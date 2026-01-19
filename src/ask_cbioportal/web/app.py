"""FastAPI web application for ask-cbioportal."""

import json
import re
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


def extract_chart_from_matplotlib(text: str) -> str | None:
    """Detect matplotlib/seaborn code in response and extract data to create a chart.

    This is a fallback for when the LLM outputs matplotlib code instead of using
    the create_chart tool.
    """
    # Check if there's already a chart block - if so, don't process
    if "```chart" in text:
        return None

    # Check if there's matplotlib or similar plotting code
    matplotlib_patterns = [
        r"plt\.pie\(",
        r"plt\.bar\(",
        r"plt\.figure\(",
        r"matplotlib",
        r"seaborn",
        r"import\s+matplotlib",
        r"import\s+seaborn",
    ]

    has_matplotlib = any(re.search(p, text, re.IGNORECASE) for p in matplotlib_patterns)
    if not has_matplotlib:
        return None

    # Try to extract labels and values from the code
    # Look for patterns like: labels = ['A', 'B', 'C'] or sizes = [10, 20, 30]
    labels = None
    values = None
    title = "Data Distribution"
    chart_type = "pie"  # Default

    # Extract labels
    labels_match = re.search(r"labels\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if labels_match:
        labels_str = labels_match.group(1)
        # Parse string labels
        labels = re.findall(r'["\']([^"\']+)["\']', labels_str)

    # Extract values (might be called sizes, values, counts, etc.)
    for var_name in ["sizes", "values", "counts", "data"]:
        values_match = re.search(rf"{var_name}\s*=\s*\[([\d,\s.]+)\]", text)
        if values_match:
            values_str = values_match.group(1)
            try:
                values = [float(x.strip()) for x in values_str.split(",") if x.strip()]
            except ValueError:
                pass
            if values:
                break

    # Also try to extract from dict patterns like {'MSI-H': 88, 'MSS': 496}
    if not labels or not values:
        dict_match = re.search(r"\{([^}]+)\}", text)
        if dict_match:
            dict_content = dict_match.group(1)
            pairs = re.findall(r'["\']([^"\']+)["\']\s*:\s*(\d+\.?\d*)', dict_content)
            if pairs:
                labels = [p[0] for p in pairs]
                values = [float(p[1]) for p in pairs]

    # Try to extract title
    title_match = re.search(r"title\s*=\s*['\"]([^'\"]+)['\"]", text)
    if title_match:
        title = title_match.group(1)
    else:
        # Try plt.title("...")
        title_match = re.search(r"plt\.title\s*\(\s*['\"]([^'\"]+)['\"]", text)
        if title_match:
            title = title_match.group(1)

    # Detect chart type
    if "plt.bar(" in text or "bar" in text.lower():
        chart_type = "bar"
    elif "plt.pie(" in text or "pie" in text.lower():
        chart_type = "pie"

    # If we extracted both labels and values, create the chart
    if labels and values and len(labels) == len(values):
        colors = ["#10a37f", "#5436da", "#ef4444", "#f59e0b", "#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6"]

        if chart_type == "pie":
            chart_config = {
                "data": [{
                    "type": "pie",
                    "labels": labels,
                    "values": values,
                    "name": "",
                    "marker": {"colors": colors[:len(values)]},
                    "textinfo": "label+percent",
                    "textposition": "inside",
                    "hole": 0,
                    "hovertemplate": "<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>"
                }],
                "layout": {
                    "title": {"text": title, "font": {"size": 16}}
                }
            }
        else:
            chart_config = {
                "data": [{
                    "type": "bar",
                    "x": labels,
                    "y": values,
                    "name": "",
                    "marker": {"color": colors[:len(values)]},
                    "hovertemplate": "<b>%{x}</b><br>Count: %{y}<extra></extra>"
                }],
                "layout": {
                    "title": {"text": title, "font": {"size": 16}},
                    "xaxis": {"title": "", "tickangle": -45 if len(labels) > 4 else 0},
                    "yaxis": {"title": "Count", "gridcolor": "#3a3a3a"}
                }
            }

        return f"\n\n```chart\n{json.dumps(chart_config, indent=2)}\n```"

    return None


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

            # Update model if specified in the message
            model = data.get("model")
            if model and agent.config.model != model:
                agent.config.model = model
                # Recreate LLM client with new model
                from ask_cbioportal.agent import create_llm_client
                agent.llm_client = create_llm_client(agent.config)

            try:
                full_response = ""
                async for chunk in agent.query_stream(question):
                    if chunk.startswith("\n[Calling"):
                        tool_name = chunk.strip().replace("\n[Calling ", "").replace("...]", "")
                        await websocket.send_json({"type": "tool_call", "name": tool_name})
                    else:
                        await websocket.send_json({"type": "chunk", "content": chunk})
                        full_response += chunk

                # Post-processing: If LLM output matplotlib code, extract and send a chart
                chart_block = extract_chart_from_matplotlib(full_response)
                if chart_block:
                    await websocket.send_json({"type": "chunk", "content": chart_block})

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
