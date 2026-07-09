# workflow-generator

<!-- mcp-name: io.github.askuma/workflow-generator -->

Scan any project and generate **WORKFLOW.html** — a dark-mode visual system diagram showing every component, how they talk to each other, and where your throughput ceiling actually is.

Works with Python, Node.js, Go, and mixed projects. No external dependencies for the core scanner.
Vendored and generated directories (`node_modules`, `venv`, `site-packages`, `dist`, …) are never scanned,
and capacity figures are clearly labeled as static-analysis estimates.

**[Live demo →](https://askuma.github.io/workflow-generator/)** — generated from
[fastapi/full-stack-fastapi-template](https://github.com/fastapi/full-stack-fastapi-template), unmodified.

![WORKFLOW.html generated for full-stack-fastapi-template](https://raw.githubusercontent.com/askuma/workflow-generator/main/docs/preview.png)

## What it produces

Every generated page contains:

| Section | What you get |
|---|---|
| **Stat row** | Workers · Concurrent I/O ceiling · Semaphore limit · Rate limit · Practical throughput |
| **Architecture diagram** | Layered flow: external sources → gateway → API → queues → AI → storage |
| **Data flow cards** | Write path, read/query path, background jobs — inferred from what's detected |
| **Concurrency table** | Every layer: model · ceiling · limiting factor · code reference |
| **Bottleneck analysis** | Ranked CRITICAL → LOW with mitigation notes |

## What it detects

| Category | Examples |
|---|---|
| API frameworks | FastAPI, Flask, Django, Express, Nest.js, Gin |
| Gateways | nginx, Caddy, Traefik (with rate limits + worker_connections) |
| LLM providers | OpenAI, Anthropic Claude, Cohere, AWS Bedrock |
| Vector stores | Qdrant, Pinecone, Weaviate, ChromaDB, pgvector, FAISS, Milvus |
| Databases | PostgreSQL, MySQL, MongoDB, SQLite, Redis |
| Queues | Celery, BullMQ, Kafka, RabbitMQ, RQ, AWS SQS |
| Async primitives | `asyncio.Semaphore`, `run_in_executor`, `asyncio.gather`, `asyncio.Lock` |
| Workers | `--workers N` (uvicorn/gunicorn), `replicas:` (docker-compose), PM2 instances |
| External sources | Jira, Azure DevOps, Slack, GitHub, Stripe, Salesforce, Twilio |
| Evaluation | TruLens, RAGAS, LangSmith |

---

## Install

### pip (CLI + MCP server)

```bash
pip install workflow-generator-mcp

workflow-generator . WORKFLOW.html       # CLI: scan and write the report
workflow-generator-mcp                    # stdio MCP server
```

With pip installed, any MCP host config reduces to:

```json
{
  "mcpServers": {
    "workflow-generator": { "command": "workflow-generator-mcp" }
  }
}
```

### Claude Code (skill)

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/askuma/workflow-generator.git ~/.claude/skills/workflow-generator
```

Then in any Claude Code session:

```
/workflow-generator
/workflow-generator /path/to/project
```

### MCP server (Claude Desktop, VS Code, Cursor, Zed, Windsurf, Continue)

**1. Install the dependency:**
```bash
pip install mcp
```

**2. Add to your MCP host config** (replace `~` with your actual home path):

<details>
<summary>Claude Desktop</summary>

`~/Library/Application Support/Claude/claude_desktop_config.json` (Mac)  
`%APPDATA%\Claude\claude_desktop_config.json` (Windows)

```json
{
  "mcpServers": {
    "workflow-generator": {
      "command": "python3",
      "args": ["~/.claude/skills/workflow-generator/mcp/server.py"]
    }
  }
}
```
</details>

<details>
<summary>VS Code</summary>

`.vscode/mcp.json`

```json
{
  "servers": {
    "workflow-generator": {
      "type": "stdio",
      "command": "python3",
      "args": ["~/.claude/skills/workflow-generator/mcp/server.py"]
    }
  }
}
```
</details>

<details>
<summary>Cursor</summary>

`~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "workflow-generator": {
      "command": "python3",
      "args": ["~/.claude/skills/workflow-generator/mcp/server.py"]
    }
  }
}
```
</details>

<details>
<summary>Zed</summary>

`.zed/settings.json`

```json
{
  "context_servers": {
    "workflow-generator": {
      "command": {
        "path": "python3",
        "args": ["~/.claude/skills/workflow-generator/mcp/server.py"]
      }
    }
  }
}
```
</details>

<details>
<summary>Windsurf</summary>

`~/.windsurf/mcp_config.json`

```json
{
  "mcpServers": {
    "workflow-generator": {
      "command": "python3",
      "args": ["~/.claude/skills/workflow-generator/mcp/server.py"]
    }
  }
}
```
</details>

**3. Restart your tool, then ask:**
```
generate a workflow diagram for this project
how many concurrent requests can this handle?
show me the system architecture
```

**MCP tools exposed:**
- `generate_workflow` — scans project, writes `WORKFLOW.html`, optionally opens in browser
- `analyze_workflow` — returns structured JSON summary (no file written)

### Command line (standalone)

No install needed beyond Python 3.8+:

```bash
python3 ~/.claude/skills/workflow-generator/scripts/analyze.py . ~/WORKFLOW.html
# then open ~/WORKFLOW.html
```

---

## Example output (terminal)

```
Written: /your/project/WORKFLOW.html
Framework: FastAPI · Workers: 8 · Concurrent I/O: ~800
Practical throughput: ~50–200 req/min
Bottleneck: OpenAI (LLM latency 3–30s per call)
Gateway: nginx · 2 rate limit zone(s)
LLM: OpenAI · eval: TruLens RAG Triad
Storage: Qdrant, Redis
External sources: Jira, Azure DevOps, Slack
```

---

## Repo layout

```
workflow-generator/
├── SKILL.md              ← Claude Code skill definition
├── INSTALL.md            ← detailed per-platform install guide
├── scripts/
│   └── analyze.py        ← core scanner + HTML renderer (stdlib only)
├── mcp/
│   ├── server.py         ← MCP stdio server
│   └── requirements.txt  ← pip install mcp
└── copilot/
    ├── index.js          ← GitHub Copilot Extension (Express)
    ├── package.json
    └── openai_function.json
```

---

## License

MIT
