# mcp_market/routers/servers.py
from fastapi import APIRouter, HTTPException, Depends
from typing import List
from ..models.server import Server, ServerCreate
from ..services.server_manager import ServerManager
import requests

router = APIRouter(prefix="/servers", tags=["servers"])

# Create a singleton instance of ServerManager
server_manager = ServerManager()

# Dependency to get the server manager
def get_server_manager():
    return server_manager

@router.post("/", response_model=Server)
async def create_server(
    server_data: ServerCreate, 
    server_manager: ServerManager = Depends(get_server_manager)
):
    """Install and run a new MCP server"""
    try:
        server = await server_manager.create_e2b_server(server_data)
        return server
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/", response_model=List[Server])
async def list_servers(server_manager: ServerManager = Depends(get_server_manager)):
    """List all installed MCP servers"""
    return await server_manager.list_servers()


@router.get("/{server_id}", response_model=Server)
async def get_server(
    server_id: str, 
    server_manager: ServerManager = Depends(get_server_manager)
):
    """Get details of a specific MCP server"""
    server = await server_manager.get_server(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return server

@router.get("/{server_id}/tools", response_model=List[str])
async def list_tools(
    server_id: str, 
    server_manager: ServerManager = Depends(get_server_manager)
):
    """List all tools available for a specific MCP server"""
    return await server_manager.list_e2b_mcp_server_tools(server_id)


@router.delete("/{server_id}")
async def delete_server(
    server_id: str, 
    server_manager: ServerManager = Depends(get_server_manager)
):
    """Stop and delete an MCP server"""
    success = await server_manager.delete_server(server_id)
    if not success:
        raise HTTPException(status_code=404, detail="Server not found")
    return {"message": "Server deleted successfully"}


@router.get("/public-urls", tags=["servers"])
async def get_public_urls(server_manager: ServerManager = Depends(get_server_manager)):
    """Get all public URLs for sharing"""
    servers = await server_manager.list_servers()
    
    # Get main API URL
    main_api_url = "Unknown"
    try:
        response = requests.get("http://localhost:4040/api/tunnels")
        tunnels = response.json()["tunnels"]
        for tunnel in tunnels:
            if "8000" in tunnel["config"]["addr"]:
                main_api_url = tunnel["public_url"]
                break
    except Exception:
        pass
    
    return {
        "main_api": main_api_url,
        "servers": [
            {
                "id": server.id,
                "name": server.name,
                "url": f"{main_api_url}{server.url}",  # Combine with main API URL
                "status": server.status
            }
            for server in servers
        ]
    }