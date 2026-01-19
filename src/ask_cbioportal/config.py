"""Configuration management for ask-cbioportal."""

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class BackendType(str, Enum):
    """Available backend types for data access."""

    REST = "rest"
    MCP = "mcp"


class LLMProvider(str, Enum):
    """Available LLM providers."""

    ANTHROPIC = "anthropic"
    LITELLM = "litellm"  # OpenAI-compatible API (LiteLLM, Ollama, vLLM, etc.)


@dataclass
class Config:
    """Application configuration."""

    # Data backend settings (where to get cBioPortal data)
    backend: BackendType = BackendType.REST

    # REST API settings
    rest_api_base_url: str = "https://www.cbioportal.org/api"

    # MCP/ClickHouse settings
    mcp_server_command: Optional[str] = None
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "cbioportal"

    # LLM Provider settings
    llm_provider: LLMProvider = LLMProvider.ANTHROPIC

    # Anthropic API settings (when llm_provider=anthropic)
    anthropic_api_key: Optional[str] = None

    # LiteLLM/OpenAI-compatible API settings (when llm_provider=litellm)
    litellm_api_base: str = "http://localhost:4000"  # LiteLLM server URL
    litellm_api_key: Optional[str] = None

    # Model settings (used by both providers)
    model: str = "claude-sonnet-4-20250514"  # Model name (provider-specific)
    max_tokens: int = 4096

    # CLI settings
    verbose: bool = False
    streaming: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        load_dotenv()

        backend_str = os.getenv("ASK_CBIOPORTAL_BACKEND", "rest").lower()
        try:
            backend = BackendType(backend_str)
        except ValueError:
            backend = BackendType.REST

        llm_provider_str = os.getenv("LLM_PROVIDER", "anthropic").lower()
        try:
            llm_provider = LLMProvider(llm_provider_str)
        except ValueError:
            llm_provider = LLMProvider.ANTHROPIC

        # Default model depends on provider
        default_model = (
            "claude-sonnet-4-20250514"
            if llm_provider == LLMProvider.ANTHROPIC
            else "gpt-4"  # Common default for LiteLLM
        )

        return cls(
            backend=backend,
            rest_api_base_url=os.getenv(
                "CBIOPORTAL_API_URL", "https://www.cbioportal.org/api"
            ),
            mcp_server_command=os.getenv("MCP_SERVER_COMMAND"),
            clickhouse_host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            clickhouse_port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            clickhouse_user=os.getenv("CLICKHOUSE_USER", "default"),
            clickhouse_password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            clickhouse_database=os.getenv("CLICKHOUSE_DATABASE", "cbioportal"),
            llm_provider=llm_provider,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            litellm_api_base=os.getenv("LITELLM_API_BASE", "http://localhost:4000"),
            litellm_api_key=os.getenv("LITELLM_API_KEY"),
            model=os.getenv("MODEL", default_model),
            max_tokens=int(os.getenv("MAX_TOKENS", "4096")),
            verbose=os.getenv("VERBOSE", "false").lower() == "true",
            streaming=os.getenv("STREAMING", "true").lower() == "true",
        )

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if self.llm_provider == LLMProvider.ANTHROPIC:
            if not self.anthropic_api_key:
                errors.append("ANTHROPIC_API_KEY is required when using Anthropic provider")
        elif self.llm_provider == LLMProvider.LITELLM:
            if not self.litellm_api_base:
                errors.append("LITELLM_API_BASE is required when using LiteLLM provider")
            # API key may be optional for some LiteLLM setups

        if self.backend == BackendType.MCP:
            if not self.mcp_server_command:
                errors.append(
                    "MCP_SERVER_COMMAND is required when using MCP backend"
                )

        return errors


@dataclass
class ConfigFile:
    """Configuration file management."""

    config_dir: Path = field(default_factory=lambda: Path.home() / ".config" / "ask-cbioportal")
    config_file: Path = field(init=False)

    def __post_init__(self) -> None:
        self.config_file = self.config_dir / "config.env"

    def ensure_dir(self) -> None:
        """Ensure config directory exists."""
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def save_backend(self, backend: BackendType) -> None:
        """Save backend preference to config file."""
        self.ensure_dir()

        # Read existing config
        existing = {}
        if self.config_file.exists():
            for line in self.config_file.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    existing[key.strip()] = value.strip()

        existing["ASK_CBIOPORTAL_BACKEND"] = backend.value

        # Write back
        with self.config_file.open("w") as f:
            for key, value in existing.items():
                f.write(f"{key}={value}\n")

    def load(self) -> None:
        """Load config file into environment."""
        if self.config_file.exists():
            load_dotenv(self.config_file)


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global config instance."""
    global _config
    if _config is None:
        config_file = ConfigFile()
        config_file.load()
        _config = Config.from_env()
    return _config


def reset_config() -> None:
    """Reset the global config instance."""
    global _config
    _config = None
