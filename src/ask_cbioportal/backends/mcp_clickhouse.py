"""MCP ClickHouse backend for cBioPortal."""

import asyncio
import json
import shlex
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ask_cbioportal.backends.base import Backend, BackendTool, ToolResult
from ask_cbioportal.config import Config


class McpClickHouseBackend(Backend):
    """Backend that uses cbioportal-mcp server for ClickHouse access."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self._session: ClientSession | None = None
        self._client_context: Any = None
        self._tools: list[BackendTool] = []

    @property
    def name(self) -> str:
        return "MCP ClickHouse"

    @property
    def description(self) -> str:
        return f"cBioPortal MCP server (ClickHouse at {self.config.clickhouse_host})"

    async def initialize(self) -> None:
        """Initialize the MCP client connection."""
        if not self.config.mcp_server_command:
            raise ValueError("MCP_SERVER_COMMAND is required for MCP backend")

        # Parse the command
        parts = shlex.split(self.config.mcp_server_command)
        command = parts[0]
        args = parts[1:] if len(parts) > 1 else []

        # Set up environment for ClickHouse connection
        env = {
            "CLICKHOUSE_HOST": self.config.clickhouse_host,
            "CLICKHOUSE_PORT": str(self.config.clickhouse_port),
            "CLICKHOUSE_USER": self.config.clickhouse_user,
            "CLICKHOUSE_PASSWORD": self.config.clickhouse_password,
            "CLICKHOUSE_DATABASE": self.config.clickhouse_database,
        }

        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env,
        )

        # Create the client context
        self._client_context = stdio_client(server_params)
        read, write = await self._client_context.__aenter__()

        # Create session
        self._session = ClientSession(read, write)
        await self._session.__aenter__()

        # Initialize the session
        await self._session.initialize()

        # Fetch available tools
        await self._refresh_tools()

    async def _refresh_tools(self) -> None:
        """Refresh the list of available tools from the MCP server."""
        if not self._session:
            return

        tools_result = await self._session.list_tools()
        self._tools = []

        for tool in tools_result.tools:
            # Convert MCP tool schema to our format
            input_schema = tool.inputSchema if hasattr(tool, "inputSchema") else {}
            if isinstance(input_schema, dict):
                properties = input_schema.get("properties", {})
                required = input_schema.get("required", [])
            else:
                properties = {}
                required = []

            self._tools.append(
                BackendTool(
                    name=tool.name,
                    description=tool.description or "",
                    parameters={
                        "properties": properties,
                        "required": required,
                    },
                )
            )

    async def close(self) -> None:
        """Close the MCP client connection."""
        if self._session:
            await self._session.__aexit__(None, None, None)
            self._session = None

        if self._client_context:
            await self._client_context.__aexit__(None, None, None)
            self._client_context = None

    def get_tools(self) -> list[BackendTool]:
        """Return tools available from the MCP server."""
        # If no tools from MCP yet, return default ClickHouse tools
        if not self._tools:
            return self._get_default_tools()
        return self._tools

    def _get_default_tools(self) -> list[BackendTool]:
        """Return default ClickHouse tools if MCP server hasn't been initialized."""
        return [
            BackendTool(
                name="clickhouse_run_select_query",
                description="Execute a SELECT query against the ClickHouse database containing cBioPortal data.",
                parameters={
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The SELECT SQL query to execute",
                        },
                    },
                    "required": ["query"],
                },
            ),
            BackendTool(
                name="clickhouse_list_tables",
                description="List all tables in the cBioPortal ClickHouse database.",
                parameters={
                    "properties": {},
                    "required": [],
                },
            ),
            BackendTool(
                name="clickhouse_list_table_columns",
                description="List columns for a specific table in the ClickHouse database.",
                parameters={
                    "properties": {
                        "table_name": {
                            "type": "string",
                            "description": "Name of the table to describe",
                        },
                    },
                    "required": ["table_name"],
                },
            ),
        ]

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a tool via the MCP server."""
        if not self._session:
            return ToolResult(success=False, error="MCP session not initialized")

        try:
            result = await self._session.call_tool(tool_name, arguments)

            # Extract content from the result
            if hasattr(result, "content") and result.content:
                content_parts = []
                for item in result.content:
                    if hasattr(item, "text"):
                        content_parts.append(item.text)
                    elif hasattr(item, "data"):
                        content_parts.append(str(item.data))
                    else:
                        content_parts.append(str(item))

                data = "\n".join(content_parts)

                # Try to parse as JSON
                try:
                    data = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    pass

                return ToolResult(success=True, data=data)
            else:
                return ToolResult(success=True, data="Query executed successfully")

        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def get_system_prompt_addition(self) -> str:
        """Return additional context for the ClickHouse backend."""
        return """
You are using the cBioPortal MCP backend with direct ClickHouse database access.

Key tables in the cBioPortal ClickHouse schema:
- cancer_study: Study metadata (cancer_study_identifier, name, description)
- patient: Patient information linked to studies
- sample: Sample data linked to patients
- mutation: Mutation data with gene info
- clinical_patient: Patient-level clinical attributes
- clinical_sample: Sample-level clinical attributes
- gene: Gene reference data (hugo_gene_symbol, entrez_gene_id)
- copy_number_seg: Copy number segment data
- structural_variant: Structural variant data

Common query patterns:
- Use cancer_study_identifier to join across tables
- Gene symbols are in hugo_gene_symbol column
- Clinical attributes are stored as key-value pairs

When writing queries:
1. Always use SELECT queries (no modifications)
2. Include LIMIT clauses for large result sets
3. Use appropriate JOINs between tables
4. Filter by study when possible for performance

Example queries:
- Count studies: SELECT count(*) FROM cancer_study
- List mutations in a gene: SELECT * FROM mutation WHERE hugo_gene_symbol = 'TP53' LIMIT 100
- Get study sample counts: SELECT cancer_study_identifier, count(*) FROM sample GROUP BY cancer_study_identifier
"""
