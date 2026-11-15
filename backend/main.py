"""
Groww AI Trading Agent - Main Application Entrypoint
FastAPI server, WebSocket live event streaming, and static UI mounting.
"""

import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import config
from backend.core.logger import logger
from backend.database.db import db
from backend.api.routes import router as api_router
from backend.api.websocket import ws_manager
from backend.agents.master_agent import master_agent

# Background WebSocket broadcaster
async def telemetry_broadcaster():
    """Pumps live system telemetry and quotes to all connected browser control centers."""
    while True:
        try:
            overview = master_agent.get_system_overview()
            await ws_manager.broadcast({
                "type": "TELEMETRY_UPDATE",
                "data": overview.model_dump()
            })
        except Exception as e:
            logger.debug(f"Telemetry broadcast notice: {e}")
        await asyncio.sleep(1.5)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Groww Autonomous AI Trading Agent backend...")
    # Start telemetry broadcaster background task
    broadcaster_task = asyncio.create_task(telemetry_broadcaster())
    yield
    logger.info("Shutting down Groww AI Trading Agent...")
    broadcaster_task.cancel()
    await master_agent.stop()

app = FastAPI(
    title=config.PROJECT_NAME,
    version=config.VERSION,
    lifespan=lifespan
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api")

# WebSocket Endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send immediate initial state
        overview = master_agent.get_system_overview()
        await websocket.send_json({
            "type": "INITIAL_STATE",
            "data": overview.model_dump()
        })
        while True:
            data = await websocket.receive_text()
            # Handle incoming ping / messages if needed
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"WebSocket client closed: {e}")
        ws_manager.disconnect(websocket)

# Mount frontend static files
frontend_dir = os.path.abspath("frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
async def serve_index():
    index_file = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Groww AI Trading Agent API Active. Frontend not yet compiled."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=config.SERVER_HOST,
        port=config.SERVER_PORT,
        reload=False
    )
