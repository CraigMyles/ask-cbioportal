"""Tests for the AI agent."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ask_cbioportal.agent import Agent, AgentResponse
from ask_cbioportal.backends.base import Backend, BackendTool, ToolResult
from ask_cbioportal.config import Config


class MockBackend(Backend):
    """Mock backend for testing."""

    @property
    def name(self) -> str:
        return "Mock Backend"

    @property
    def description(self) -> str:
        return "A mock backend for testing"

    async def initialize(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def get_tools(self) -> list[BackendTool]:
        return [
            BackendTool(
                name="test_tool",
                description="A test tool",
                parameters={
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                },
            )
        ]

    async def execute_tool(
        self, tool_name: str, arguments: dict
    ) -> ToolResult:
        if tool_name == "test_tool":
            return ToolResult(
                success=True,
                data={"result": f"Executed with {arguments}"},
            )
        return ToolResult(success=False, error="Unknown tool")

    def get_system_prompt_addition(self) -> str:
        return "This is a mock backend."


class TestAgent:
    """Tests for Agent class."""

    @pytest.fixture
    def config(self) -> Config:
        """Create test config."""
        return Config(
            anthropic_api_key="test-key",
            claude_model="claude-sonnet-4-20250514",
        )

    @pytest.fixture
    def backend(self) -> MockBackend:
        """Create mock backend."""
        return MockBackend()

    @pytest.fixture
    def agent(self, config: Config, backend: MockBackend) -> Agent:
        """Create agent with mock backend."""
        return Agent(config, backend)

    def test_system_prompt(self, agent: Agent) -> None:
        """Test system prompt includes backend addition."""
        prompt = agent.system_prompt

        assert "cBioPortal" in prompt
        assert "mock backend" in prompt.lower()

    def test_get_tools(self, agent: Agent) -> None:
        """Test getting tools in Anthropic format."""
        tools = agent.get_tools()

        assert len(tools) == 1
        assert tools[0]["name"] == "test_tool"
        assert "input_schema" in tools[0]

    def test_clear_conversation(self, agent: Agent) -> None:
        """Test clearing conversation history."""
        agent.conversation = [{"role": "user", "content": "test"}]
        agent.clear_conversation()

        assert len(agent.conversation) == 0

    @pytest.mark.asyncio
    async def test_query_without_tools(
        self, agent: Agent, config: Config
    ) -> None:
        """Test query that doesn't require tool use."""
        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = [MagicMock(type="text", text="Hello!")]

        with patch.object(
            agent.client.messages, "create", return_value=mock_response
        ):
            response = await agent.query("Hello")

        assert response.content == "Hello!"
        assert len(response.tool_calls) == 0

    @pytest.mark.asyncio
    async def test_query_with_tool_use(
        self, agent: Agent, config: Config
    ) -> None:
        """Test query that uses a tool."""
        # First response: tool use
        tool_response = MagicMock()
        tool_response.stop_reason = "tool_use"
        tool_response.content = [
            MagicMock(type="text", text="Let me check that."),
            MagicMock(
                type="tool_use",
                id="tool_123",
                name="test_tool",
                input={"query": "test"},
            ),
        ]

        # Second response: final answer
        final_response = MagicMock()
        final_response.stop_reason = "end_turn"
        final_response.content = [
            MagicMock(type="text", text="Here's what I found.")
        ]

        with patch.object(
            agent.client.messages,
            "create",
            side_effect=[tool_response, final_response],
        ):
            response = await agent.query("What's the data?")

        assert response.content == "Here's what I found."
        assert len(response.tool_calls) == 1
        assert response.tool_calls[0]["name"] == "test_tool"
        assert len(response.tool_results) == 1
        assert response.tool_results[0]["success"] is True

    def test_conversation_history(self, agent: Agent) -> None:
        """Test that conversation history is maintained."""
        # Simulate adding messages
        agent.conversation.append({"role": "user", "content": "Question 1"})
        agent.conversation.append({"role": "assistant", "content": "Answer 1"})

        assert len(agent.conversation) == 2
        assert agent.conversation[0]["content"] == "Question 1"
        assert agent.conversation[1]["content"] == "Answer 1"
