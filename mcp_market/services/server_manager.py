# mcp_market/services/server_manager.py
import subprocess
import psutil
import socket
from typing import List, Dict, Optional, Any
import os
import signal
import time
import json
import requests
from ..models.server import Server, ServerCreate
from datetime import datetime
from e2b_code_interpreter import Sandbox
from contextlib import AsyncExitStack
import httpx
from httpx_sse import aconnect_sse
from fastapi.responses import StreamingResponse
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

class ServerManager:
    def __init__(self, base_port: int = 8100):
        self.servers: Dict[str, Server] = {}
        self.e2b_sandboxes: Dict[str, Sandbox] = {}
        self.next_port = base_port

    def _find_available_port(self) -> int:
        """Find an available port starting from self.next_port"""
        while True:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(('localhost', self.next_port)) != 0:
                    # Port is available
                    port = self.next_port
                    self.next_port += 1
                    return port
                self.next_port += 1

    async def create_e2b_server(self, server_data: ServerCreate) -> Server:
        """Create a new E2B server"""
        sbx = Sandbox(timeout=60*60)
        sbx.commands.run(f"npx -y supergateway --cors --stdio \"{server_data.command}\" --port 8000", background=True)
        self.e2b_sandboxes[sbx.sandbox_id] = sbx

        host = sbx.get_host(8000)

        url = f"https://{host}/sse"

        server = Server(
            name=server_data.name,
            command=server_data.command,
            url=url,
            sandbox_id=sbx.sandbox_id
        )

        self.servers[server.id] = server

        # sbx.pause()

        return server
    
    async def list_e2b_mcp_server_tools(self, server_id: str) -> List[str]:
        """List all MCP server tools"""
        server = self.servers.get(server_id)
        if not server or not server.sandbox_id:
            raise ValueError("Server not found")

        async with AsyncExitStack() as stack:
            # Enter the context managers properly within this function's task
            sse_transport = await stack.enter_async_context(sse_client(server.url))
            read_stream, write_stream = sse_transport
            session = await stack.enter_async_context(ClientSession(read_stream, write_stream))

            await session.initialize()

            # List available tools
            response = await session.list_tools()
            tools = response.tools

            return [tool.name for tool in tools]


    async def create_server(self, server_data: ServerCreate) -> Server:
        """Start a new MCP server using supergateway"""
        port = self._find_available_port()
        
        # Prepare the supergateway command
        gateway_cmd = f"npx -y supergateway --cors --stdio \"{server_data.command}\" --port {port}"
        
        # Start the process
        process = subprocess.Popen(
            gateway_cmd,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid  # Use process group for easier termination
        )
        
        # Wait a moment for the server to start
        time.sleep(2)
        
        # Check if process is still running
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise RuntimeError(f"Server failed to start: {stderr}")
        
        # Create server record
        server = Server(
            name=server_data.name,
            command=server_data.command,
            url="",  # Will be set after ID is generated
            port=port,
            process_id=process.pid,
            local_url=f"http://localhost:{port}/sse"  # Keep local URL for reference
        )
        
        # Now that we have an ID, set the URL
        server.url = f"/api/mcp/{server.id}"
        
        self.servers[server.id] = server
        print(f"Added server {server.id} to manager. Total servers: {len(self.servers)}")
        return server
    
    async def get_sse(self, server_id: str):
        """Get a proxy to the SSE stream for a specific server"""
        server = self.servers.get(server_id)
        if not server or not server.sandbox_id:
            raise ValueError("Server not found")
        
        # Return a streaming response that proxies the SSE connection
        from fastapi.responses import StreamingResponse
        
        async def event_stream():
            """Generator that proxies the SSE events from the sandbox to the client"""
            # Create a client to connect to the sandbox SSE endpoint
            async with httpx.AsyncClient() as client:
                # Use a much longer timeout for SSE connections
                timeout = httpx.Timeout(5.0, read=5*60*60)  # 1 hour read timeout
                
                async with aconnect_sse(client, "GET", server.url, timeout=timeout) as event_source:
                    # Check if connection was successful
                    event_source.response.raise_for_status()
                    
                    # Now forward each SSE event from the remote server
                    async for sse in event_source.aiter_sse():
                        # Skip the original endpoint event since we've already sent our own
                        print("SSE event", sse)
                        if sse.event == "endpoint":
                            print("Skipping endpoint event", sse)
                            # First, send a custom endpoint event to tell the client where to send messages
                            # This is crucial - the client is waiting for this!
                            base_path = f"/servers/{server_id}"
                            endpoint_event = [
                                "event: endpoint",
                                f"data: {base_path}{sse.data}",
                                "",
                                ""
                            ]
                            yield "\n".join(endpoint_event)
                            continue
                            
                        # Reconstruct the SSE format
                        output = []
                        if sse.event:
                            output.append(f"event: {sse.event}")
                        if sse.id:
                            output.append(f"id: {sse.id}")
                        if sse.retry:
                            output.append(f"retry: {sse.retry}")
                        # Data can be multi-line, handle each line
                        for line in sse.data.splitlines():
                            output.append(f"data: {line}")
                        # End with an empty line as per SSE spec
                        output.append("")

                        yield "\n".join(output)
        
        # Return a streaming response with the appropriate headers
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable buffering in Nginx
            }
        )
    
    async def list_servers(self) -> List[Server]:
        """List all registered servers"""
        # Update status of each server
        print(Sandbox.list())

        for server_id, server in list(self.servers.items()):
            if server.process_id:
                try:
                    # Check if process is still running
                    process = psutil.Process(server.process_id)
                    if process.is_running():
                        server.status = "running"
                    else:
                        server.status = "stopped"
                except psutil.NoSuchProcess:
                    server.status = "stopped"
        
        return list(self.servers.values())

    async def get_server(self, server_id: str) -> Optional[Server]:
        """Get a server by ID"""
        return self.servers.get(server_id)

    async def stop_local_server(self, server_id: str) -> bool:
        """Stop a running server"""
        server = self.servers.get(server_id)
        if not server or not server.process_id:
            return False

        try:
            # Kill the process group
            os.killpg(os.getpgid(server.process_id), signal.SIGTERM)
            server.status = "stopped"
            return True
        except (ProcessLookupError, psutil.NoSuchProcess):
            server.status = "stopped"
            return True
        except Exception:
            return False
        
    async def stop_e2b_server(self, server_id: str) -> bool:
        """Stop an E2B server"""
        server = self.servers.get(server_id)
        if not server or not server.sandbox_id:
            return False

        sbx = self.e2b_sandboxes.get(server.sandbox_id)
        if not sbx:
            return False
        
        sbx.kill()
        del self.e2b_sandboxes[server.sandbox_id]
        return True
    
    async def delete_server(self, server_id: str) -> bool:
        """Stop and delete a server"""
        await self.stop_e2b_server(server_id)
        if server_id in self.servers:
            del self.servers[server_id]
            return True
        return False
