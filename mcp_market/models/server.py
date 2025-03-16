# mcp_market/models/server.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid

class ServerCreate(BaseModel):
    """Model for creating a new server"""
    command: str = Field(..., description="Command to install and run the server")
    name: str = Field(..., description="Friendly name for the server")

class Server(BaseModel):
    """Model for a running server"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    command: str
    url: str  # Relative URL for proxy
    sandbox_id: Optional[str] = None
    process_id: Optional[int] = None
    created_at: datetime = Field(default_factory=datetime.now)
    status: str = "running"  # running, stopped, error
