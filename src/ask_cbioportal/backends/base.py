"""Abstract base class for cBioPortal data backends."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Result from executing a backend tool."""

    success: bool
    data: Any = None
    error: str | None = None

    def to_content(self) -> str:
        """Convert result to string content for Claude."""
        if self.success:
            if isinstance(self.data, str):
                return self.data
            elif isinstance(self.data, (list, dict)):
                import json

                return json.dumps(self.data, indent=2, default=str)
            else:
                return str(self.data)
        else:
            return f"Error: {self.error}"


@dataclass
class BackendTool:
    """Definition of a tool provided by a backend."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_anthropic_tool(self) -> dict[str, Any]:
        """Convert to Anthropic tool format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters.get("properties", {}),
                "required": self.parameters.get("required", []),
            },
        }


class Backend(ABC):
    """Abstract base class for data backends."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the backend name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return a description of the backend."""
        pass

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the backend connection."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the backend connection."""
        pass

    @abstractmethod
    def get_tools(self) -> list[BackendTool]:
        """Return list of tools provided by this backend."""
        pass

    @abstractmethod
    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool with the given arguments."""
        pass

    def get_system_prompt_addition(self) -> str:
        """Return additional system prompt content for this backend."""
        return ""

    async def __aenter__(self) -> "Backend":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()
