# workflow-generator — Installation Guide

Type `/workflow-generator` in any supported tool to get a visual system workflow for your project.

The skill lives at: `~/.claude/skills/workflow-generator/`

```
~/.claude/skills/workflow-generator/
├── SKILL.md                  ← Claude Code skill definition
├── INSTALL.md                ← this file
├── scripts/
│   └── analyze.py            ← core scanner + HTML renderer (no external deps)
├── mcp/
│   ├── server.py             ← MCP stdio server
│   └── requirements.txt      ← pip install mcp
└── copilot/
    ├── index.js              ← GitHub Copilot Extension (Express)
    ├── package.json
    └── openai_function.json  ← OpenAI / Antigravity function schema
```

---

## Claude Code (already installed)

Just use:
```
/workflow-generator
/workflow-generator /path/to/project
```

To reinstall:
```bash
mkdir -p ~/.claude/skills/workflow-generator/{scripts,mcp,copilot}
# copy SKILL.md, scripts/analyze.py, mcp/server.py, etc.
```

---

## MCP — Claude Desktop, VS Code, Cursor, Zed, Windsurf, Continue

Any MCP-compatible host can use the stdio server.

**Install the dependency:**
```bash
pip install mcp
```

**Configure your MCP host** (replace `/home/<you>` with your home directory):

### Claude Desktop
`~/Library/Application Support/Claude/claude_desktop_config.json` (Mac)
`%APPDATA%\Claude\claude_desktop_config.json` (Windows)
```json
{
  "mcpServers": {
    "workflow-generator": {
      "command": "python3",
      "args": ["/home/<you>/.claude/skills/workflow-generator/mcp/server.py"]
    }
  }
}
```

### VS Code (`.vscode/mcp.json` or user `settings.json`)
```json
{
  "servers": {
    "workflow-generator": {
      "type": "stdio",
      "command": "python3",
      "args": ["/home/<you>/.claude/skills/workflow-generator/mcp/server.py"]
    }
  }
}
```

### Cursor (`~/.cursor/mcp.json`)
```json
{
  "mcpServers": {
    "workflow-generator": {
      "command": "python3",
      "args": ["/home/<you>/.claude/skills/workflow-generator/mcp/server.py"]
    }
  }
}
```

### Zed (`.zed/settings.json`)
```json
{
  "context_servers": {
    "workflow-generator": {
      "command": {
        "path": "python3",
        "args": ["/home/<you>/.claude/skills/workflow-generator/mcp/server.py"]
      }
    }
  }
}
```

### Windsurf (`~/.windsurf/mcp_config.json`)
```json
{
  "mcpServers": {
    "workflow-generator": {
      "command": "python3",
      "args": ["/home/<you>/.claude/skills/workflow-generator/mcp/server.py"]
    }
  }
}
```

**Restart your tool, then use:**
```
/workflow-generator
"generate workflow diagram"
"how many concurrent requests can this project handle?"
"show me the system architecture"
```

**MCP tools exposed:**
- `generate_workflow` — scans project, writes `WORKFLOW.html`, opens in browser
- `analyze_workflow` — returns JSON summary with capacity numbers, no file written

---

## GitHub Copilot Extension

**Prerequisites:** GitHub account with Copilot access, public HTTPS endpoint (ngrok for local dev)

```bash
cd ~/.claude/skills/workflow-generator/copilot
npm install
npm start   # port 3000

# Expose locally:
ngrok http 3000
```

**Register the GitHub App:**
1. GitHub → Settings → Developer settings → GitHub Apps → New GitHub App
2. Set **Homepage URL** and **Callback URL** to your ngrok URL
3. Enable **Copilot Extension**, set **Agent URL**: `https://your-url/agent`
4. Permissions: `Copilot chat` → Read & Write
5. Install on your account or organisation

**Usage in Copilot Chat:**
```
@workflow-generator /workflow-generator
@workflow-generator /workflow-generator /path/to/project
```

---

## Antigravity / OpenAI-compatible function calling

Register `copilot/openai_function.json` in your assistant config.
When the model calls `generate_workflow`, execute:
```bash
python3 ~/.claude/skills/workflow-generator/scripts/analyze.py <project_dir> <output_file>
```

---

## Quick test (any platform)

```bash
python3 ~/.claude/skills/workflow-generator/scripts/analyze.py . ~/WORKFLOW.html
# open ~/WORKFLOW.html in browser
```

Expected output:
```
Written: /home/you/WORKFLOW.html
Framework: FastAPI · Workers: 8 · Concurrent I/O: ~800
Bottleneck: OpenAI · Practical throughput: ~50–200/min
Gateway: nginx · 2 rate limit zone(s)
LLM: OpenAI · eval: TruLens RAG Triad
Storage: Qdrant, Redis
External sources: Jira, Azure DevOps, Slack, Users / API Clients
```

---

## What gets detected

| Category | Signals |
|---|---|
| **Workers** | `--workers N` (uvicorn/gunicorn), `replicas: N` (docker-compose), PM2 `instances`, Celery `-c N` |
| **Async** | `asyncio.Semaphore(N)`, `run_in_executor`, `asyncio.gather`, `async def` density |
| **Gateway** | `nginx.conf`, `Caddyfile`, `traefik.yml`, nginx image in docker-compose |
| **Rate limits** | `limit_req_zone` (nginx), `@limiter.limit` (slowapi), `express-rate-limit` |
| **API framework** | FastAPI, Flask, Django, Express, Gin (Go), Spring Boot |
| **Frontend** | Streamlit, Gradio, React, Next.js, Vue, Svelte |
| **LLM** | OpenAI (ChatOpenAI), Anthropic (Claude), Cohere, AWS Bedrock |
| **Embedding** | `text-embedding-3`, `CohereEmbeddings`, `HuggingFaceEmbeddings` |
| **Vector stores** | Qdrant, Pinecone, Weaviate, ChromaDB, pgvector, FAISS, Milvus |
| **Databases** | PostgreSQL, MySQL, MongoDB, SQLite, Redis |
| **Queues** | Celery, BullMQ, Kafka, RabbitMQ, RQ, AWS SQS |
| **External sources** | Jira, Azure DevOps, Slack, GitHub, Stripe, Salesforce, Twilio |
| **Evaluation** | TruLens, RAGAS, LangSmith |

## Output sections

Every generated `WORKFLOW.html` includes:

1. **Stat row** — worker count, concurrent I/O ceiling, semaphore limit, rate limit, practical throughput
2. **Architecture diagram** — adaptive layered flow (layers with no components omitted)
3. **Flow cards** — write path, read path, queue jobs (inferred from what's detected)
4. **Concurrency table** — every layer: model / ceiling / limiting factor
5. **Bottleneck analysis** — ranked bars CRITICAL → LOW with mitigation notes
