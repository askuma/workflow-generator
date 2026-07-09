---
name: workflow-generator
description: |
  FIRE when user intent matches any of the following conditions —

  EXPLICIT TRIGGERS: /workflow-generator; "generate workflow"; "create workflow diagram"; "show workflow"

  ARCHITECTURAL VISUALIZATION INTENT: user wants to visualize, diagram, draw, map, or generate
  a system architecture diagram / component diagram / service topology / service map /
  architecture overview / system overview / data flow diagram / pipeline diagram for the
  current project or a specified project path.

  PHRASING VARIANTS THAT SHOULD ROUTE HERE: "how does this system work", "what talks to what",
  "show me the components", "map the services", "diagram this", "visualize the stack",
  "show request flow", "show data flow", "trace the pipeline", "architecture of this project",
  "system map", "service dependencies", "component graph", "what calls what", "show me the
  architecture", "draw the architecture", "explain the system design", "infrastructure diagram".

  CAPACITY / CONCURRENCY ANALYSIS INTENT: user asks about concurrent request capacity,
  max throughput, practical throughput ceiling, worker count, worker processes, async workers,
  uvicorn/gunicorn workers, replicas, semaphore limits, rate limits, bottleneck analysis,
  "what's the bottleneck", "how many concurrent requests can this handle", "what's the max
  throughput", "where does this system slow down", "what limits this system".

  DATA FLOW TRACING INTENT: user wants to trace write path / read path / ingestion pipeline /
  query pipeline / embedding pipeline / retrieval pipeline through the codebase; wants to
  understand how a request moves end-to-end from client to storage.

  AI/LLM INFRASTRUCTURE ANALYSIS INTENT: user wants to audit or diagram an AI application's
  infrastructure — LLM providers, vector stores, embedding models, eval frameworks, RAG pipeline,
  queue workers, and how they connect.

  DO NOT FIRE when: user asks about a single file, function, class, or bug; wants code review,
  refactor, or test generation; asks about a specific library's API or error message; intent
  is purely explanatory with no visualization, topology, or capacity-analysis component.

  DISAMBIGUATE FROM generate-tech-stack: generate-tech-stack answers "what technologies are
  used" (inventory/listing); this skill answers "how do the components connect and what is the
  capacity" (topology + concurrency). If user wants both, run this skill first.

  DETECTED SIGNALS — frameworks: FastAPI, Flask, Django, Express, NestJS, Gin, Spring;
  gateways: nginx, Caddy, Traefik; LLM: OpenAI, Anthropic, Cohere, Bedrock;
  vector stores: Qdrant, Pinecone, Weaviate, ChromaDB, pgvector, FAISS, Milvus;
  databases: PostgreSQL, MySQL, MongoDB, Redis, SQLite;
  queues: Celery, BullMQ, Kafka, RabbitMQ, RQ, SQS;
  async primitives: asyncio.Semaphore, run_in_executor, asyncio.gather, asyncio.Lock;
  workers: uvicorn --workers, gunicorn -w, docker-compose replicas, PM2 instances.
---

# workflow-generator

Scan the current project and produce a complete visual system workflow with concurrency capacity analysis.

## Steps

1. **Locate the project root** — use the current working directory unless the user specified a path.

2. **Run the analyzer**:
   ```bash
   python3 ~/.claude/skills/workflow-generator/scripts/analyze.py <project_root> <project_root>/WORKFLOW.html
   ```

3. **Open the output**:
   ```bash
   xdg-open <project_root>/WORKFLOW.html 2>/dev/null || open <project_root>/WORKFLOW.html 2>/dev/null || true
   ```

4. **Report to the user** — include:
   - Framework and worker count
   - Concurrent request capacity (total I/O + practical throughput)
   - Primary bottleneck
   - Detected storage and external sources
   - Clickable link to `WORKFLOW.html`

## Output sections

The generated `WORKFLOW.html` always contains all of the following:

1. **Stat row** — 4–6 large-number tiles:
   - API Worker Processes (replicas × uvicorn/gunicorn workers)
   - Max Concurrent Async I/O (~100 per asyncio worker)
   - Max Parallel CPU Tasks (asyncio.Semaphore limit, if detected)
   - Rate Limit (nginx / slowapi / express-rate-limit, if detected)
   - Practical Throughput (what the real ceiling is after all limits)
   - LLM Timeout (if an LLM provider is detected)

2. **System Architecture diagram** — adaptive layered CSS flow:
   - **EXTERNAL SOURCES & CLIENTS** — webhook sources (Jira, Slack, ADO, GitHub, Stripe), users
   - **GATEWAY / REVERSE PROXY** — nginx, Caddy, Traefik (with rate limits + worker_connections)
   - **APPLICATION LAYER** — API framework + frontend (Streamlit, React, Next.js, etc.)
   - **PROCESSING & QUEUE LAYER** — Semaphore-guarded CPU tasks, Celery/Bull/Kafka workers
   - **AI / INTELLIGENCE LAYER** — LLM providers, embedding, evaluation framework
   - **STORAGE & PERSISTENCE** — vector DB, relational DB, NoSQL, Redis, S3

3. **Data Flow Paths** — step-by-step cards per detected flow:
   - Write Path (webhooks → sanitize → chunk → embed → index)
   - Read Path (query → cache? → vector search → LLM → score)
   - Queue/Background Jobs (enqueue → worker → persist)
   - Generic HTTP flow (if nothing else detected)

4. **Concurrency Model table** — every layer with model / ceiling / limiting factor / code reference

5. **Bottleneck Analysis** — ranked bar cards (CRITICAL → LOW) with mitigation notes

## What the analyzer detects

### Workers & replicas
| Signal | Detected from |
|---|---|
| `uvicorn --workers N` | Dockerfile, docker-compose, Procfile |
| `gunicorn -w N` | same + gunicorn.conf.py |
| `replicas: N` | docker-compose |
| PM2 `instances: N` | ecosystem.config.js |
| Celery `-c N` / `concurrency=N` | docker-compose, Python files |

### Async concurrency model
| Signal | Meaning |
|---|---|
| `asyncio.Semaphore(N)` | Hard cap on concurrent CPU tasks |
| `run_in_executor` | CPU-bound work offloaded to thread pool |
| `asyncio.Lock()` | Exclusive section (e.g. dedup store) |
| `asyncio.gather` | Fan-out async tasks |
| `async def` density > 2 | asyncio event loop model |

### Rate limits
| Source | Detected signal |
|---|---|
| nginx | `limit_req_zone … rate=Xr/m` + `limit_req … burst=N` |
| slowapi (Python) | `@limiter.limit("N per minute")` |
| express-rate-limit | `max: N` in config |

### External sources
Jira · Azure DevOps · Slack · GitHub · Stripe · Salesforce · Twilio · S3 · Users/clients · Cron/Scheduler

### LLM providers
OpenAI (ChatOpenAI / gpt-*) · Anthropic (Claude) · Cohere · AWS Bedrock

### Vector stores
Qdrant · Pinecone · Weaviate · ChromaDB · pgvector · FAISS · Milvus

### Databases
PostgreSQL · MySQL · MongoDB · SQLite · Redis

### Queues
Celery · BullMQ · Kafka · RabbitMQ · RQ · AWS SQS

### Evaluation frameworks
TruLens · RAGAS · LangSmith

## Concurrency calculation

```
total_workers      = (uvicorn_workers + gunicorn_workers) × replicas
per_worker_io      = 100 if asyncio else 1
total_io_concurrent= total_workers × per_worker_io
practical_limit    = min(rate_limit, external_api_rpm, semaphore × total_workers)
```

For LLM-backed services, the practical ceiling is almost always the LLM inference latency
(3–30s per call) rather than the application layer. The semantic cache bypass rate (if
detected) directly multiplies effective throughput.

## Design tokens (dark mode — same as TECH_STACK.html)

| CSS variable | Value |
|---|---|
| `--bg` | `#0f172a` |
| `--bg3` | `#161e2e` |
| `--border` | `#1e293b` |
| `--text` | `#f1f5f9` |
| `--muted` | `#64748b` |
| `--mono` | `'JetBrains Mono', monospace` |
| `--sans` | `'IBM Plex Sans', system-ui, sans-serif` |

Accent colors (consistent with `WORKFLOW.html` reference output):
- Orange `#f97316` — write/ingestion path, external sources
- Blue `#3b82f6` — API layer, relational DBs
- Green `#22c55e` — read/query path, user-facing components
- Purple `#a855f7` — processing, Slack, queues
- Pink `#ec4899` — LLM / inference
- Indigo `#818cf8` — vector stores
- Yellow `#eab308` — evaluation, schedulers
- Red `#ef4444` — Redis, bottlenecks
- Cyan `#06b6d4` — embedding, I/O stats

## Fallback (script not found)

If `~/.claude/skills/workflow-generator/scripts/analyze.py` cannot be found, perform the
analysis manually using your Read and Bash tools, then write `WORKFLOW.html` directly.

**Manual analysis steps:**

1. **Detect framework** — grep for `fastapi`, `flask`, `django`, `express`, `gin`, `@SpringBoot`
2. **Detect workers** — grep `--workers`, `replicas:`, `pm2 instances` in docker-compose / Procfiles
3. **Detect gateway** — look for `nginx.conf`, `Caddyfile`, `traefik.yml`
4. **Extract rate limits** — `limit_req_zone`, `@limiter.limit`, `express-rate-limit`
5. **Extract async primitives** — `asyncio.Semaphore`, `run_in_executor`, `asyncio.gather`
6. **Detect LLM** — `ChatOpenAI`, `ChatAnthropic`, `request_timeout=`, `max_retries=`
7. **Detect storage** — scan docker-compose, .env for `postgres://`, `redis://`, `qdrant`, `pinecone`
8. **Detect queues** — `celery`, `bullmq`, `kafka`, `rabbitmq`
9. **Detect external sources** — `jira`, `slack`, `ado`, `github`, `stripe` in source + env

Then write `WORKFLOW.html` using the exact design tokens above and the section structure:
stat-row → architecture diagram → flow cards → concurrency table → bottleneck bars → footer.

## Notes

- Always overwrite an existing `WORKFLOW.html` — never ask for confirmation
- Works on Python, Node.js, Go, Rust, Java, Ruby projects
- Architecture diagram adapts to what is detected: layers with no components are omitted
- Stat cards show only metrics that could be computed (skip if data unavailable)
- Never scan vendored or generated directories (`node_modules`, `venv`, `.venv`,
  `site-packages`, `dist`, `build`, `.git`, …) — only the project's own source
- Capacity figures are static-analysis heuristics (e.g. ~100 concurrent tasks per
  async worker), not load-test results — present them as estimates
