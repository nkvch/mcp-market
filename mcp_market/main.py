# mcp_market/main.py
from fastapi import FastAPI, Request, HTTPException, Depends
import uvicorn
from .routers import servers
import subprocess
import threading
import time
import requests
import httpx
from fastapi.responses import StreamingResponse
from .services.server_manager import ServerManager
from dotenv import load_dotenv
load_dotenv()


app = FastAPI(
    title="MCP Market API",
    description="API for managing MCP servers",
    version="0.1.0",
)

# Include routers
app.include_router(servers.router)

@app.get("/")
async def root():
    return {"message": "Welcome to MCP Market API"}

# Dependency to get the server manager
def get_server_manager():
    return servers.server_manager

# # Proxy endpoint for MCP servers
# @app.api_route("/api/mcp/{server_id}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
# async def proxy_to_mcp_server(
#     server_id: str, 
#     path: str, 
#     request: Request,
#     server_manager: ServerManager = Depends(get_server_manager)
# ):
#     """Proxy requests to MCP servers by server ID"""
#     # Get the server
#     server = await server_manager.get_server(server_id)

#     print(server)

#     if not server:
#         raise HTTPException(status_code=404, detail="Server not found")
    
#     if server.status != "running":
#         raise HTTPException(status_code=503, detail="Server is not running")
    
#     # Construct target URL
#     target_url = f"http://localhost:{server.port}/{'sse/' + path if path else 'sse'}"

#     print(target_url)
    
#     # Get request body
#     body = await request.body()
    
#     # Forward the request
#     try:
#         async with httpx.AsyncClient() as client:
#             response = await client.request(
#                 method=request.method,
#                 url=target_url,
#                 headers={k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]},
#                 content=body,
#                 timeout=30.0
#             )
            
#             # Return the response
#             return StreamingResponse(
#                 response.aiter_bytes(),
#                 status_code=response.status_code,
#                 headers=dict(response.headers)
#             )
#     except Exception as e:
#         raise HTTPException(status_code=502, detail=f"Error proxying to MCP server: {str(e)}")

# def start_ngrok(port):
#     """Start ngrok tunnel for the main API"""
#     ngrok_cmd = f"ngrok http {port} --log=stdout"
#     subprocess.Popen(ngrok_cmd, shell=True)
    
#     # Wait for tunnel to be established
#     time.sleep(2)
    
#     try:
#         # Get tunnel URL from ngrok API
#         response = requests.get("http://localhost:4040/api/tunnels")
#         tunnels = response.json()["tunnels"]
#         for tunnel in tunnels:
#             if str(port) in tunnel["config"]["addr"]:
#                 public_url = tunnel["public_url"]
#                 print(f"\n🚀 Main API available at: {public_url}\n")
#                 return
#     except Exception:
#         print("\n⚠️ Failed to get ngrok URL. Make sure ngrok is installed and running.\n")

# # Start ngrok in a separate thread
# threading.Thread(target=start_ngrok, args=(8000,), daemon=True).start()

def start():
    """Entry point for the application script"""
    uvicorn.run("mcp_market.main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    start()