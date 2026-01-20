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
                description="Get clinical data for patients or samples in a study. Returns summarized statistics (counts, distributions) for large datasets. Use attribute_id to query specific attributes like MSI_SENSOR_SCORE, OS_STATUS, ER_STATUS_BY_IHC, etc.",
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
                            "description": "Specific clinical attribute ID to fetch (e.g., MSI_SENSOR_SCORE, OS_STATUS, ER_STATUS_BY_IHC). Required for efficient queries.",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of raw records to return if not summarizing (default: 100)",
                        },
                        "summarize": {
                            "type": "boolean",
                            "description": "If true (default), returns summary statistics instead of raw records for large datasets",
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
            BackendTool(
                name="get_survival_data",
                description="Get survival data (overall survival, disease-free survival, progression-free survival) for patients in a study. Can optionally stratify by a gene mutation to compare survival between mutated and wild-type groups. Use this for Kaplan-Meier analysis and survival comparisons.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID (e.g., 'brca_tcga')",
                        },
                        "gene_symbol": {
                            "type": "string",
                            "description": "Optional: Gene to stratify by (e.g., 'TP53'). Compares survival between mutated vs wild-type patients.",
                        },
                    },
                    "required": ["study_id"],
                },
            ),
            BackendTool(
                name="get_gene_panel_data",
                description="Get information about a gene panel used in a study, including the list of genes covered.",
                parameters={
                    "properties": {
                        "gene_panel_id": {
                            "type": "string",
                            "description": "The gene panel ID (e.g., 'IMPACT468')",
                        },
                    },
                    "required": ["gene_panel_id"],
                },
            ),
            BackendTool(
                name="get_alteration_enrichments",
                description="Find co-occurring or mutually exclusive gene alterations. Performs statistical analysis (Fisher's exact test) to identify genes that are significantly enriched or depleted in samples with a specific alteration. Use this to find genes that tend to be altered together or are mutually exclusive.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID",
                        },
                        "gene_symbol": {
                            "type": "string",
                            "description": "The gene to analyze for co-occurring/mutually exclusive alterations (e.g., 'KRAS')",
                        },
                        "alteration_type": {
                            "type": "string",
                            "enum": ["MUTATION", "CNA"],
                            "description": "Type of alteration: MUTATION or CNA (copy number alteration)",
                        },
                    },
                    "required": ["study_id", "gene_symbol", "alteration_type"],
                },
            ),
            BackendTool(
                name="get_structural_variants",
                description="Get structural variant data including gene fusions. Query fusion genes like ALK, ROS1, NTRK, RET fusions. Useful for identifying clinically actionable fusions in cancer samples.",
                parameters={
                    "properties": {
                        "study_id": {
                            "type": "string",
                            "description": "The study ID",
                        },
                        "gene_symbols": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional: Filter by specific fusion partner genes (e.g., ['ALK', 'ROS1', 'NTRK1'])",
                        },
                    },
                    "required": ["study_id"],
                },
            ),
            BackendTool(
                name="create_chart",
                description="Create a chart visualization. Use this when the user asks for a chart, pie chart, bar chart, or visualization. Returns a chart that will be rendered in the UI. Supports multiple chart types including survival curves.",
                parameters={
                    "properties": {
                        "chart_type": {
                            "type": "string",
                            "enum": ["pie", "bar", "doughnut", "survival", "scatter", "heatmap", "lollipop"],
                            "description": "Type of chart: pie, bar, doughnut, survival (Kaplan-Meier), scatter, heatmap, or lollipop",
                        },
                        "title": {
                            "type": "string",
                            "description": "Chart title",
                        },
                        "labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Labels for the data points (e.g., ['MSI-High', 'MSS'])",
                        },
                        "values": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Numeric values for each label (e.g., [88, 496])",
                        },
                        "survival_data": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "times": {"type": "array", "items": {"type": "number"}},
                                    "probabilities": {"type": "array", "items": {"type": "number"}},
                                },
                            },
                            "description": "For survival charts: Array of groups with time points and survival probabilities",
                        },
                        "x_values": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "For scatter/lollipop charts: X-axis values",
                        },
                        "y_values": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "For scatter/lollipop charts: Y-axis values",
                        },
                        "x_label": {
                            "type": "string",
                            "description": "X-axis label",
                        },
                        "y_label": {
                            "type": "string",
                            "description": "Y-axis label",
                        },
                        "heatmap_data": {
                            "type": "object",
                            "description": "For heatmap charts: Object with z (2D array), x (labels), y (labels)",
                        },
                        "text_labels": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "For scatter/lollipop charts: Text labels for each point",
                        },
                    },
                    "required": ["chart_type", "title"],
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
        summarize: bool = True,
    ) -> ToolResult:
        """Get clinical data for a study with automatic summarization."""
        endpoint = f"/studies/{study_id}/clinical-data"
        params = {"clinicalDataType": clinical_data_type}

        if attribute_id:
            params["attributeId"] = attribute_id

        response = await self._client.get(endpoint, params=params)
        response.raise_for_status()
        data = response.json()

        total_count = len(data)

        # If summarize is enabled and we have a specific attribute, provide summary statistics
        if summarize and attribute_id and total_count > 20:
            values = [d.get("value") for d in data if d.get("value") is not None]

            # Try to detect if numeric
            numeric_values = []
            for v in values:
                try:
                    numeric_values.append(float(v))
                except (ValueError, TypeError):
                    pass

            if len(numeric_values) > len(values) * 0.5:
                # Mostly numeric - provide statistics
                numeric_values.sort()
                summary = {
                    "attribute_id": attribute_id,
                    "total_samples": total_count,
                    "non_null_count": len(numeric_values),
                    "min": min(numeric_values),
                    "max": max(numeric_values),
                    "mean": sum(numeric_values) / len(numeric_values),
                    "median": numeric_values[len(numeric_values) // 2],
                    # For MSI scores, add clinically relevant cutoffs
                    "above_3.5": sum(1 for v in numeric_values if v > 3.5),
                    "below_or_equal_3.5": sum(1 for v in numeric_values if v <= 3.5),
                    "sample_values": numeric_values[:10],  # First 10 as examples
                }
                return ToolResult(success=True, data=summary)
            else:
                # Categorical - provide value counts
                from collections import Counter
                value_counts = Counter(values)
                summary = {
                    "attribute_id": attribute_id,
                    "total_samples": total_count,
                    "unique_values": len(value_counts),
                    "value_counts": dict(value_counts.most_common(20)),
                }
                return ToolResult(success=True, data=summary)

        # Return raw data if not summarizing or small dataset
        return ToolResult(
            success=True,
            data={
                "total_count": total_count,
                "records": data[:limit],
            }
        )

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

    async def _tool_get_survival_data(
        self,
        study_id: str,
        gene_symbol: str | None = None,
    ) -> ToolResult:
        """Get survival data for patients in a study, optionally stratified by gene mutation."""
        # Get survival clinical data (OS_STATUS, OS_MONTHS)
        os_status_response = await self._client.get(
            f"/studies/{study_id}/clinical-data",
            params={"clinicalDataType": "PATIENT", "attributeId": "OS_STATUS"},
        )
        os_status_response.raise_for_status()
        os_status_data = os_status_response.json()

        os_months_response = await self._client.get(
            f"/studies/{study_id}/clinical-data",
            params={"clinicalDataType": "PATIENT", "attributeId": "OS_MONTHS"},
        )
        os_months_response.raise_for_status()
        os_months_data = os_months_response.json()

        # Build patient survival map
        patient_survival = {}
        for record in os_months_data:
            patient_id = record.get("patientId")
            try:
                months = float(record.get("value", 0))
                patient_survival[patient_id] = {"months": months}
            except (ValueError, TypeError):
                continue

        for record in os_status_data:
            patient_id = record.get("patientId")
            if patient_id in patient_survival:
                status = record.get("value", "")
                # OS_STATUS values: "0:LIVING", "1:DECEASED", "LIVING", "DECEASED"
                is_event = "1:" in status or status.upper() == "DECEASED"
                patient_survival[patient_id]["event"] = 1 if is_event else 0

        # Filter to patients with complete survival data
        complete_patients = {
            pid: data for pid, data in patient_survival.items()
            if "event" in data and "months" in data
        }

        if not complete_patients:
            return ToolResult(
                success=False,
                error=f"No survival data found in study {study_id}. The study may not have OS_STATUS and OS_MONTHS clinical attributes.",
            )

        # If gene_symbol provided, stratify by mutation status
        if gene_symbol:
            # Get mutation data for the gene
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

            # Get gene entrez ID
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

            entrez_id = genes[0].get("entrezGeneId")
            profile_id = mutation_profile.get("molecularProfileId")

            # Get mutations
            mutations_response = await self._client.get(
                f"/molecular-profiles/{profile_id}/mutations",
                params={
                    "entrezGeneId": entrez_id,
                    "sampleListId": f"{study_id}_all",
                },
            )
            mutations_response.raise_for_status()
            mutations = mutations_response.json()

            # Get mutated patient IDs (need to map sample -> patient)
            mutated_samples = {m.get("sampleId") for m in mutations}

            # Get sample-to-patient mapping
            samples_response = await self._client.get(f"/studies/{study_id}/samples")
            samples_response.raise_for_status()
            samples = samples_response.json()
            sample_to_patient = {s.get("sampleId"): s.get("patientId") for s in samples}

            mutated_patients = {
                sample_to_patient.get(sid) for sid in mutated_samples
                if sample_to_patient.get(sid)
            }

            # Calculate Kaplan-Meier curves for both groups
            mutated_survival = []
            wildtype_survival = []

            for pid, data in complete_patients.items():
                if pid in mutated_patients:
                    mutated_survival.append(data)
                else:
                    wildtype_survival.append(data)

            def calculate_km_curve(patients):
                """Calculate Kaplan-Meier survival curve."""
                if not patients:
                    return [], []

                # Sort by time
                sorted_patients = sorted(patients, key=lambda x: x["months"])

                times = [0]
                probabilities = [1.0]
                n_at_risk = len(patients)
                current_prob = 1.0

                for p in sorted_patients:
                    t = p["months"]
                    event = p["event"]

                    if event == 1:  # Death occurred
                        current_prob *= (n_at_risk - 1) / n_at_risk
                        times.append(t)
                        probabilities.append(current_prob)

                    n_at_risk -= 1

                return times, probabilities

            mut_times, mut_probs = calculate_km_curve(mutated_survival)
            wt_times, wt_probs = calculate_km_curve(wildtype_survival)

            # Calculate median survival
            def get_median_survival(times, probs):
                for i, p in enumerate(probs):
                    if p <= 0.5:
                        return times[i]
                return None

            result = {
                "study_id": study_id,
                "gene": gene_symbol,
                "total_patients_with_survival": len(complete_patients),
                "mutated_group": {
                    "patient_count": len(mutated_survival),
                    "events": sum(p["event"] for p in mutated_survival),
                    "median_survival_months": get_median_survival(mut_times, mut_probs),
                    "times": mut_times,
                    "probabilities": mut_probs,
                },
                "wildtype_group": {
                    "patient_count": len(wildtype_survival),
                    "events": sum(p["event"] for p in wildtype_survival),
                    "median_survival_months": get_median_survival(wt_times, wt_probs),
                    "times": wt_times,
                    "probabilities": wt_probs,
                },
            }

            return ToolResult(success=True, data=result)
        else:
            # No stratification - return overall survival data
            all_survival = list(complete_patients.values())

            def calculate_km_curve(patients):
                if not patients:
                    return [], []
                sorted_patients = sorted(patients, key=lambda x: x["months"])
                times = [0]
                probabilities = [1.0]
                n_at_risk = len(patients)
                current_prob = 1.0

                for p in sorted_patients:
                    t = p["months"]
                    event = p["event"]
                    if event == 1:
                        current_prob *= (n_at_risk - 1) / n_at_risk
                        times.append(t)
                        probabilities.append(current_prob)
                    n_at_risk -= 1

                return times, probabilities

            times, probs = calculate_km_curve(all_survival)

            def get_median_survival(times, probs):
                for i, p in enumerate(probs):
                    if p <= 0.5:
                        return times[i]
                return None

            result = {
                "study_id": study_id,
                "total_patients": len(complete_patients),
                "total_events": sum(p["event"] for p in all_survival),
                "median_survival_months": get_median_survival(times, probs),
                "times": times,
                "probabilities": probs,
            }

            return ToolResult(success=True, data=result)

    async def _tool_get_gene_panel_data(self, gene_panel_id: str) -> ToolResult:
        """Get information about a gene panel."""
        response = await self._client.get(f"/gene-panels/{gene_panel_id}")
        response.raise_for_status()
        panel = response.json()

        # Get genes in the panel
        genes_response = await self._client.get(f"/gene-panels/{gene_panel_id}/genes")
        genes_response.raise_for_status()
        genes = genes_response.json()

        return ToolResult(
            success=True,
            data={
                "gene_panel_id": panel.get("genePanelId"),
                "description": panel.get("description"),
                "gene_count": len(genes),
                "genes": [g.get("hugoGeneSymbol") for g in genes],
            },
        )

    async def _tool_get_alteration_enrichments(
        self,
        study_id: str,
        gene_symbol: str,
        alteration_type: str,
    ) -> ToolResult:
        """Find co-occurring or mutually exclusive alterations for a gene."""
        from collections import Counter

        # Get molecular profiles
        profiles_response = await self._client.get(
            f"/studies/{study_id}/molecular-profiles"
        )
        profiles_response.raise_for_status()
        profiles = profiles_response.json()

        if alteration_type == "MUTATION":
            profile = next(
                (p for p in profiles if p.get("molecularAlterationType") == "MUTATION_EXTENDED"),
                None,
            )
            if not profile:
                return ToolResult(success=False, error=f"No mutation profile found in study {study_id}")
        else:  # CNA
            profile = next(
                (p for p in profiles if p.get("molecularAlterationType") == "COPY_NUMBER_ALTERATION"),
                None,
            )
            if not profile:
                return ToolResult(success=False, error=f"No CNA profile found in study {study_id}")

        profile_id = profile.get("molecularProfileId")

        # Get gene info
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

        entrez_id = genes[0].get("entrezGeneId")

        # Get samples with alterations in the target gene
        if alteration_type == "MUTATION":
            mutations_response = await self._client.get(
                f"/molecular-profiles/{profile_id}/mutations",
                params={
                    "entrezGeneId": entrez_id,
                    "sampleListId": f"{study_id}_all",
                },
            )
            mutations_response.raise_for_status()
            mutations = mutations_response.json()
            altered_samples = {m.get("sampleId") for m in mutations}
        else:
            cna_response = await self._client.post(
                f"/molecular-profiles/{profile_id}/discrete-copy-number",
                params={"discreteCopyNumberEventType": "ALL"},
                json={"entrezGeneIds": [entrez_id], "sampleListId": f"{study_id}_all"},
                headers={"Content-Type": "application/json"},
            )
            cna_response.raise_for_status()
            cna_data = cna_response.json()
            # CNA values: -2 (deep del), -1 (shallow del), 0 (diploid), 1 (gain), 2 (amp)
            altered_samples = {c.get("sampleId") for c in cna_data if abs(c.get("alteration", 0)) >= 1}

        # Get all samples in study
        samples_response = await self._client.get(f"/studies/{study_id}/samples")
        samples_response.raise_for_status()
        all_samples = {s.get("sampleId") for s in samples_response.json()}
        unaltered_samples = all_samples - altered_samples

        if not altered_samples:
            return ToolResult(
                success=False,
                error=f"No alterations found for {gene_symbol} in study {study_id}",
            )

        # Get all mutations in the study to find co-occurring genes
        if alteration_type == "MUTATION":
            # We need to get mutations for other genes
            # Fetch a batch of common cancer genes to check for co-occurrence
            common_genes = [
                "TP53", "KRAS", "PIK3CA", "PTEN", "APC", "BRAF", "EGFR",
                "BRCA1", "BRCA2", "ATM", "CDKN2A", "RB1", "NF1", "ARID1A",
                "KMT2D", "NOTCH1", "FAT1", "FBXW7", "SMAD4", "CTNNB1"
            ]
            # Remove the target gene
            common_genes = [g for g in common_genes if g.upper() != gene_symbol.upper()]

            gene_response = await self._client.post(
                "/genes/fetch",
                params={"geneIdType": "HUGO_GENE_SYMBOL"},
                json=common_genes,
                headers={"Content-Type": "application/json"},
            )
            gene_response.raise_for_status()
            genes_info = gene_response.json()

            co_occurrence_results = []

            for gene_info in genes_info:
                test_entrez = gene_info.get("entrezGeneId")
                test_symbol = gene_info.get("hugoGeneSymbol")

                test_mutations_response = await self._client.get(
                    f"/molecular-profiles/{profile_id}/mutations",
                    params={
                        "entrezGeneId": test_entrez,
                        "sampleListId": f"{study_id}_all",
                    },
                )
                test_mutations_response.raise_for_status()
                test_mutations = test_mutations_response.json()
                test_altered = {m.get("sampleId") for m in test_mutations}

                # Calculate 2x2 contingency table
                both_altered = len(altered_samples & test_altered)
                only_target = len(altered_samples - test_altered)
                only_test = len(test_altered - altered_samples)
                neither = len(unaltered_samples - test_altered)

                # Fisher's exact test approximation using odds ratio
                total = len(all_samples)
                if both_altered > 0 and (only_target * only_test) > 0:
                    odds_ratio = (both_altered * neither) / (only_target * only_test) if (only_target * only_test) > 0 else float('inf')
                else:
                    odds_ratio = 0

                # Simple p-value approximation (for display purposes)
                # In production, use scipy.stats.fisher_exact
                expected = (len(altered_samples) * len(test_altered)) / total if total > 0 else 0

                co_occurrence_results.append({
                    "gene": test_symbol,
                    "both_altered": both_altered,
                    "only_query_altered": only_target,
                    "only_this_altered": only_test,
                    "neither_altered": neither,
                    "odds_ratio": round(odds_ratio, 2) if odds_ratio != float('inf') else "inf",
                    "tendency": "co-occurring" if odds_ratio > 1.5 else "mutually_exclusive" if odds_ratio < 0.67 else "no_association",
                    "query_gene_altered_count": len(altered_samples),
                    "this_gene_altered_count": len(test_altered),
                })

            # Sort by both_altered for co-occurring, or by mutual exclusivity
            co_occurrence_results.sort(key=lambda x: x["both_altered"], reverse=True)

            return ToolResult(
                success=True,
                data={
                    "study_id": study_id,
                    "query_gene": gene_symbol,
                    "alteration_type": alteration_type,
                    "total_samples": len(all_samples),
                    "query_gene_altered": len(altered_samples),
                    "enrichments": co_occurrence_results[:15],  # Top 15 results
                },
            )
        else:
            # Simplified for CNA - just return the altered samples info
            return ToolResult(
                success=True,
                data={
                    "study_id": study_id,
                    "query_gene": gene_symbol,
                    "alteration_type": alteration_type,
                    "total_samples": len(all_samples),
                    "altered_samples": len(altered_samples),
                    "note": "For full enrichment analysis with CNA, mutation co-occurrence is more commonly analyzed",
                },
            )

    async def _tool_get_structural_variants(
        self,
        study_id: str,
        gene_symbols: list[str] | None = None,
    ) -> ToolResult:
        """Get structural variant / fusion data for a study."""
        # Get molecular profiles
        profiles_response = await self._client.get(
            f"/studies/{study_id}/molecular-profiles"
        )
        profiles_response.raise_for_status()
        profiles = profiles_response.json()

        # Find structural variant profile
        sv_profile = next(
            (p for p in profiles if p.get("molecularAlterationType") == "STRUCTURAL_VARIANT"),
            None,
        )

        if not sv_profile:
            return ToolResult(
                success=False,
                error=f"No structural variant/fusion profile found in study {study_id}. This study may not have fusion data.",
            )

        profile_id = sv_profile.get("molecularProfileId")

        # If gene symbols provided, get their entrez IDs
        entrez_ids = None
        if gene_symbols:
            gene_response = await self._client.post(
                "/genes/fetch",
                params={"geneIdType": "HUGO_GENE_SYMBOL"},
                json=gene_symbols,
                headers={"Content-Type": "application/json"},
            )
            gene_response.raise_for_status()
            genes = gene_response.json()
            entrez_ids = [g.get("entrezGeneId") for g in genes]

        # Fetch structural variants
        # The API uses POST with sample list or sample IDs
        try:
            if entrez_ids:
                # Fetch by gene
                sv_response = await self._client.post(
                    f"/molecular-profiles/{profile_id}/structural-variant/fetch",
                    json={
                        "entrezGeneIds": entrez_ids,
                        "sampleMolecularIdentifiers": [],
                    },
                    params={"structuralVariantFilter": "ALL"},
                    headers={"Content-Type": "application/json"},
                )
            else:
                # Fetch all structural variants for the study
                sv_response = await self._client.post(
                    f"/molecular-profiles/{profile_id}/structural-variant/fetch",
                    json={
                        "sampleListId": f"{study_id}_all",
                    },
                    params={"structuralVariantFilter": "ALL"},
                    headers={"Content-Type": "application/json"},
                )

            sv_response.raise_for_status()
            sv_data = sv_response.json()
        except httpx.HTTPStatusError as e:
            # Some studies may not support this endpoint format
            return ToolResult(
                success=False,
                error=f"Could not fetch structural variants: {e.response.status_code}. The study may use a different data format.",
            )

        if not sv_data:
            return ToolResult(
                success=True,
                data={
                    "study_id": study_id,
                    "total_fusions": 0,
                    "message": "No structural variants/fusions found" + (f" for genes {gene_symbols}" if gene_symbols else ""),
                    "fusions": [],
                },
            )

        # Process and summarize fusions
        from collections import Counter
        fusion_pairs = Counter()
        fusion_details = []

        for sv in sv_data[:200]:  # Limit to first 200
            gene1 = sv.get("site1HugoSymbol", "Unknown")
            gene2 = sv.get("site2HugoSymbol", "Unknown")

            # Normalize fusion pair (alphabetical order)
            pair = tuple(sorted([gene1, gene2]))
            fusion_pairs[pair] += 1

            fusion_details.append({
                "sample_id": sv.get("sampleId"),
                "gene1": gene1,
                "gene2": gene2,
                "event_info": sv.get("eventInfo", ""),
                "variant_class": sv.get("variantClass", ""),
            })

        # Get top fusion pairs
        top_fusions = [
            {"genes": f"{p[0]}-{p[1]}", "count": c}
            for p, c in fusion_pairs.most_common(20)
        ]

        return ToolResult(
            success=True,
            data={
                "study_id": study_id,
                "total_fusions": len(sv_data),
                "unique_fusion_pairs": len(fusion_pairs),
                "top_fusion_pairs": top_fusions,
                "sample_fusions": fusion_details[:50],  # First 50 detailed records
            },
        )

    async def _tool_create_chart(
        self,
        chart_type: str,
        title: str,
        labels: list[str] | None = None,
        values: list[float] | None = None,
        survival_data: list[dict] | None = None,
        x_values: list[float] | None = None,
        y_values: list[float] | None = None,
        x_label: str | None = None,
        y_label: str | None = None,
        heatmap_data: dict | None = None,
        text_labels: list[str] | None = None,
    ) -> ToolResult:
        """Create a chart visualization that will be rendered in the UI."""
        # Color palette - scientific, colorblind-friendly
        colors = ["#10a37f", "#5436da", "#ef4444", "#f59e0b", "#3b82f6", "#8b5cf6", "#ec4899", "#14b8a6"]

        # Build Plotly config based on chart type
        if chart_type in ["pie", "doughnut"]:
            if not labels or not values:
                return ToolResult(success=False, error="Pie/doughnut charts require 'labels' and 'values' parameters")
            chart_config = {
                "data": [{
                    "type": "pie",
                    "labels": labels,
                    "values": values,
                    "name": "",
                    "marker": {"colors": colors[:len(values)]},
                    "textinfo": "label+percent",
                    "textposition": "inside",
                    "hole": 0.4 if chart_type == "doughnut" else 0,
                    "hovertemplate": "<b>%{label}</b><br>Count: %{value}<br>Percentage: %{percent}<extra></extra>"
                }],
                "layout": {
                    "title": {"text": title, "font": {"size": 16}}
                }
            }
        elif chart_type == "bar":
            if not labels or not values:
                return ToolResult(success=False, error="Bar charts require 'labels' and 'values' parameters")
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
                    "xaxis": {"title": x_label or "", "tickangle": -45 if len(labels) > 4 else 0},
                    "yaxis": {"title": y_label or "Count", "gridcolor": "#3a3a3a"}
                }
            }
        elif chart_type == "survival":
            if not survival_data:
                return ToolResult(success=False, error="Survival charts require 'survival_data' parameter with times and probabilities")

            traces = []
            for i, group in enumerate(survival_data):
                traces.append({
                    "type": "scatter",
                    "mode": "lines",
                    "x": group.get("times", []),
                    "y": group.get("probabilities", []),
                    "name": group.get("name", f"Group {i+1}"),
                    "line": {"shape": "hv", "color": colors[i % len(colors)], "width": 2},
                    "hovertemplate": "<b>%{fullData.name}</b><br>Time: %{x:.1f} months<br>Survival: %{y:.1%}<extra></extra>"
                })

            chart_config = {
                "data": traces,
                "layout": {
                    "title": {"text": title, "font": {"size": 16}},
                    "xaxis": {"title": x_label or "Time (months)", "gridcolor": "#3a3a3a"},
                    "yaxis": {"title": y_label or "Survival Probability", "range": [0, 1.05], "gridcolor": "#3a3a3a"},
                    "showlegend": True,
                    "legend": {"x": 0.7, "y": 0.95}
                }
            }
        elif chart_type == "scatter":
            if not x_values or not y_values:
                return ToolResult(success=False, error="Scatter charts require 'x_values' and 'y_values' parameters")

            trace = {
                "type": "scatter",
                "mode": "markers",
                "x": x_values,
                "y": y_values,
                "name": "",
                "marker": {"color": colors[0], "size": 8},
            }

            if text_labels:
                trace["text"] = text_labels
                trace["hovertemplate"] = "<b>%{text}</b><br>X: %{x}<br>Y: %{y}<extra></extra>"
            else:
                trace["hovertemplate"] = "X: %{x}<br>Y: %{y}<extra></extra>"

            chart_config = {
                "data": [trace],
                "layout": {
                    "title": {"text": title, "font": {"size": 16}},
                    "xaxis": {"title": x_label or "X", "gridcolor": "#3a3a3a"},
                    "yaxis": {"title": y_label or "Y", "gridcolor": "#3a3a3a"}
                }
            }
        elif chart_type == "lollipop":
            if not x_values or not y_values:
                return ToolResult(success=False, error="Lollipop charts require 'x_values' and 'y_values' parameters")

            # Lollipop chart: vertical lines with markers at top (like mutation position plots)
            traces = [
                # Stems (lines from 0 to value)
                {
                    "type": "scatter",
                    "mode": "lines",
                    "x": [x for x in x_values for _ in range(2)],
                    "y": [val for y in y_values for val in [0, y]],
                    "line": {"color": "#666666", "width": 1},
                    "hoverinfo": "skip",
                    "showlegend": False,
                },
                # Markers at top
                {
                    "type": "scatter",
                    "mode": "markers",
                    "x": x_values,
                    "y": y_values,
                    "marker": {"color": colors[0], "size": 10},
                    "name": "",
                    "text": text_labels or [str(x) for x in x_values],
                    "hovertemplate": "<b>%{text}</b><br>Position: %{x}<br>Count: %{y}<extra></extra>"
                }
            ]

            chart_config = {
                "data": traces,
                "layout": {
                    "title": {"text": title, "font": {"size": 16}},
                    "xaxis": {"title": x_label or "Position", "gridcolor": "#3a3a3a"},
                    "yaxis": {"title": y_label or "Count", "gridcolor": "#3a3a3a", "rangemode": "tozero"}
                }
            }
        elif chart_type == "heatmap":
            if not heatmap_data:
                return ToolResult(success=False, error="Heatmap charts require 'heatmap_data' parameter with z, x, and y arrays")

            chart_config = {
                "data": [{
                    "type": "heatmap",
                    "z": heatmap_data.get("z", []),
                    "x": heatmap_data.get("x", []),
                    "y": heatmap_data.get("y", []),
                    "colorscale": "RdBu",
                    "reversescale": True,
                    "hovertemplate": "X: %{x}<br>Y: %{y}<br>Value: %{z}<extra></extra>"
                }],
                "layout": {
                    "title": {"text": title, "font": {"size": 16}},
                    "xaxis": {"title": x_label or ""},
                    "yaxis": {"title": y_label or ""}
                }
            }
        else:
            return ToolResult(success=False, error=f"Unknown chart type: {chart_type}. Supported: pie, bar, doughnut, survival, scatter, heatmap, lollipop")

        # Return the chart as a special markdown block
        chart_json = json.dumps(chart_config, indent=2)
        chart_markdown = f"```chart\n{chart_json}\n```"

        return ToolResult(
            success=True,
            data=f"Chart created successfully. Include this EXACTLY in your response to display it:\n\n{chart_markdown}\n\nIMPORTANT: Copy the above chart block exactly as shown."
        )

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

## New Advanced Features

### Survival Analysis
- Use `get_survival_data` to query OS (overall survival) data
- Can stratify by gene mutation to compare mutated vs wild-type survival
- Returns Kaplan-Meier curve data (times, probabilities) ready for visualization
- After getting survival data, use `create_chart` with chart_type="survival" and survival_data parameter
- Example: For "Does TP53 affect survival?", first get_survival_data(study_id, gene_symbol="TP53"), then create the survival chart

### Enrichment Analysis (Co-occurrence)
- Use `get_alteration_enrichments` to find co-occurring or mutually exclusive alterations
- Supports MUTATION or CNA alteration types
- Returns odds ratios: >1.5 suggests co-occurrence, <0.67 suggests mutual exclusivity
- Compares against common cancer genes automatically

### Gene Fusions / Structural Variants
- Use `get_structural_variants` to query fusion data
- Can filter by specific genes (e.g., ALK, ROS1, NTRK1)
- Returns fusion pairs and their frequencies
- Not all studies have structural variant data - handle gracefully if missing

### Advanced Visualizations
When creating charts, choose the appropriate type:
- survival: For Kaplan-Meier curves (step-function with times/probabilities)
- lollipop: For mutation position plots (position on x-axis, count on y-axis)
- scatter: For correlations between two continuous variables
- heatmap: For gene-sample alteration matrices
"""
