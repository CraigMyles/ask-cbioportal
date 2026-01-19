# ask-cbioportal

A natural language interface for querying [cBioPortal](https://www.cbioportal.org/) cancer genomics data using Claude AI.

## Features

- **Natural language queries**: Ask questions about cancer genomics data in plain English
- **Multiple backends**:
  - REST API (default): Works immediately with the public cBioPortal API
  - MCP/ClickHouse: For faster queries via cbioportal-mcp server
- **Interactive chat**: Multi-turn conversations with follow-up questions
- **CLI and Web interfaces**: Use from terminal or browser
- **Rich output**: Formatted tables, markdown responses, and streaming

## Installation

```bash
# Install from source
pip install -e .

# Or with web interface support
pip install -e ".[web]"

# Or with development dependencies
pip install -e ".[dev]"
```

## Quick Start

1. **Set up your configuration**

   Create a `.env` file in the project root (copy from `.env.example`):

   ```bash
   cp .env.example .env
   ```

   Then edit `.env` to configure your LLM provider:

   **Option A: Use Local LLMs via LiteLLM** (recommended for institutional GPU clusters)
   ```bash
   LLM_PROVIDER=litellm
   LITELLM_API_BASE=http://192.168.33.27  # Your LiteLLM server
   LITELLM_API_KEY=your_api_key_here
   MODEL=gpt-4  # Or whatever model alias your server uses
   ```

   **Option B: Use Anthropic's Claude API** (cloud)
   ```bash
   LLM_PROVIDER=anthropic
   ANTHROPIC_API_KEY=your_api_key_here
   MODEL=claude-sonnet-4-20250514
   ```

2. **Ask a question**

   ```bash
   ask-cbioportal ask "How many cancer studies are available in cBioPortal?"
   ```

3. **Start an interactive chat**

   ```bash
   ask-cbioportal chat
   ```

## Usage

### Single Query

```bash
ask-cbioportal ask "What genes are commonly mutated in breast cancer?"
```

### Interactive Chat

```bash
ask-cbioportal chat
```

In chat mode:
- Type your questions and press Enter
- Type `clear` to clear conversation history
- Type `exit` or `quit` to end the session

### Web Interface

```bash
# Requires web dependencies: pip install -e ".[web]"
ask-cbioportal web
```

Then open http://127.0.0.1:8000 in your browser.

### Direct Data Access

```bash
# List studies
ask-cbioportal studies list

# Filter by keyword
ask-cbioportal studies list -k "breast"

# Get study details
ask-cbioportal studies info brca_tcga

# Get gene information
ask-cbioportal genes info TP53 BRCA1 EGFR
```

### Configuration

```bash
# Show current configuration
ask-cbioportal config show

# Set backend (rest or mcp)
ask-cbioportal config set-backend rest
```

## Backends

### REST API Backend (Default)

Uses the public cBioPortal REST API at https://www.cbioportal.org/api. No additional setup required.

```bash
# Explicitly use REST API
export ASK_CBIOPORTAL_BACKEND=rest
```

### MCP/ClickHouse Backend

For faster queries, you can use the cbioportal-mcp server with a local ClickHouse database.

1. Set up ClickHouse with cBioPortal data (see [cbioportal-docker-compose](https://github.com/cBioPortal/cbioportal-docker-compose))

2. Install cbioportal-mcp:
   ```bash
   pip install cbioportal-mcp
   ```

3. Configure:
   ```bash
   export ASK_CBIOPORTAL_BACKEND=mcp
   export MCP_SERVER_COMMAND="uvx cbioportal-mcp"
   export CLICKHOUSE_HOST=localhost
   export CLICKHOUSE_PORT=8123
   ```

## Example Queries

Here are some example questions you can ask:

- "How many studies are available in cBioPortal?"
- "Find all breast cancer studies"
- "What mutations are found in TP53 in the TCGA breast cancer study?"
- "What is the mutation rate of BRCA1 across different cancers?"
- "List the clinical attributes available in the MSK-IMPACT study"
- "How many patients have KRAS mutations in lung adenocarcinoma?"
- "What genes are in the DNA repair pathway?"
- "Compare mutation frequencies of EGFR in lung vs colorectal cancer"

## Environment Variables

### LLM Provider Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM provider: `anthropic` or `litellm` | `anthropic` |
| `MODEL` | Model name (provider-specific) | `claude-sonnet-4-20250514` |
| `MAX_TOKENS` | Maximum response tokens | `4096` |
| `STREAMING` | Enable streaming responses | `true` |

**Anthropic-specific** (when `LLM_PROVIDER=anthropic`):
| Variable | Description | Default |
|----------|-------------|---------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | - |

**LiteLLM-specific** (when `LLM_PROVIDER=litellm`):
| Variable | Description | Default |
|----------|-------------|---------|
| `LITELLM_API_BASE` | LiteLLM server URL | `http://localhost:4000` |
| `LITELLM_API_KEY` | API key (if required) | - |

### Data Backend Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `ASK_CBIOPORTAL_BACKEND` | Backend type: `rest` or `mcp` | `rest` |
| `CBIOPORTAL_API_URL` | REST API base URL | `https://www.cbioportal.org/api` |
| `MCP_SERVER_COMMAND` | Command to start MCP server | - |
| `CLICKHOUSE_HOST` | ClickHouse server host | `localhost` |
| `CLICKHOUSE_PORT` | ClickHouse server port | `8123` |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run type checking
mypy src/

# Run linting
ruff check src/
```

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  User (CLI/Web) │────▶│  ask-cbioportal  │────▶│  Data Backend   │
│                 │◀────│  (Python app)    │◀────│  (REST or MCP)  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                │                        │
                                ▼                        ▼
                        ┌──────────────┐         ┌─────────────┐
                        │ LLM Provider │         │  cBioPortal │
                        │ (Anthropic,  │         │  Database   │
                        │  LiteLLM,    │         │             │
                        │  Local LLMs) │         └─────────────┘
                        └──────────────┘
```

### How It Works

1. **You ask a question** in natural language (CLI or web)
2. **The LLM interprets** your question and decides which cBioPortal API calls to make
3. **Data is fetched** from cBioPortal (via REST API or ClickHouse)
4. **The LLM summarizes** the results in plain English

### LLM Provider Options

- **Anthropic Claude** (cloud): Best quality, requires API key
- **LiteLLM** (local/cloud): Route to any OpenAI-compatible API including:
  - Local models on GPU clusters
  - Ollama, vLLM, text-generation-inference
  - Azure OpenAI, AWS Bedrock, etc.

## License

MIT

## Acknowledgments

- [cBioPortal](https://www.cbioportal.org/) - Cancer genomics database
- [cbioportal-mcp](https://github.com/cBioPortal/cbioportal-mcp) - MCP server for cBioPortal
- [Anthropic Claude](https://anthropic.com/) - AI assistant
