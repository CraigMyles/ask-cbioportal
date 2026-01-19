"""Claude-powered AI agent for cBioPortal queries."""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import anthropic
import openai

from ask_cbioportal.backends.base import Backend
from ask_cbioportal.config import Config, LLMProvider
from ask_cbioportal.prompts import get_full_system_prompt


@dataclass
class Message:
    """A message in the conversation."""

    role: str  # "user" or "assistant"
    content: str


@dataclass
class AgentResponse:
    """Response from the agent."""

    content: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)


class LLMClient(ABC):
    """Abstract base class for LLM clients."""

    @abstractmethod
    def get_tools_format(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert tools to the format expected by this provider."""
        pass

    @abstractmethod
    async def query(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> tuple[str, list[dict[str, Any]], str]:
        """
        Send a query and return (response_text, tool_calls, stop_reason).

        tool_calls is a list of dicts with 'id', 'name', 'input' keys.
        stop_reason is 'tool_use' if tools were called, otherwise 'end'.
        """
        pass

    @abstractmethod
    async def query_stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> AsyncIterator[tuple[str, list[dict[str, Any]], bool]]:
        """
        Stream a query and yield (chunk, tool_calls, is_done).

        tool_calls is populated when streaming is done.
        is_done is True on the final yield.
        """
        pass


class AnthropicClient(LLMClient):
    """Anthropic API client."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = anthropic.Anthropic(api_key=config.anthropic_api_key)

    def get_tools_format(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Anthropic tools are already in the right format."""
        return tools

    async def query(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> tuple[str, list[dict[str, Any]], str]:
        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

        text = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        stop_reason = "tool_use" if response.stop_reason == "tool_use" else "end"
        return text, tool_calls, stop_reason

    async def query_stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> AsyncIterator[tuple[str, list[dict[str, Any]], bool]]:
        collected_text = ""
        tool_calls = []
        current_tool_call: dict[str, Any] | None = None

        with self.client.messages.stream(
            model=self.config.model,
            max_tokens=max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages,
        ) as stream:
            for event in stream:
                if event.type == "content_block_start":
                    if event.content_block.type == "tool_use":
                        current_tool_call = {
                            "id": event.content_block.id,
                            "name": event.content_block.name,
                            "input_json": "",
                        }
                elif event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        collected_text += event.delta.text
                        yield event.delta.text, [], False
                    elif hasattr(event.delta, "partial_json"):
                        if current_tool_call:
                            current_tool_call["input_json"] += event.delta.partial_json
                elif event.type == "content_block_stop":
                    if current_tool_call:
                        try:
                            current_tool_call["input"] = json.loads(
                                current_tool_call["input_json"]
                            )
                        except json.JSONDecodeError:
                            current_tool_call["input"] = {}
                        tool_calls.append(current_tool_call)
                        current_tool_call = None

            final_message = stream.get_final_message()
            is_tool_use = final_message.stop_reason == "tool_use"

        yield "", tool_calls, True


class LiteLLMClient(LLMClient):
    """LiteLLM/OpenAI-compatible API client."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = openai.OpenAI(
            api_key=config.litellm_api_key or "not-needed",
            base_url=config.litellm_api_base,
        )

    def get_tools_format(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert Anthropic tool format to OpenAI format."""
        openai_tools = []
        for tool in tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"],
                },
            })
        return openai_tools

    def _convert_messages(
        self, messages: list[dict[str, Any]], system_prompt: str
    ) -> list[dict[str, Any]]:
        """Convert Anthropic message format to OpenAI format."""
        openai_messages = [{"role": "system", "content": system_prompt}]

        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if isinstance(content, str):
                openai_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                # Handle Anthropic's structured content
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            openai_messages.append({"role": role, "content": item["text"]})
                        elif item.get("type") == "tool_use":
                            # Assistant's tool call
                            openai_messages.append({
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [{
                                    "id": item["id"],
                                    "type": "function",
                                    "function": {
                                        "name": item["name"],
                                        "arguments": json.dumps(item["input"]),
                                    },
                                }],
                            })
                        elif item.get("type") == "tool_result":
                            # Tool result
                            openai_messages.append({
                                "role": "tool",
                                "tool_call_id": item["tool_use_id"],
                                "content": item["content"],
                            })

        return openai_messages

    async def query(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> tuple[str, list[dict[str, Any]], str]:
        openai_messages = self._convert_messages(messages, system_prompt)
        openai_tools = self.get_tools_format(tools)

        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=openai_messages,
            tools=openai_tools if openai_tools else None,
            max_tokens=max_tokens,
        )

        message = response.choices[0].message
        text = message.content or ""
        tool_calls = []

        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "input": json.loads(tc.function.arguments),
                })

        stop_reason = "tool_use" if tool_calls else "end"
        return text, tool_calls, stop_reason

    async def query_stream(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        max_tokens: int,
    ) -> AsyncIterator[tuple[str, list[dict[str, Any]], bool]]:
        openai_messages = self._convert_messages(messages, system_prompt)
        openai_tools = self.get_tools_format(tools)

        stream = self.client.chat.completions.create(
            model=self.config.model,
            messages=openai_messages,
            tools=openai_tools if openai_tools else None,
            max_tokens=max_tokens,
            stream=True,
        )

        collected_text = ""
        tool_calls: dict[int, dict[str, Any]] = {}  # index -> tool call

        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if not delta:
                continue

            # Handle text content
            if delta.content:
                collected_text += delta.content
                yield delta.content, [], False

            # Handle tool calls (streamed incrementally)
            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in tool_calls:
                        tool_calls[idx] = {
                            "id": tc.id or "",
                            "name": tc.function.name if tc.function and tc.function.name else "",
                            "arguments": "",
                        }
                    if tc.id:
                        tool_calls[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            tool_calls[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            tool_calls[idx]["arguments"] += tc.function.arguments

        # Convert collected tool calls to final format
        final_tool_calls = []
        for tc in tool_calls.values():
            try:
                args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                args = {}
            final_tool_calls.append({
                "id": tc["id"],
                "name": tc["name"],
                "input": args,
            })

        yield "", final_tool_calls, True


def create_llm_client(config: Config) -> LLMClient:
    """Create the appropriate LLM client based on configuration."""
    if config.llm_provider == LLMProvider.LITELLM:
        return LiteLLMClient(config)
    return AnthropicClient(config)


class Agent:
    """AI agent for querying cBioPortal."""

    def __init__(self, config: Config, backend: Backend) -> None:
        self.config = config
        self.backend = backend
        self.llm_client = create_llm_client(config)
        self.conversation: list[dict[str, Any]] = []
        self._system_prompt: str | None = None

    @property
    def system_prompt(self) -> str:
        """Get the system prompt with backend-specific additions."""
        if self._system_prompt is None:
            backend_addition = self.backend.get_system_prompt_addition()
            self._system_prompt = get_full_system_prompt(backend_addition)
        return self._system_prompt

    def get_tools(self) -> list[dict[str, Any]]:
        """Get tools in Anthropic format (will be converted by client if needed)."""
        return [tool.to_anthropic_tool() for tool in self.backend.get_tools()]

    def clear_conversation(self) -> None:
        """Clear the conversation history."""
        self.conversation = []

    def _build_assistant_content(
        self, text: str, tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, Any]] | str:
        """Build assistant content in Anthropic format."""
        if not tool_calls:
            return text

        content = []
        if text:
            content.append({"type": "text", "text": text})
        for tc in tool_calls:
            content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["input"],
            })
        return content

    async def query(self, user_message: str) -> AgentResponse:
        """Send a query to the agent and get a response."""
        # Add user message to conversation
        self.conversation.append({"role": "user", "content": user_message})

        all_tool_calls = []
        all_tool_results = []

        # Loop for tool use
        while True:
            text, tool_calls, stop_reason = await self.llm_client.query(
                messages=self.conversation,
                system_prompt=self.system_prompt,
                tools=self.get_tools(),
                max_tokens=self.config.max_tokens,
            )

            if stop_reason == "tool_use" and tool_calls:
                # Add assistant response with tool calls
                assistant_content = self._build_assistant_content(text, tool_calls)
                self.conversation.append({"role": "assistant", "content": assistant_content})

                # Execute tools
                tool_result_content = []
                for tc in tool_calls:
                    result = await self.backend.execute_tool(tc["name"], tc["input"])
                    all_tool_calls.append(tc)
                    all_tool_results.append({
                        "tool_name": tc["name"],
                        "input": tc["input"],
                        "result": result.to_content(),
                        "success": result.success,
                    })
                    tool_result_content.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": result.to_content(),
                    })

                self.conversation.append({"role": "user", "content": tool_result_content})
            else:
                # Done - add final response
                self.conversation.append({"role": "assistant", "content": text})
                return AgentResponse(
                    content=text,
                    tool_calls=all_tool_calls,
                    tool_results=all_tool_results,
                )

    async def query_stream(self, user_message: str) -> AsyncIterator[str]:
        """Send a query and stream the response."""
        # Add user message to conversation
        self.conversation.append({"role": "user", "content": user_message})

        # Loop for tool use
        while True:
            collected_text = ""
            tool_calls = []

            async for chunk, tc_list, is_done in self.llm_client.query_stream(
                messages=self.conversation,
                system_prompt=self.system_prompt,
                tools=self.get_tools(),
                max_tokens=self.config.max_tokens,
            ):
                if chunk:
                    collected_text += chunk
                    yield chunk
                if is_done:
                    tool_calls = tc_list

            if tool_calls:
                # Add assistant response with tool calls
                assistant_content = self._build_assistant_content(collected_text, tool_calls)
                self.conversation.append({"role": "assistant", "content": assistant_content})

                # Execute tools
                tool_result_content = []
                for tc in tool_calls:
                    yield f"\n[Calling {tc['name']}...]\n"
                    result = await self.backend.execute_tool(tc["name"], tc["input"])
                    tool_result_content.append({
                        "type": "tool_result",
                        "tool_use_id": tc["id"],
                        "content": result.to_content(),
                    })

                self.conversation.append({"role": "user", "content": tool_result_content})
            else:
                # Done
                if collected_text:
                    self.conversation.append({"role": "assistant", "content": collected_text})
                break
