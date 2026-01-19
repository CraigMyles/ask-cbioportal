"""FastAPI web application for ask-cbioportal."""

import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ask_cbioportal.agent import Agent
from ask_cbioportal.backends import McpClickHouseBackend, RestApiBackend
from ask_cbioportal.config import BackendType, Config, get_config

# Global state
_config: Config | None = None
_backend: RestApiBackend | McpClickHouseBackend | None = None
_sessions: dict[str, Agent] = {}  # session_id -> Agent


def get_backend(config: Config) -> RestApiBackend | McpClickHouseBackend:
    """Create the appropriate backend based on configuration."""
    if config.backend == BackendType.MCP:
        return McpClickHouseBackend(config)
    return RestApiBackend(config)


def get_or_create_session(session_id: str) -> Agent:
    """Get existing session or create a new one."""
    global _sessions, _config, _backend

    if session_id not in _sessions:
        if not _config or not _backend:
            raise RuntimeError("Server not initialized")
        _sessions[session_id] = Agent(_config, _backend)

    return _sessions[session_id]


def clear_session(session_id: str) -> None:
    """Clear a session's conversation history."""
    if session_id in _sessions:
        _sessions[session_id].clear_conversation()


def delete_session(session_id: str) -> None:
    """Delete a session entirely."""
    if session_id in _sessions:
        del _sessions[session_id]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    global _config, _backend

    _config = get_config()
    errors = _config.validate()
    if errors:
        raise RuntimeError(f"Configuration errors: {', '.join(errors)}")

    _backend = get_backend(_config)
    await _backend.initialize()

    yield

    if _backend:
        await _backend.close()
    _sessions.clear()


app = FastAPI(
    title="ask-cbioportal",
    description="Natural language interface for cBioPortal cancer genomics data",
    version="0.1.0",
    lifespan=lifespan,
)

# Serve static files
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


class QueryRequest(BaseModel):
    """Request model for queries."""

    question: str
    session_id: str | None = None
    clear_history: bool = False


class QueryResponse(BaseModel):
    """Response model for queries."""

    answer: str
    session_id: str
    tool_calls: list[dict] = []


class NewSessionResponse(BaseModel):
    """Response for creating a new session."""

    session_id: str


@app.get("/")
async def root() -> FileResponse:
    """Serve the main chat interface."""
    return FileResponse(static_dir / "index.html")


@app.post("/api/session/new", response_model=NewSessionResponse)
async def create_session() -> NewSessionResponse:
    """Create a new chat session."""
    session_id = str(uuid.uuid4())
    get_or_create_session(session_id)
    return NewSessionResponse(session_id=session_id)


@app.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    """Submit a query and get a response."""
    session_id = request.session_id or str(uuid.uuid4())
    agent = get_or_create_session(session_id)

    if request.clear_history:
        agent.clear_conversation()

    response = await agent.query(request.question)
    return QueryResponse(
        answer=response.content,
        session_id=session_id,
        tool_calls=response.tool_calls,
    )


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """WebSocket endpoint for streaming chat with session support."""
    await websocket.accept()

    try:
        agent = get_or_create_session(session_id)
    except RuntimeError as e:
        await websocket.send_json({"type": "error", "content": str(e)})
        await websocket.close()
        return

    # Send session confirmation
    await websocket.send_json({"type": "session", "session_id": session_id})

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("clear"):
                clear_session(session_id)
                await websocket.send_json({"type": "cleared"})
                continue

            question = data.get("question", "")
            if not question:
                continue

            try:
                async for chunk in agent.query_stream(question):
                    if chunk.startswith("\n[Calling"):
                        tool_name = chunk.strip().replace("\n[Calling ", "").replace("...]", "")
                        await websocket.send_json({"type": "tool_call", "name": tool_name})
                    else:
                        await websocket.send_json({"type": "chunk", "content": chunk})

                await websocket.send_json({"type": "done"})
            except Exception as e:
                await websocket.send_json({"type": "error", "content": str(e)})

    except WebSocketDisconnect:
        pass


# Legacy endpoint for backwards compatibility
@app.websocket("/ws")
async def websocket_endpoint_legacy(websocket: WebSocket) -> None:
    """Legacy WebSocket endpoint - creates a new session automatically."""
    session_id = str(uuid.uuid4())
    await websocket_endpoint(websocket, session_id)


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "backend": _backend.name if _backend else None,
        "model": _config.model if _config else None,
        "llm_provider": _config.llm_provider.value if _config else None,
        "active_sessions": len(_sessions),
    }


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the web server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
