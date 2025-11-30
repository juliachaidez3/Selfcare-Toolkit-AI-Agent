# Self-Care MCP Agent

This directory hosts a small MCP server and driver modeled after the `yt-mcp-agent` example. The server exposes:

- A `system_prompt` prompt that reuses the same coaching instructions as the rest of the project.
- A `generate_toolkit` tool that calls OpenAI with the existing prompt template to create self-care recommendations.

## Requirements

- Python 3.10+
- An OpenAI API key (`OPENAI_API_KEY`)
- `uv` (recommended) or plain `pip`

## Setup

```bash
cd selfcare-mcp-agent
cp .env.example .env  # fill in your API key
```

### Using uv (recommended)
```bash
uv sync
uv run main.py
```

### Using pip
```bash
python -m venv .venv
.venv\\Scripts\\activate  # On macOS/Linux: source .venv/bin/activate
pip install -e .
python main.py
```

The CLI will launch an OpenAI Agent that communicates with the MCP server over stdio. Type `exit` to leave the session.
