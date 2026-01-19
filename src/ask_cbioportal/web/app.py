"""FastAPI web application for ask-cbioportal."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ask_cbioportal.agent import Agent
from ask_cbioportal.backends import McpClickHouseBackend, RestApiBackend
from ask_cbioportal.config import BackendType, Config, get_config

# Global state
_agent: Agent | None = None
_backend: RestApiBackend | McpClickHouseBackend | None = None


def get_backend(config: Config) -> RestApiBackend | McpClickHouseBackend:
    """Create the appropriate backend based on configuration."""
    if config.backend == BackendType.MCP:
        return McpClickHouseBackend(config)
    return RestApiBackend(config)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    global _agent, _backend

    config = get_config()
    errors = config.validate()
    if errors:
        raise RuntimeError(f"Configuration errors: {', '.join(errors)}")

    _backend = get_backend(config)
    await _backend.initialize()
    _agent = Agent(config, _backend)

    yield

    if _backend:
        await _backend.close()


app = FastAPI(
    title="ask-cbioportal",
    description="Natural language interface for cBioPortal cancer genomics data",
    version="0.1.0",
    lifespan=lifespan,
)

# Serve static files
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


class QueryRequest(BaseModel):
    """Request model for queries."""

    question: str
    clear_history: bool = False


class QueryResponse(BaseModel):
    """Response model for queries."""

    answer: str
    tool_calls: list[dict] = []


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    """Serve the main chat interface."""
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ask-cbioportal</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #1a1a2e;
            color: #eee;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        header {
            background: #16213e;
            padding: 1rem 2rem;
            border-bottom: 1px solid #0f3460;
        }
        header h1 {
            font-size: 1.5rem;
            color: #e94560;
        }
        header p {
            font-size: 0.9rem;
            color: #888;
            margin-top: 0.25rem;
        }
        #chat-container {
            flex: 1;
            overflow-y: auto;
            padding: 1rem 2rem;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }
        .message {
            max-width: 80%;
            padding: 1rem;
            border-radius: 12px;
            line-height: 1.5;
        }
        .message.user {
            background: #0f3460;
            align-self: flex-end;
            border-bottom-right-radius: 4px;
        }
        .message.assistant {
            background: #16213e;
            align-self: flex-start;
            border-bottom-left-radius: 4px;
        }
        .message.assistant pre {
            background: #1a1a2e;
            padding: 0.75rem;
            border-radius: 6px;
            overflow-x: auto;
            margin: 0.5rem 0;
        }
        .message.assistant code {
            font-family: 'Monaco', 'Consolas', monospace;
            font-size: 0.9em;
        }
        .message .tool-call {
            background: #1a1a2e;
            padding: 0.5rem;
            border-radius: 4px;
            font-size: 0.85rem;
            color: #888;
            margin: 0.5rem 0;
        }
        #input-container {
            padding: 1rem 2rem;
            background: #16213e;
            border-top: 1px solid #0f3460;
        }
        #input-form {
            display: flex;
            gap: 0.5rem;
        }
        #question-input {
            flex: 1;
            padding: 0.75rem 1rem;
            border: 1px solid #0f3460;
            border-radius: 8px;
            background: #1a1a2e;
            color: #eee;
            font-size: 1rem;
        }
        #question-input:focus {
            outline: none;
            border-color: #e94560;
        }
        button {
            padding: 0.75rem 1.5rem;
            border: none;
            border-radius: 8px;
            background: #e94560;
            color: white;
            font-size: 1rem;
            cursor: pointer;
            transition: background 0.2s;
        }
        button:hover {
            background: #c73e54;
        }
        button:disabled {
            background: #555;
            cursor: not-allowed;
        }
        #clear-btn {
            background: #0f3460;
        }
        #clear-btn:hover {
            background: #0a2240;
        }
        .typing-indicator {
            display: flex;
            gap: 4px;
            padding: 0.5rem;
        }
        .typing-indicator span {
            width: 8px;
            height: 8px;
            background: #e94560;
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out;
        }
        .typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
        .typing-indicator span:nth-child(2) { animation-delay: -0.16s; }
        @keyframes bounce {
            0%, 80%, 100% { transform: scale(0); }
            40% { transform: scale(1); }
        }
        .welcome {
            text-align: center;
            padding: 2rem;
            color: #888;
        }
        .welcome h2 {
            color: #e94560;
            margin-bottom: 1rem;
        }
        .welcome p {
            margin: 0.5rem 0;
        }
        .examples {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            justify-content: center;
            margin-top: 1rem;
        }
        .example-btn {
            background: #0f3460;
            padding: 0.5rem 1rem;
            font-size: 0.9rem;
        }
    </style>
</head>
<body>
    <header>
        <h1>ask-cbioportal</h1>
        <p>Natural language interface for cBioPortal cancer genomics data</p>
    </header>

    <div id="chat-container">
        <div class="welcome">
            <h2>Welcome to ask-cbioportal</h2>
            <p>Ask questions about cancer genomics data from cBioPortal.</p>
            <p>Try some example questions:</p>
            <div class="examples">
                <button class="example-btn" onclick="askExample(this)">How many studies are available?</button>
                <button class="example-btn" onclick="askExample(this)">Find breast cancer studies</button>
                <button class="example-btn" onclick="askExample(this)">What genes are commonly mutated in lung cancer?</button>
            </div>
        </div>
    </div>

    <div id="input-container">
        <form id="input-form">
            <input type="text" id="question-input" placeholder="Ask a question about cancer genomics..." autocomplete="off">
            <button type="submit" id="send-btn">Send</button>
            <button type="button" id="clear-btn" onclick="clearChat()">Clear</button>
        </form>
    </div>

    <script>
        const chatContainer = document.getElementById('chat-container');
        const questionInput = document.getElementById('question-input');
        const sendBtn = document.getElementById('send-btn');
        const form = document.getElementById('input-form');

        let ws = null;
        let currentMessageDiv = null;

        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            ws.onopen = () => console.log('WebSocket connected');

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);

                if (data.type === 'chunk') {
                    if (!currentMessageDiv) {
                        currentMessageDiv = addMessage('', 'assistant');
                    }
                    currentMessageDiv.innerHTML += escapeHtml(data.content);
                } else if (data.type === 'tool_call') {
                    if (!currentMessageDiv) {
                        currentMessageDiv = addMessage('', 'assistant');
                    }
                    currentMessageDiv.innerHTML += `<div class="tool-call">Calling: ${data.name}</div>`;
                } else if (data.type === 'done') {
                    currentMessageDiv = null;
                    sendBtn.disabled = false;
                    questionInput.disabled = false;
                } else if (data.type === 'error') {
                    if (currentMessageDiv) {
                        currentMessageDiv.innerHTML += `<span style="color: #e94560;">Error: ${data.content}</span>`;
                    } else {
                        addMessage(`Error: ${data.content}`, 'assistant');
                    }
                    currentMessageDiv = null;
                    sendBtn.disabled = false;
                    questionInput.disabled = false;
                }

                chatContainer.scrollTop = chatContainer.scrollHeight;
            };

            ws.onclose = () => {
                console.log('WebSocket closed, reconnecting...');
                setTimeout(connectWebSocket, 1000);
            };

            ws.onerror = (error) => console.error('WebSocket error:', error);
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function addMessage(content, role) {
            // Remove welcome message if present
            const welcome = chatContainer.querySelector('.welcome');
            if (welcome) welcome.remove();

            const div = document.createElement('div');
            div.className = `message ${role}`;
            div.innerHTML = content;
            chatContainer.appendChild(div);
            chatContainer.scrollTop = chatContainer.scrollHeight;
            return div;
        }

        function addTypingIndicator() {
            const div = document.createElement('div');
            div.className = 'message assistant typing-indicator';
            div.innerHTML = '<span></span><span></span><span></span>';
            chatContainer.appendChild(div);
            chatContainer.scrollTop = chatContainer.scrollHeight;
            return div;
        }

        async function sendMessage(question) {
            if (!question.trim() || !ws || ws.readyState !== WebSocket.OPEN) return;

            addMessage(question, 'user');
            questionInput.value = '';
            sendBtn.disabled = true;
            questionInput.disabled = true;

            ws.send(JSON.stringify({ question }));
        }

        function askExample(btn) {
            sendMessage(btn.textContent);
        }

        function clearChat() {
            chatContainer.innerHTML = `
                <div class="welcome">
                    <h2>Welcome to ask-cbioportal</h2>
                    <p>Ask questions about cancer genomics data from cBioPortal.</p>
                </div>
            `;
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ clear: true }));
            }
        }

        form.addEventListener('submit', (e) => {
            e.preventDefault();
            sendMessage(questionInput.value);
        });

        connectWebSocket();
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@app.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse:
    """Submit a query and get a response."""
    if not _agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")

    if request.clear_history:
        _agent.clear_conversation()

    response = await _agent.query(request.question)
    return QueryResponse(
        answer=response.content,
        tool_calls=response.tool_calls,
    )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for streaming chat."""
    await websocket.accept()

    if not _agent:
        await websocket.send_json({"type": "error", "content": "Agent not initialized"})
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("clear"):
                _agent.clear_conversation()
                continue

            question = data.get("question", "")
            if not question:
                continue

            try:
                async for chunk in _agent.query_stream(question):
                    if chunk.startswith("\n[Calling"):
                        # Extract tool name
                        tool_name = chunk.strip().replace("\n[Calling ", "").replace("...]", "")
                        await websocket.send_json({"type": "tool_call", "name": tool_name})
                    else:
                        await websocket.send_json({"type": "chunk", "content": chunk})

                await websocket.send_json({"type": "done"})
            except Exception as e:
                await websocket.send_json({"type": "error", "content": str(e)})

    except WebSocketDisconnect:
        pass


@app.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "agent_initialized": _agent is not None,
        "backend": _backend.name if _backend else None,
    }


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the web server."""
    import uvicorn

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()
