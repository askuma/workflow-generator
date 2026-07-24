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
  architecture", "draw the architecture", "explain the system design", "infrastructure diagram",
  "dependency graph", "call graph", "module graph", "what imports what", "import graph".

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

   Optional flags, appended after the two positional args:
   - `--access-log <path>` — overlay real request counts (from a combined/common log file) onto
     the codebase dependency graph's HTTP-entry edges, instead of import-direction only.
   - `--graph-detail auto|files|dirs` — force file-level or directory-level graph nodes. Default
     `auto` aggregates to directories once a project exceeds ~350 source files.

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
   - Write Path (webhook route + signature-check evidence, if any)
   - Read Path (LLM + vector store presence)
   - Queue/Background Jobs
   - Generic HTTP flow (if nothing else detected)

   These cards combine genuinely detected facts (provider names, models, timeouts,
   specific routes, real HMAC-verification evidence) with the *typical* shape of that
   kind of component. They are not a trace of an actual request path through the code —
   the tool never confirms that a detected webhook source and a detected route are
   the same request. Card titles say "(inferred, not traced)" or "(typical pattern)"
   for exactly this reason, and individual steps say "not confirmed" wherever the
   claim isn't backed by direct evidence.

4. **Concurrency Model table** — every layer with model / ceiling / limiting factor (a category label, not a file:line pointer into the user's code)

5. **Bottleneck Analysis** — ranked bar cards (CRITICAL → LOW). Severities are derived
   from the same min() comparison used for the "Practical Throughput" stat, so this
   section and that stat can never disagree with each other.

6. **Codebase Dependency Graph** — a force-directed graph of every source file (Python, JS/TS,
   Go, Java, Rust, Ruby) as a node and every real, parser-resolved import as an edge; files that
   match an already-detected component (an LLM call, a database client, a queue) also get an edge
   to that component. Click a node to isolate its neighbors; hover for file details. Large
   projects (350+ files) are aggregated to directory-level nodes automatically. Edges are
   import-direction only (static, honest) unless `--access-log` was supplied, in which case
   HTTP-entry edges are weighted with real observed request counts — the graph is explicit about
   which kind of edge is which so it's never mistaken for a traced request path.

7. **Guided tour** — a spotlight walkthrough that dims the page and steps through each section
   in turn (Back/Next/Skip), shown automatically the first time a generated report is opened.
   Steps for sections that don't apply to a given project (e.g. no detected routes, no graph)
   are skipped automatically. Replayable anytime via the `?` button next to the theme toggle.

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
total_workers       = (uvicorn_workers + gunicorn_workers) × replicas
per_worker_io       = 100 if asyncio else 1
total_io_concurrent = total_workers × per_worker_io
concurrency_ceiling = min(total_io_concurrent, semaphore × total_workers)   # whichever is present
```

`practical_limit` is a genuine `min()` across every throughput-shaped constraint that
was actually detected — not a priority-ordered guess that stops at the first match:

```
candidates = []
if nginx/Caddy rate limit detected:      candidates += gateway_rate (r/m, parsed from config)
if slowapi/express rate limit detected:  candidates += app_rate (r/m)
if an LLM provider was detected:         candidates += concurrency_ceiling × (60 / timeout)
practical_limit = min(candidates) if candidates else concurrency_ceiling
```

The LLM term ties the throughput estimate to this project's actually-detected worker
count and async model — it no longer produces the same number regardless of whether
the app runs one sync worker or sixteen async ones. Whichever candidate is tightest is
reported as the bottleneck, and the "Bottleneck Analysis" section ranks the *same*
candidate list, so the two sections of the page cannot disagree with each other.

This is still a static-analysis heuristic, not a load test — it has no visibility into
CPU/memory limits, downstream database latency, or GC pauses. Treat it as a fast sanity
check on where to look first, not a capacity-planning number to put in an SLA.

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
