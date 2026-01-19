"""Command-line interface for ask-cbioportal."""

import asyncio
import sys
from typing import Any

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from ask_cbioportal.agent import Agent
from ask_cbioportal.backends import McpClickHouseBackend, RestApiBackend
from ask_cbioportal.config import BackendType, Config, ConfigFile, LLMProvider, get_config

console = Console()


def get_backend(config: Config) -> RestApiBackend | McpClickHouseBackend:
    """Create the appropriate backend based on configuration."""
    if config.backend == BackendType.MCP:
        return McpClickHouseBackend(config)
    return RestApiBackend(config)


def validate_config(config: Config) -> bool:
    """Validate configuration and print errors."""
    errors = config.validate()
    if errors:
        console.print("[bold red]Configuration errors:[/bold red]")
        for error in errors:
            console.print(f"  - {error}")
        console.print("\nPlease set the required environment variables or create a .env file.")
        console.print("See .env.example for a template.")
        return False
    return True


@click.group(invoke_without_command=True)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    """Natural language interface for querying cBioPortal cancer genomics data.

    Use 'ask-cbioportal ask' for single queries or 'ask-cbioportal chat' for
    interactive conversations.
    """
    ctx.ensure_object(dict)
    config = get_config()
    config.verbose = verbose or config.verbose
    ctx.obj["config"] = config

    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.argument("question")
@click.option("--no-stream", is_flag=True, help="Disable streaming output")
@click.pass_context
def ask(ctx: click.Context, question: str, no_stream: bool) -> None:
    """Ask a single question about cBioPortal data.

    Example: ask-cbioportal ask "How many cancer studies are available?"
    """
    config: Config = ctx.obj["config"]

    if not validate_config(config):
        sys.exit(1)

    async def run_query() -> None:
        backend = get_backend(config)

        async with backend:
            agent = Agent(config, backend)

            if config.verbose:
                console.print(f"[dim]Using backend: {backend.name}[/dim]")
                console.print(f"[dim]Model: {config.claude_model}[/dim]")
                console.print()

            console.print(Panel(question, title="Question", border_style="blue"))
            console.print()

            if no_stream or not config.streaming:
                with console.status("[bold green]Thinking...[/bold green]"):
                    response = await agent.query(question)

                if config.verbose and response.tool_calls:
                    console.print("[dim]Tool calls made:[/dim]")
                    for tc in response.tool_calls:
                        console.print(f"[dim]  - {tc['name']}[/dim]")
                    console.print()

                console.print(Markdown(response.content))
            else:
                collected_response = ""
                async for chunk in agent.query_stream(question):
                    if chunk.startswith("\n[Calling"):
                        console.print(f"[dim]{chunk.strip()}[/dim]", end="")
                    else:
                        console.print(chunk, end="")
                        collected_response += chunk

                console.print()

    asyncio.run(run_query())


@main.command()
@click.pass_context
def chat(ctx: click.Context) -> None:
    """Start an interactive chat session.

    Allows multi-turn conversations with follow-up questions.
    Type 'exit', 'quit', or press Ctrl+C to end the session.
    """
    config: Config = ctx.obj["config"]

    if not validate_config(config):
        sys.exit(1)

    async def run_chat() -> None:
        backend = get_backend(config)

        async with backend:
            agent = Agent(config, backend)

            console.print(
                Panel(
                    "[bold]Welcome to ask-cbioportal![/bold]\n\n"
                    "Ask questions about cancer genomics data from cBioPortal.\n"
                    "Type 'exit' or 'quit' to end the session.\n"
                    "Type 'clear' to clear conversation history.",
                    title="ask-cbioportal",
                    border_style="green",
                )
            )
            console.print(f"[dim]Backend: {backend.name} | Model: {config.claude_model}[/dim]")
            console.print()

            while True:
                try:
                    question = Prompt.ask("[bold blue]You[/bold blue]")

                    if not question.strip():
                        continue

                    if question.lower() in ("exit", "quit"):
                        console.print("[dim]Goodbye![/dim]")
                        break

                    if question.lower() == "clear":
                        agent.clear_conversation()
                        console.print("[dim]Conversation cleared.[/dim]")
                        continue

                    console.print()

                    if config.streaming:
                        console.print("[bold green]Assistant[/bold green]: ", end="")
                        async for chunk in agent.query_stream(question):
                            if chunk.startswith("\n[Calling"):
                                console.print(f"\n[dim]{chunk.strip()}[/dim]", end="")
                            else:
                                console.print(chunk, end="")
                        console.print("\n")
                    else:
                        with console.status("[bold green]Thinking...[/bold green]"):
                            response = await agent.query(question)
                        console.print("[bold green]Assistant[/bold green]:")
                        console.print(Markdown(response.content))
                        console.print()

                except KeyboardInterrupt:
                    console.print("\n[dim]Goodbye![/dim]")
                    break
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
                    if config.verbose:
                        console.print_exception()

    asyncio.run(run_chat())


@main.group()
def config_cmd() -> None:
    """Manage configuration settings."""
    pass


@config_cmd.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Show current configuration."""
    config: Config = ctx.obj["config"]

    table = Table(title="Current Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    # Data backend (where cBioPortal data comes from)
    table.add_row("Data Backend", config.backend.value)
    table.add_row("REST API URL", config.rest_api_base_url)

    # LLM Provider settings
    table.add_row("", "")  # Spacer
    table.add_row("LLM Provider", config.llm_provider.value)
    table.add_row("Model", config.model)
    table.add_row("Max Tokens", str(config.max_tokens))
    table.add_row("Streaming", str(config.streaming))

    if config.llm_provider == LLMProvider.ANTHROPIC:
        table.add_row("Anthropic API Key", "Set" if config.anthropic_api_key else "Not set")
    elif config.llm_provider == LLMProvider.LITELLM:
        table.add_row("LiteLLM API Base", config.litellm_api_base)
        table.add_row("LiteLLM API Key", "Set" if config.litellm_api_key else "Not set")

    if config.backend == BackendType.MCP:
        table.add_row("", "")  # Spacer
        table.add_row("MCP Command", config.mcp_server_command or "Not set")
        table.add_row("ClickHouse Host", config.clickhouse_host)
        table.add_row("ClickHouse Port", str(config.clickhouse_port))

    console.print(table)


@config_cmd.command("set-backend")
@click.argument("backend", type=click.Choice(["rest", "mcp"]))
def config_set_backend(backend: str) -> None:
    """Set the default backend (rest or mcp)."""
    config_file = ConfigFile()
    backend_type = BackendType(backend)
    config_file.save_backend(backend_type)
    console.print(f"[green]Backend set to: {backend}[/green]")
    console.print(f"[dim]Saved to: {config_file.config_file}[/dim]")


@main.group()
def studies() -> None:
    """Commands for exploring studies directly."""
    pass


@studies.command("list")
@click.option("--keyword", "-k", help="Filter studies by keyword")
@click.option("--limit", "-l", default=20, help="Maximum number of studies to show")
@click.pass_context
def studies_list(ctx: click.Context, keyword: str | None, limit: int) -> None:
    """List available cancer studies."""
    config: Config = ctx.obj["config"]

    if config.backend == BackendType.MCP:
        console.print("[yellow]Direct API commands use REST API backend.[/yellow]")

    async def run() -> None:
        backend = RestApiBackend(config)
        async with backend:
            result = await backend.execute_tool(
                "list_studies", {"keyword": keyword, "limit": limit}
            )

            if not result.success:
                console.print(f"[red]Error: {result.error}[/red]")
                return

            data = result.data
            table = Table(title=f"Cancer Studies ({data['total_count']} shown)")
            table.add_column("Study ID", style="cyan", no_wrap=True)
            table.add_column("Name", style="green")
            table.add_column("Cancer Type", style="yellow")
            table.add_column("Samples", justify="right")

            for study in data["studies"]:
                table.add_row(
                    study["study_id"],
                    study["name"][:50] + "..." if len(study["name"]) > 50 else study["name"],
                    study["cancer_type"] or "N/A",
                    str(study["sample_count"]),
                )

            console.print(table)

    asyncio.run(run())


@studies.command("info")
@click.argument("study_id")
@click.pass_context
def studies_info(ctx: click.Context, study_id: str) -> None:
    """Get detailed information about a specific study."""
    config: Config = ctx.obj["config"]

    async def run() -> None:
        backend = RestApiBackend(config)
        async with backend:
            result = await backend.execute_tool("get_study", {"study_id": study_id})

            if not result.success:
                console.print(f"[red]Error: {result.error}[/red]")
                return

            data = result.data
            panel_content = f"""
[bold]Study ID:[/bold] {data.get('studyId')}
[bold]Name:[/bold] {data.get('name')}
[bold]Description:[/bold] {data.get('description', 'N/A')}
[bold]Cancer Type:[/bold] {data.get('cancerTypeId')}
[bold]Reference Genome:[/bold] {data.get('referenceGenome', 'N/A')}
[bold]Citation:[/bold] {data.get('citation', 'N/A')}
[bold]Sample Count:[/bold] {data.get('allSampleCount', 0)}
"""
            console.print(Panel(panel_content, title=data.get("name", study_id)))

    asyncio.run(run())


@main.group()
def genes() -> None:
    """Commands for exploring gene data directly."""
    pass


@genes.command("info")
@click.argument("gene_symbols", nargs=-1, required=True)
@click.pass_context
def genes_info(ctx: click.Context, gene_symbols: tuple[str, ...]) -> None:
    """Get information about specific genes.

    Example: ask-cbioportal genes info TP53 BRCA1 EGFR
    """
    config: Config = ctx.obj["config"]

    async def run() -> None:
        backend = RestApiBackend(config)
        async with backend:
            result = await backend.execute_tool(
                "get_genes", {"gene_symbols": list(gene_symbols)}
            )

            if not result.success:
                console.print(f"[red]Error: {result.error}[/red]")
                return

            table = Table(title="Gene Information")
            table.add_column("Symbol", style="cyan")
            table.add_column("Entrez ID", style="green")
            table.add_column("Type", style="yellow")
            table.add_column("Cytoband")
            table.add_column("Length")

            for gene in result.data:
                table.add_row(
                    gene.get("hugoGeneSymbol", "N/A"),
                    str(gene.get("entrezGeneId", "N/A")),
                    gene.get("type", "N/A"),
                    gene.get("cytoband", "N/A"),
                    str(gene.get("length", "N/A")),
                )

            console.print(table)

    asyncio.run(run())


@main.command()
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to")
@click.option("--port", "-p", default=8000, help="Port to bind to")
@click.pass_context
def web(ctx: click.Context, host: str, port: int) -> None:
    """Start the web interface.

    Launches a web server with a chat UI accessible in your browser.
    Requires the [web] optional dependencies.
    """
    config: Config = ctx.obj["config"]

    if not validate_config(config):
        sys.exit(1)

    try:
        import uvicorn
    except ImportError:
        console.print("[red]Web dependencies not installed.[/red]")
        console.print("Install with: pip install 'ask-cbioportal[web]'")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold]Starting web server[/bold]\n\n"
            f"URL: http://{host}:{port}\n"
            f"Backend: {config.backend.value}\n"
            f"Press Ctrl+C to stop",
            title="ask-cbioportal web",
            border_style="green",
        )
    )

    uvicorn.run(
        "ask_cbioportal.web.app:app",
        host=host,
        port=port,
        reload=False,
    )


# Rename config command to avoid conflict
main.add_command(config_cmd, name="config")


if __name__ == "__main__":
    main()
