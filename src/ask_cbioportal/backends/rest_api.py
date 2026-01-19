"""REST API backend for cBioPortal public API."""

import json
from typing import Any

import httpx

from ask_cbioportal.backends.base import Backend, BackendTool, ToolResult
from ask_cbioportal.config import Config


class RestApiBackend(Backend):
    """Backend that uses the cBioPortal public REST API."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.base_url = config.rest_api_base_url.rstrip("/")
        self._client: httpx.AsyncClient | None = None

    @property
    def name(self) -> str:
        return "REST API"

    @property
    def description(self) -> str:
        return f"cBioPortal REST API at {self.base_url}"

    async def initialize(self) -> None:
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=30.0,
            headers={"Accept": "application/json"},
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def get_tools(self) -> list[BackendTool]:
        """Return tools for interacting with cBioPortal REST API."""
        return [
            BackendTool(
                name="list_studies",
                description="List all cancer studies available in cBioPortal. Returns study IDs, names, descriptions, and basic metadata.",
                parameters={
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "Optional keyword to filter studies by name or description",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of studies to return (default: 100)",
                        },
                    },
                    "required": [],
                },
            ),
            BackendTool(
                name="get_study",
                description="Get detailed information about a specific cancer study.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID (e.g., 'brca_tcga', 'luad_tcga_pan_can_atlas_2018')",
                        },
                    },
                    "required": ["study_id"],
                },
            ),
            BackendTool(
                name="get_cancer_types",
                description="List all cancer types in cBioPortal with their names and descriptions.",
                parameters={
                    "properties": {},
                    "required": [],
                },
            ),
            BackendTool(
                name="get_genes",
                description="Search for genes by Hugo symbol or Entrez gene ID.",
                parameters={
                    "properties": {
                        "gene_symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of gene Hugo symbols (e.g., ['TP53', 'BRCA1', 'EGFR'])",
                        },
                    },
                    "required": ["gene_symbols"],
                },
            ),
            BackendTool(
                name="get_mutations_in_gene",
                description="Get mutations for a specific gene across studies or within a specific study.",
                parameters={
                    "properties": {
                        "gene_symbol": {
                            "type": "string",
                            "description": "Gene Hugo symbol (e.g., 'TP53', 'BRCA1')",
                        },
                        "study_id": {
                            "type": "string",
                            "description": "Optional: Limit to a specific study ID",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of mutations to return (default: 100)",
                        },
                    },
                    "required": ["gene_symbol"],
                },
            ),
            BackendTool(
                name="get_samples_in_study",
                description="Get all samples in a specific study with their clinical attributes.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of samples to return (default: 100)",
                        },
                    },
                    "required": ["study_id"],
                },
            ),
            BackendTool(
                name="get_clinical_data",
                description="Get clinical data for patients or samples in a study.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID",
                        },
                        "clinical_data_type": {
                            "type": "string",
                            "enum": ["PATIENT", "SAMPLE"],
                            "description": "Type of clinical data: PATIENT or SAMPLE",
                        },
                        "attribute_id": {
                            "type": "string",
                            "description": "Optional: Specific clinical attribute ID to fetch",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of records to return (default: 100)",
                        },
                    },
                    "required": ["study_id", "clinical_data_type"],
                },
            ),
            BackendTool(
                name="get_clinical_attributes",
                description="List available clinical attributes for a study.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID",
                        },
                    },
                    "required": ["study_id"],
                },
            ),
            BackendTool(
                name="get_molecular_profiles",
                description="List molecular profiles (e.g., mutations, CNA, mRNA) available in a study.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID",
                        },
                    },
                    "required": ["study_id"],
                },
            ),
            BackendTool(
                name="get_mutation_counts",
                description="Get mutation counts for specific genes in a study.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID",
                        },
                        "gene_symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of gene Hugo symbols",
                        },
                    },
                    "required": ["study_id", "gene_symbols"],
                },
            ),
            BackendTool(
                name="search_patients",
                description="Search for patients across studies.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID to search within",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of patients to return (default: 100)",
                        },
                    },
                    "required": ["study_id"],
                },
            ),
            BackendTool(
                name="get_cna_genes",
                description="Get copy number alteration data for genes in a study.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID",
                        },
                        "gene_symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of gene Hugo symbols",
                        },
                    },
                    "required": ["study_id", "gene_symbols"],
                },
            ),
        ]

    async def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute a REST API tool."""
        if not self._client:
            return ToolResult(success=False, error="Backend not initialized")

        try:
            method = getattr(self, f"_tool_{tool_name}", None)
            if method is None:
                return ToolResult(success=False, error=f"Unknown tool: {tool_name}")
            return await method(**arguments)
        except httpx.HTTPStatusError as e:
            return ToolResult(
                success=False,
                error=f"HTTP error {e.response.status_code}: {e.response.text[:500]}",
            )
        except httpx.RequestError as e:
            return ToolResult(success=False, error=f"Request error: {str(e)}")
        except Exception as e:
            return ToolResult(success=False, error=f"Error: {str(e)}")

    async def _tool_list_studies(
        self, keyword: str | None = None, limit: int = 100
    ) -> ToolResult:
        """List all studies, optionally filtered by keyword."""
        response = await self._client.get("/studies")
        response.raise_for_status()
        studies = response.json()

        if keyword:
            keyword_lower = keyword.lower()
            studies = [
                s
                for s in studies
                if keyword_lower in s.get("name", "").lower()
                or keyword_lower in s.get("description", "").lower()
                or keyword_lower in s.get("studyId", "").lower()
            ]

        # Sort by name and limit
        studies = sorted(studies, key=lambda s: s.get("name", ""))[:limit]

        # Format output
        result = []
        for study in studies:
            result.append(
                {
                    "study_id": study.get("studyId"),
                    "name": study.get("name"),
                    "description": study.get("description", "")[:200],
                    "cancer_type": study.get("cancerTypeId"),
                    "sample_count": study.get("allSampleCount", 0),
                }
            )

        return ToolResult(
            success=True,
            data={"total_count": len(result), "studies": result},
        )

    async def _tool_get_study(self, study_id: str) -> ToolResult:
        """Get details for a specific study."""
        response = await self._client.get(f"/studies/{study_id}")
        response.raise_for_status()
        return ToolResult(success=True, data=response.json())

    async def _tool_get_cancer_types(self) -> ToolResult:
        """List all cancer types."""
        response = await self._client.get("/cancer-types")
        response.raise_for_status()
        cancer_types = response.json()

        result = [
            {
                "id": ct.get("cancerTypeId"),
                "name": ct.get("name"),
                "clinical_trial_keywords": ct.get("dedicatedColor"),
            }
            for ct in cancer_types
        ]
        return ToolResult(success=True, data=result)

    async def _tool_get_genes(self, gene_symbols: list[str]) -> ToolResult:
        """Get information about specific genes."""
        # The API expects a POST with gene IDs and geneIdType parameter
        response = await self._client.post(
            "/genes/fetch",
            params={"geneIdType": "HUGO_GENE_SYMBOL"},
            json=gene_symbols,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        return ToolResult(success=True, data=response.json())

    async def _tool_get_mutations_in_gene(
        self,
        gene_symbol: str,
        study_id: str | None = None,
        limit: int = 100,
    ) -> ToolResult:
        """Get mutations for a gene."""
        # First, get the gene info to get entrezGeneId
        gene_response = await self._client.post(
            "/genes/fetch",
            params={"geneIdType": "HUGO_GENE_SYMBOL"},
            json=[gene_symbol],
            headers={"Content-Type": "application/json"},
        )
        gene_response.raise_for_status()
        genes = gene_response.json()

        if not genes:
            return ToolResult(success=False, error=f"Gene not found: {gene_symbol}")

        entrez_gene_id = genes[0].get("entrezGeneId")

        if study_id:
            # Get molecular profiles for the study
            profiles_response = await self._client.get(
                f"/studies/{study_id}/molecular-profiles"
            )
            profiles_response.raise_for_status()
            profiles = profiles_response.json()

            # Find mutation profile
            mutation_profile = next(
                (p for p in profiles if p.get("molecularAlterationType") == "MUTATION_EXTENDED"),
                None,
            )

            if not mutation_profile:
                return ToolResult(
                    success=False,
                    error=f"No mutation profile found in study {study_id}",
                )

            profile_id = mutation_profile.get("molecularProfileId")

            # Get mutations - requires sampleListId parameter
            response = await self._client.get(
                f"/molecular-profiles/{profile_id}/mutations",
                params={
                    "entrezGeneId": entrez_gene_id,
                    "sampleListId": f"{study_id}_all",
                },
            )
            response.raise_for_status()
            mutations = response.json()[:limit]
        else:
            # Search across all studies - use a different approach
            # Get mutations from the gene endpoint
            response = await self._client.get(f"/genes/{entrez_gene_id}")
            response.raise_for_status()
            mutations = [
                {
                    "gene": gene_symbol,
                    "info": response.json(),
                    "note": "For specific mutations, please specify a study_id",
                }
            ]

        return ToolResult(success=True, data=mutations)

    async def _tool_get_samples_in_study(
        self, study_id: str, limit: int = 100
    ) -> ToolResult:
        """Get samples in a study."""
        response = await self._client.get(f"/studies/{study_id}/samples")
        response.raise_for_status()
        samples = response.json()[:limit]

        result = [
            {
                "sample_id": s.get("sampleId"),
                "patient_id": s.get("patientId"),
                "sample_type": s.get("sampleType"),
            }
            for s in samples
        ]

        return ToolResult(
            success=True,
            data={"total_count": len(samples), "samples": result},
        )

    async def _tool_get_clinical_data(
        self,
        study_id: str,
        clinical_data_type: str,
        attribute_id: str | None = None,
        limit: int = 100,
    ) -> ToolResult:
        """Get clinical data for a study."""
        endpoint = f"/studies/{study_id}/clinical-data"
        params = {"clinicalDataType": clinical_data_type}

        if attribute_id:
            params["attributeId"] = attribute_id

        response = await self._client.get(endpoint, params=params)
        response.raise_for_status()
        data = response.json()[:limit]

        return ToolResult(success=True, data=data)

    async def _tool_get_clinical_attributes(self, study_id: str) -> ToolResult:
        """Get clinical attributes available in a study."""
        response = await self._client.get(f"/studies/{study_id}/clinical-attributes")
        response.raise_for_status()
        attributes = response.json()

        result = [
            {
                "attribute_id": attr.get("clinicalAttributeId"),
                "display_name": attr.get("displayName"),
                "description": attr.get("description"),
                "datatype": attr.get("datatype"),
                "patient_attribute": attr.get("patientAttribute"),
            }
            for attr in attributes
        ]

        return ToolResult(success=True, data=result)

    async def _tool_get_molecular_profiles(self, study_id: str) -> ToolResult:
        """Get molecular profiles in a study."""
        response = await self._client.get(f"/studies/{study_id}/molecular-profiles")
        response.raise_for_status()
        profiles = response.json()

        result = [
            {
                "profile_id": p.get("molecularProfileId"),
                "name": p.get("name"),
                "description": p.get("description"),
                "alteration_type": p.get("molecularAlterationType"),
                "datatype": p.get("datatype"),
            }
            for p in profiles
        ]

        return ToolResult(success=True, data=result)

    async def _tool_get_mutation_counts(
        self, study_id: str, gene_symbols: list[str]
    ) -> ToolResult:
        """Get mutation counts for genes in a study."""
        # Get molecular profiles
        profiles_response = await self._client.get(
            f"/studies/{study_id}/molecular-profiles"
        )
        profiles_response.raise_for_status()
        profiles = profiles_response.json()

        mutation_profile = next(
            (p for p in profiles if p.get("molecularAlterationType") == "MUTATION_EXTENDED"),
            None,
        )

        if not mutation_profile:
            return ToolResult(
                success=False,
                error=f"No mutation profile found in study {study_id}",
            )

        profile_id = mutation_profile.get("molecularProfileId")

        # Get gene info
        gene_response = await self._client.post(
            "/genes/fetch",
            params={"geneIdType": "HUGO_GENE_SYMBOL"},
            json=gene_symbols,
            headers={"Content-Type": "application/json"},
        )
        gene_response.raise_for_status()
        genes = gene_response.json()

        results = []
        for gene in genes:
            entrez_id = gene.get("entrezGeneId")
            symbol = gene.get("hugoGeneSymbol")

            mutations_response = await self._client.get(
                f"/molecular-profiles/{profile_id}/mutations",
                params={
                    "entrezGeneId": entrez_id,
                    "sampleListId": f"{study_id}_all",
                },
            )
            mutations_response.raise_for_status()
            mutations = mutations_response.json()

            results.append(
                {
                    "gene": symbol,
                    "entrez_gene_id": entrez_id,
                    "mutation_count": len(mutations),
                }
            )

        return ToolResult(success=True, data=results)

    async def _tool_search_patients(self, study_id: str, limit: int = 100) -> ToolResult:
        """Get patients in a study."""
        response = await self._client.get(f"/studies/{study_id}/patients")
        response.raise_for_status()
        patients = response.json()[:limit]

        result = [
            {
                "patient_id": p.get("patientId"),
                "study_id": p.get("studyId"),
            }
            for p in patients
        ]

        return ToolResult(
            success=True,
            data={"total_count": len(patients), "patients": result},
        )

    async def _tool_get_cna_genes(
        self, study_id: str, gene_symbols: list[str]
    ) -> ToolResult:
        """Get CNA data for genes in a study."""
        # Get molecular profiles
        profiles_response = await self._client.get(
            f"/studies/{study_id}/molecular-profiles"
        )
        profiles_response.raise_for_status()
        profiles = profiles_response.json()

        cna_profile = next(
            (
                p
                for p in profiles
                if p.get("molecularAlterationType") == "COPY_NUMBER_ALTERATION"
            ),
            None,
        )

        if not cna_profile:
            return ToolResult(
                success=False,
                error=f"No CNA profile found in study {study_id}",
            )

        profile_id = cna_profile.get("molecularProfileId")

        # Get gene info
        gene_response = await self._client.post(
            "/genes/fetch",
            params={"geneIdType": "HUGO_GENE_SYMBOL"},
            json=gene_symbols,
            headers={"Content-Type": "application/json"},
        )
        gene_response.raise_for_status()
        genes = gene_response.json()

        entrez_ids = [g.get("entrezGeneId") for g in genes]

        # Fetch discrete CNA data
        response = await self._client.post(
            f"/molecular-profiles/{profile_id}/discrete-copy-number",
            params={"discreteCopyNumberEventType": "ALL"},
            json={"entrezGeneIds": entrez_ids, "sampleListId": f"{study_id}_all"},
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        return ToolResult(success=True, data=response.json())

    def get_system_prompt_addition(self) -> str:
        """Return additional context for the REST API backend."""
        return """
You are using the cBioPortal REST API backend. Key information:

- Study IDs follow patterns like: brca_tcga, luad_tcga_pan_can_atlas_2018, msk_impact_2017
- Gene symbols should be HUGO symbols (e.g., TP53, BRCA1, EGFR, KRAS)
- Clinical data types are PATIENT (patient-level) or SAMPLE (sample-level)
- Common cancer types: breast (brca), lung (luad/lusc), colorectal (coadread), prostate (prad)
- TCGA studies often have "_tcga" suffix, MSK-IMPACT has "_msk" suffix

When answering questions:
1. Start by listing available studies if the user hasn't specified one
2. Use appropriate molecular profiles for the data type requested
3. Provide counts and summaries where helpful
4. Explain any limitations in the data returned
"""
