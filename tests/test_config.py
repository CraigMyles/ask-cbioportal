"""Tests for configuration management."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ask_cbioportal.config import BackendType, Config, ConfigFile


class TestConfig:
    """Tests for Config class."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = Config()

        assert config.backend == BackendType.REST
        assert config.rest_api_base_url == "https://www.cbioportal.org/api"
        assert config.claude_model == "claude-sonnet-4-20250514"
        assert config.max_tokens == 4096
        assert config.streaming is True

    def test_from_env(self) -> None:
        """Test loading config from environment variables."""
        env_vars = {
            "ANTHROPIC_API_KEY": "test-key",
            "ASK_CBIOPORTAL_BACKEND": "mcp",
            "CBIOPORTAL_API_URL": "https://custom.api/",
            "CLAUDE_MODEL": "claude-opus-4-20250514",
            "MAX_TOKENS": "8192",
            "STREAMING": "false",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            config = Config.from_env()

        assert config.anthropic_api_key == "test-key"
        assert config.backend == BackendType.MCP
        assert config.rest_api_base_url == "https://custom.api/"
        assert config.claude_model == "claude-opus-4-20250514"
        assert config.max_tokens == 8192
        assert config.streaming is False

    def test_validate_missing_api_key(self) -> None:
        """Test validation with missing API key."""
        config = Config(anthropic_api_key=None)
        errors = config.validate()

        assert len(errors) == 1
        assert "ANTHROPIC_API_KEY" in errors[0]

    def test_validate_mcp_missing_command(self) -> None:
        """Test validation with MCP backend but no command."""
        config = Config(
            anthropic_api_key="test-key",
            backend=BackendType.MCP,
            mcp_server_command=None,
        )
        errors = config.validate()

        assert len(errors) == 1
        assert "MCP_SERVER_COMMAND" in errors[0]

    def test_validate_success(self) -> None:
        """Test successful validation."""
        config = Config(
            anthropic_api_key="test-key",
            backend=BackendType.REST,
        )
        errors = config.validate()

        assert len(errors) == 0


class TestConfigFile:
    """Tests for ConfigFile class."""

    def test_default_path(self) -> None:
        """Test default config file path."""
        config_file = ConfigFile()
        expected = Path.home() / ".config" / "ask-cbioportal" / "config.env"
        assert config_file.config_file == expected

    def test_save_backend(self, tmp_path: Path) -> None:
        """Test saving backend preference."""
        config_file = ConfigFile(config_dir=tmp_path)
        config_file.save_backend(BackendType.MCP)

        content = config_file.config_file.read_text()
        assert "ASK_CBIOPORTAL_BACKEND=mcp" in content

    def test_save_backend_preserves_existing(self, tmp_path: Path) -> None:
        """Test that saving backend preserves other settings."""
        config_file = ConfigFile(config_dir=tmp_path)
        config_file.ensure_dir()

        # Write some existing config
        config_file.config_file.write_text("OTHER_SETTING=value\n")

        config_file.save_backend(BackendType.REST)

        content = config_file.config_file.read_text()
        assert "OTHER_SETTING=value" in content
        assert "ASK_CBIOPORTAL_BACKEND=rest" in content
