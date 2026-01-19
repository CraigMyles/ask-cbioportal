"""Tests for backend implementations."""

import pytest
from pytest_httpx import HTTPXMock

from ask_cbioportal.backends.base import BackendTool, ToolResult
from ask_cbioportal.backends.rest_api import RestApiBackend
from ask_cbioportal.config import Config


class TestToolResult:
    """Tests for ToolResult class."""

    def test_success_with_string(self) -> None:
        """Test success result with string data."""
        result = ToolResult(success=True, data="test data")
        assert result.to_content() == "test data"

    def test_success_with_dict(self) -> None:
        """Test success result with dict data."""
        result = ToolResult(success=True, data={"key": "value"})
        content = result.to_content()
        assert '"key": "value"' in content

    def test_success_with_list(self) -> None:
        """Test success result with list data."""
        result = ToolResult(success=True, data=[1, 2, 3])
        content = result.to_content()
        assert "1" in content
        assert "2" in content
        assert "3" in content

    def test_error_result(self) -> None:
        """Test error result."""
        result = ToolResult(success=False, error="Something went wrong")
        assert result.to_content() == "Error: Something went wrong"


class TestBackendTool:
    """Tests for BackendTool class."""

    def test_to_anthropic_tool(self) -> None:
        """Test conversion to Anthropic tool format."""
        tool = BackendTool(
            name="test_tool",
            description="A test tool",
            parameters={
                "properties": {
                    "arg1": {"type": "string", "description": "First arg"},
                },
                "required": ["arg1"],
            },
        )

        anthropic_tool = tool.to_anthropic_tool()

        assert anthropic_tool["name"] == "test_tool"
        assert anthropic_tool["description"] == "A test tool"
        assert anthropic_tool["input_schema"]["type"] == "object"
        assert "arg1" in anthropic_tool["input_schema"]["properties"]
        assert anthropic_tool["input_schema"]["required"] == ["arg1"]


class TestRestApiBackend:
    """Tests for REST API backend."""

    @pytest.fixture
    def config(self) -> Config:
        """Create test config."""
        return Config(
            anthropic_api_key="test-key",
            rest_api_base_url="https://www.cbioportal.org/api",
        )

    @pytest.fixture
    def backend(self, config: Config) -> RestApiBackend:
        """Create test backend."""
        return RestApiBackend(config)

    def test_name_and_description(self, backend: RestApiBackend) -> None:
        """Test backend name and description."""
        assert backend.name == "REST API"
        assert "cbioportal.org" in backend.description

    def test_get_tools(self, backend: RestApiBackend) -> None:
        """Test that backend provides tools."""
        tools = backend.get_tools()

        assert len(tools) > 0
        tool_names = [t.name for t in tools]
        assert "list_studies" in tool_names
        assert "get_study" in tool_names
        assert "get_genes" in tool_names

    @pytest.mark.asyncio
    async def test_list_studies(
        self, backend: RestApiBackend, httpx_mock: HTTPXMock
    ) -> None:
        """Test list_studies tool."""
        httpx_mock.add_response(
            url="https://www.cbioportal.org/api/studies",
            json=[
                {
                    "studyId": "brca_tcga",
                    "name": "Breast Cancer (TCGA)",
                    "description": "TCGA breast cancer study",
                    "cancerTypeId": "brca",
                    "allSampleCount": 1000,
                },
                {
                    "studyId": "luad_tcga",
                    "name": "Lung Adenocarcinoma (TCGA)",
                    "description": "TCGA lung cancer study",
                    "cancerTypeId": "luad",
                    "allSampleCount": 500,
                },
            ],
        )

        async with backend:
            result = await backend.execute_tool("list_studies", {})

        assert result.success
        assert result.data["total_count"] == 2
        assert len(result.data["studies"]) == 2
        assert result.data["studies"][0]["study_id"] == "brca_tcga"

    @pytest.mark.asyncio
    async def test_list_studies_with_keyword(
        self, backend: RestApiBackend, httpx_mock: HTTPXMock
    ) -> None:
        """Test list_studies with keyword filter."""
        httpx_mock.add_response(
            url="https://www.cbioportal.org/api/studies",
            json=[
                {
                    "studyId": "brca_tcga",
                    "name": "Breast Cancer (TCGA)",
                    "description": "Breast cancer study",
                    "cancerTypeId": "brca",
                    "allSampleCount": 1000,
                },
                {
                    "studyId": "luad_tcga",
                    "name": "Lung Adenocarcinoma (TCGA)",
                    "description": "Lung cancer study",
                    "cancerTypeId": "luad",
                    "allSampleCount": 500,
                },
            ],
        )

        async with backend:
            result = await backend.execute_tool(
                "list_studies", {"keyword": "breast"}
            )

        assert result.success
        assert result.data["total_count"] == 1
        assert result.data["studies"][0]["study_id"] == "brca_tcga"

    @pytest.mark.asyncio
    async def test_get_study(
        self, backend: RestApiBackend, httpx_mock: HTTPXMock
    ) -> None:
        """Test get_study tool."""
        httpx_mock.add_response(
            url="https://www.cbioportal.org/api/studies/brca_tcga",
            json={
                "studyId": "brca_tcga",
                "name": "Breast Cancer (TCGA)",
                "description": "TCGA breast cancer study",
                "cancerTypeId": "brca",
                "allSampleCount": 1000,
            },
        )

        async with backend:
            result = await backend.execute_tool(
                "get_study", {"study_id": "brca_tcga"}
            )

        assert result.success
        assert result.data["studyId"] == "brca_tcga"

    @pytest.mark.asyncio
    async def test_get_genes(
        self, backend: RestApiBackend, httpx_mock: HTTPXMock
    ) -> None:
        """Test get_genes tool."""
        httpx_mock.add_response(
            url="https://www.cbioportal.org/api/genes/fetch",
            json=[
                {
                    "entrezGeneId": 7157,
                    "hugoGeneSymbol": "TP53",
                    "type": "protein-coding",
                },
                {
                    "entrezGeneId": 672,
                    "hugoGeneSymbol": "BRCA1",
                    "type": "protein-coding",
                },
            ],
        )

        async with backend:
            result = await backend.execute_tool(
                "get_genes", {"gene_symbols": ["TP53", "BRCA1"]}
            )

        assert result.success
        assert len(result.data) == 2
        assert result.data[0]["hugoGeneSymbol"] == "TP53"

    @pytest.mark.asyncio
    async def test_unknown_tool(self, backend: RestApiBackend) -> None:
        """Test calling an unknown tool."""
        async with backend:
            result = await backend.execute_tool("nonexistent_tool", {})

        assert not result.success
        assert "Unknown tool" in result.error

    @pytest.mark.asyncio
    async def test_http_error(
        self, backend: RestApiBackend, httpx_mock: HTTPXMock
    ) -> None:
        """Test handling HTTP errors."""
        httpx_mock.add_response(
            url="https://www.cbioportal.org/api/studies/invalid_study",
            status_code=404,
            text="Study not found",
        )

        async with backend:
            result = await backend.execute_tool(
                "get_study", {"study_id": "invalid_study"}
            )

        assert not result.success
        assert "404" in result.error

    def test_system_prompt_addition(self, backend: RestApiBackend) -> None:
        """Test that backend provides system prompt addition."""
        addition = backend.get_system_prompt_addition()

        assert len(addition) > 0
        assert "cBioPortal" in addition
        assert "REST API" in addition
