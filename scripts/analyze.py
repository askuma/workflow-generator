#!/usr/bin/env python3
"""
workflow-generator — project workflow analyzer
Scans a project directory, detects all components and their communication
patterns, computes concurrent request capacity, and writes WORKFLOW.html.

Usage:
    python3 analyze.py [project_dir] [output_file]
"""

import datetime, json, re, sys
from pathlib import Path

# ── Design tokens (identical to generated WORKFLOW.html) ─────────────────────
C = {
    'orange': '#f97316', 'orange_d': '#1a1208',
    'blue':   '#3b82f6', 'blue_d':   '#0f1a2e',
    'purple': '#a855f7', 'purple_d': '#1a0f2e',
    'green':  '#22c55e', 'green_d':  '#0a1a0e',
    'red':    '#ef4444', 'red_d':    '#1a0808',
    'yellow': '#eab308', 'yellow_d': '#1a1408',
    'cyan':   '#06b6d4', 'cyan_d':   '#061a20',
    'indigo': '#818cf8', 'indigo_d': '#0f1040',
    'pink':   '#ec4899', 'pink_d':   '#1a0818',
    'gray':   '#94a3b8', 'gray_d':   '#1a2535',
}

# ── Pattern library ───────────────────────────────────────────────────────────
_RE = {
    # Workers & replicas
    'uvicorn_workers':  re.compile(r'--workers[=\s]+(\d+)', re.I),
    'gunicorn_workers': re.compile(r'gunicorn.*?-w\s+(\d+)|-w\s+(\d+).*?gunicorn|workers\s*=\s*(\d+)', re.I),
    'replicas':         re.compile(r'replicas:\s*(\d+)'),
    'pm2_instances':    re.compile(r'instances\s*:\s*(\d+)'),
    'celery_concur':    re.compile(r'-c\s+(\d+)|--concurrency\s*=?\s*(\d+)|concurrency\s*=\s*(\d+)'),
    # Async primitives
    'semaphore':        re.compile(r'Semaphore\(\s*(\d+)\s*\)'),
    'asyncio_lock':     re.compile(r'asyncio\.Lock\(\)'),
    'run_in_executor':  re.compile(r'run_in_executor'),
    'asyncio_gather':   re.compile(r'asyncio\.gather'),
    'async_def':        re.compile(r'^async\s+def\s+', re.M),
    # Rate limiting — nginx
    'nginx_rate_zone':  re.compile(r'limit_req_zone\s+\$[^\s]+\s+zone=(\w+)[^;]+rate=(\d+)r/([ms])'),
    'nginx_rate_use':   re.compile(r'limit_req\s+zone=(\w+)[^;]*burst=(\d+)'),
    'nginx_worker_conn':re.compile(r'worker_connections\s+(\d+)'),
    # Rate limiting — Python
    'slowapi_limit':    re.compile(r'@limiter\.limit\(["\'](\d+)\s*per\s*(\w+)["\']'),
    'py_ratelimit':     re.compile(r'RateLimiter[^)]*requests=(\d+)[^)]*period=(\d+)'),
    # Rate limiting — Express
    'express_rl':       re.compile(r'max\s*:\s*(\d+)'),
    # LLM
    'openai_chat':      re.compile(r'ChatOpenAI|openai\.OpenAI|AzureChatOpenAI', re.I),
    'anthropic_chat':   re.compile(r'ChatAnthropic|anthropic\.Anthropic', re.I),
    'cohere_chat':      re.compile(r'ChatCohere|cohere\.Client', re.I),
    'bedrock_chat':     re.compile(r'ChatBedrock|boto3.*bedrock', re.I),
    'llm_timeout':      re.compile(r'request_timeout\s*=\s*(\d+)|timeout\s*=\s*(\d+)'),
    'llm_retries':      re.compile(r'max_retries\s*=\s*(\d+)'),
    'model_name':       re.compile(r'["\']?(gpt-4o?(?:-mini|-turbo)?|gpt-3\.5[^"\']+|claude-[^"\']+|mistral[^"\']+|llama[^"\']+|command[^"\']+)["\']?', re.I),
    # Cache
    'redis_cache':      re.compile(r'redis://|RedisCache|aioredis|redis\.Redis', re.I),
    'semantic_cache':   re.compile(r'semantic.?cache|cosine.?sim|similarity.?thresh', re.I),
    'cache_thresh':     re.compile(r'similarity.?threshold\s*=\s*([\d.]+)|threshold\s*=\s*([\d.]+)'),
    'cache_ttl':        re.compile(r'ttl\s*=\s*(\d+)|TTL\s*=\s*(\d+)'),
    # Vector store
    'qdrant':           re.compile(r'qdrant', re.I),
    'pinecone':         re.compile(r'pinecone', re.I),
    'weaviate':         re.compile(r'weaviate', re.I),
    'chromadb':         re.compile(r'chroma', re.I),
    'pgvector':         re.compile(r'pgvector|vector.*postgres', re.I),
    'faiss':            re.compile(r'faiss', re.I),
    'milvus':           re.compile(r'milvus', re.I),
    # Databases
    'postgres':         re.compile(r'postgresql://|postgres://|psycopg|image:\s*postgres', re.I),
    'mysql':            re.compile(r'mysql://|pymysql|image:\s*mysql', re.I),
    'mongo':            re.compile(r'mongodb://|pymongo|motor|image:\s*mongo', re.I),
    'sqlite':           re.compile(r'sqlite://', re.I),
    'redis_db':         re.compile(r'image:\s*redis|redis://\s*$', re.I | re.M),
    # Queues
    'celery':           re.compile(r'celery', re.I),
    'bull':             re.compile(r'bullmq|bull\.Queue', re.I),
    'kafka':            re.compile(r'kafka', re.I),
    'rabbitmq':         re.compile(r'rabbitmq|pika|amqp://', re.I),
    'redis_queue':      re.compile(r'rq\.|from rq |RedisQueue', re.I),
    'sqs':              re.compile(r'boto3.*sqs|SQSClient|aws.*sqs', re.I),
    # External sources
    'jira':             re.compile(r'jira|atlassian', re.I),
    'ado':              re.compile(r'azure.?devops|dev\.azure\.com|AzureDevOps', re.I),
    'slack':            re.compile(r'slack', re.I),
    'github':           re.compile(r'github|octokit|PyGithub', re.I),
    'stripe':           re.compile(r'stripe', re.I),
    'salesforce':       re.compile(r'salesforce|simple_salesforce', re.I),
    'twilio':           re.compile(r'twilio', re.I),
    'sendgrid':         re.compile(r'sendgrid|mailgun|SES.*email', re.I),
    's3':               re.compile(r'boto3.*s3|s3://|S3Client', re.I),
    # Auth
    'jwt':              re.compile(r'JWT|PyJWT|jsonwebtoken|jose', re.I),
    'oauth':            re.compile(r'oauth|OAuth', re.I),
    'hmac_sig':         re.compile(r'HMAC|hmac\.new|X-Hub-Signature|signing.?secret', re.I),
    'api_key_auth':     re.compile(r'api.key|APIKey|api_key.*header', re.I),
    # API routes — Python
    'fastapi_route':    re.compile(r'@(?:app|router)\.(get|post|put|delete|patch|websocket)\s*\(\s*["\']([^"\']+)["\']'),
    'flask_route':      re.compile(r'@app\.route\s*\(\s*["\']([^"\']+)["\']'),
    'django_path':      re.compile(r"(?:path|re_path|url)\s*\(\s*['\"]([^'\"]+)['\"]"),
    # API routes — Node.js
    'express_route':    re.compile(r'(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'),
    # Webhooks
    'webhook_path':     re.compile(r'/webhook[s]?/?', re.I),
    # Framework detection
    'fastapi_import':   re.compile(r'from fastapi import|import fastapi', re.I),
    'flask_import':     re.compile(r'from flask import|import flask', re.I),
    'django_import':    re.compile(r'from django|import django', re.I),
    'express_require':  re.compile(r"require\(['\"]express['\"]"),
    'gin_import':       re.compile(r'"github.com/gin-gonic/gin"'),
    'spring_annot':     re.compile(r'@RestController|@SpringBootApplication'),
    'rails_route':      re.compile(r'Rails\.application\.routes'),
    # Embedding
    'openai_embed':     re.compile(r'text-embedding|OpenAIEmbeddings', re.I),
    'cohere_embed':     re.compile(r'embed-english|CohereEmbeddings', re.I),
    'hf_embed':         re.compile(r'HuggingFaceEmbeddings|sentence-transformers', re.I),
    # Evaluation
    'trulens':          re.compile(r'trulens', re.I),
    'ragas':            re.compile(r'ragas', re.I),
    'langsmith':        re.compile(r'langsmith', re.I),
    # Ingestion patterns
    'batch_size':       re.compile(r'batch.?size\s*=\s*(\d+)|BATCH.?SIZE\s*=\s*(\d+)', re.I),
    'chunk_size':       re.compile(r'chunk.?size\s*=\s*(\d+)|CHUNK.?SIZE\s*=\s*(\d+)', re.I),
    # Prometheus
    'prometheus':       re.compile(r'prometheus|prom_client|Prometheus', re.I),
    # Nginx
    'nginx_upstream':   re.compile(r'upstream\s+(\w+)'),
}


# Directories that contain third-party or generated code, never the project's own
# architecture. Scanning them makes every dependency's feature list look like a
# component of the project (e.g. a local venv with langchain installed would
# "detect" every vector store langchain supports).
EXCLUDED_DIRS = frozenset({
    '.git', '.hg', '.svn',
    'node_modules', 'bower_components',
    'site-packages', 'dist-packages',
    'venv', '.venv', 'env', 'virtualenv',
    '__pycache__', '.mypy_cache', '.pytest_cache', '.ruff_cache', '.tox', '.nox',
    'dist', 'build', 'target', '.next', '.nuxt', '.output',
    'vendor', 'third_party', '.terraform',
    'htmlcov', 'coverage', '.cache',
})


def _is_excluded(root: Path, p: Path) -> bool:
    parents = p.relative_to(root).parts[:-1]
    return any(d in EXCLUDED_DIRS or d.endswith('.egg-info') for d in parents)


def _read_all(root: Path, pattern: str) -> str:
    """Read all matching files (skipping vendored/venv dirs) and concatenate their contents."""
    parts = []
    for p in root.rglob(pattern):
        if _is_excluded(root, p):
            continue
        try:
            parts.append(p.read_text(errors='ignore'))
        except Exception:
            pass
    return '\n'.join(parts)


def _read_file(root: Path, *names: str) -> str:
    for name in names:
        p = root / name
        if p.exists():
            try:
                return p.read_text(errors='ignore')
            except Exception:
                pass
    return ''


def _read_manifests(root: Path) -> str:
    """Dependency manifests: packages declared here are first-party signal,
    unlike the same names appearing inside vendored dependency source."""
    parts = []
    for name in ('requirements.txt', 'requirements-dev.txt', 'pyproject.toml',
                 'package.json', 'go.mod', 'Cargo.toml', 'Gemfile'):
        p = root / name
        if p.exists():
            try:
                parts.append(p.read_text(errors='ignore'))
            except Exception:
                pass
    return '\n'.join(parts)


def _first_int(m: re.Match | None) -> int | None:
    if not m:
        return None
    for g in m.groups():
        if g and g.isdigit():
            return int(g)
    return None


# ── Detectors ─────────────────────────────────────────────────────────────────

def detect_project_name(root: Path) -> str:
    pj = _read_file(root, 'package.json')
    if pj:
        try:
            return json.loads(pj).get('name', '') or ''
        except Exception:
            pass
    return root.resolve().name.replace('-', ' ').replace('_', ' ').title()


def detect_workers(root: Path) -> dict:
    compose = _read_file(root, 'docker-compose.prod.yml', 'docker-compose.yml', 'docker-compose.yaml')
    proc = _read_file(root, 'Procfile', 'procfile')
    gunicorn_conf = _read_all(root, 'gunicorn*.py') + _read_all(root, 'gunicorn*.conf')

    uv = _first_int(_RE['uvicorn_workers'].search(compose + proc))
    gu = _first_int(_RE['gunicorn_workers'].search(compose + proc + gunicorn_conf))
    replicas = _first_int(_RE['replicas'].search(compose))
    pm2 = _first_int(_RE['pm2_instances'].search(_read_all(root, 'ecosystem*.js') + _read_all(root, 'ecosystem*.config.js')))
    celery_c = _first_int(_RE['celery_concur'].search(_read_all(root, '*.py') if not uv and not gu else compose))

    # Detect async model
    py_src = _read_all(root, '*.py')
    js_src = _read_all(root, '*.js') + _read_all(root, '*.ts')
    async_count = len(_RE['async_def'].findall(py_src))
    is_async = async_count > 2 or bool(_RE['fastapi_import'].search(py_src))

    return {
        'uvicorn_workers': uv,
        'gunicorn_workers': gu,
        'replicas': replicas or 1,
        'pm2_instances': pm2,
        'celery_workers': celery_c,
        'is_async': is_async,
        'async_def_count': async_count,
    }


def detect_gateway(root: Path) -> dict | None:
    # Search recursively for nginx.conf (may be in deploy/, nginx/, config/, etc.)
    nginx_conf = _read_all(root, 'nginx.conf') or _read_all(root, '*.nginx')
    caddy = _read_file(root, 'Caddyfile') or _read_all(root, 'Caddyfile')
    traefik = _read_file(root, 'traefik.yml', 'traefik.yaml') or _read_all(root, 'traefik.yml')
    compose = _read_file(root, 'docker-compose.prod.yml', 'docker-compose.yml', 'docker-compose.yaml')

    has_nginx = bool(nginx_conf) or 'nginx' in compose.lower()
    has_caddy = bool(caddy)
    has_traefik = bool(traefik)

    gw_type = ('nginx' if has_nginx else 'Caddy' if has_caddy else 'Traefik' if has_traefik else None)
    if not gw_type:
        return None

    # Rate limits from nginx
    rate_limits = []
    zones = {}
    for m in _RE['nginx_rate_zone'].finditer(nginx_conf):
        zone_name, rate, unit = m.groups()
        zones[zone_name] = f"{rate}r/{unit}"
    for m in _RE['nginx_rate_use'].finditer(nginx_conf):
        zone_name, burst = m.group(1), m.group(2)
        rate = zones.get(zone_name, '?r/m')
        rate_limits.append({'zone': zone_name, 'rate': rate, 'burst': int(burst)})

    worker_conn = _first_int(_RE['nginx_worker_conn'].search(nginx_conf))

    return {
        'type': gw_type,
        'rate_limits': rate_limits,
        'worker_connections': worker_conn,
        'tls': 'ssl_certificate' in nginx_conf or 'tls' in caddy.lower(),
    }


def detect_api_server(root: Path) -> dict:
    py_src = _read_all(root, '*.py')
    js_src = _read_all(root, '*.js') + _read_all(root, '*.ts')
    go_src = _read_all(root, '*.go')
    java_src = _read_all(root, '*.java')

    framework = 'unknown'
    if _RE['fastapi_import'].search(py_src):
        framework = 'FastAPI'
    elif _RE['flask_import'].search(py_src):
        framework = 'Flask'
    elif _RE['django_import'].search(py_src):
        framework = 'Django'
    elif _RE['express_require'].search(js_src):
        framework = 'Express'
    elif _RE['gin_import'].search(go_src):
        framework = 'Gin (Go)'
    elif _RE['spring_annot'].search(java_src):
        framework = 'Spring Boot'

    # Routes
    routes = set()
    for m in _RE['fastapi_route'].finditer(py_src):
        routes.add(f"{m.group(1).upper()} {m.group(2)}")
    for m in _RE['flask_route'].finditer(py_src):
        routes.add(f"* {m.group(1)}")
    for m in _RE['express_route'].finditer(js_src):
        routes.add(f"{m.group(1).upper()} {m.group(2)}")

    has_webhooks = any('/webhook' in r.lower() for r in routes) or bool(_RE['webhook_path'].search(py_src + js_src))

    auth = {
        'jwt': bool(_RE['jwt'].search(py_src + js_src)),
        'oauth': bool(_RE['oauth'].search(py_src + js_src)),
        'hmac': bool(_RE['hmac_sig'].search(py_src + js_src)),
        'api_key': bool(_RE['api_key_auth'].search(py_src + js_src)),
    }

    has_prometheus = bool(_RE['prometheus'].search(py_src + js_src))

    # Slowapi / express-rate-limit
    app_rate_limits = []
    for m in _RE['slowapi_limit'].finditer(py_src):
        app_rate_limits.append({'rate': m.group(1), 'unit': m.group(2)})

    return {
        'framework': framework,
        'routes': sorted(routes)[:20],
        'has_webhooks': has_webhooks,
        'auth': auth,
        'has_prometheus': has_prometheus,
        'app_rate_limits': app_rate_limits,
    }


def detect_frontend(root: Path) -> list:
    py_src = _read_all(root, '*.py')
    js_src = _read_all(root, '*.js') + _read_all(root, '*.ts') + _read_all(root, '*.tsx') + _read_all(root, '*.jsx')
    compose = _read_file(root, 'docker-compose.prod.yml', 'docker-compose.yml', 'docker-compose.yaml')
    pkg = _read_file(root, 'package.json')

    fe = []
    if re.search(r'streamlit', py_src + compose, re.I):
        fe.append({'name': 'Streamlit', 'desc': 'Python web dashboard', 'color': 'green'})
    if re.search(r'gradio', py_src + compose, re.I):
        fe.append({'name': 'Gradio', 'desc': 'ML demo interface', 'color': 'orange'})
    if re.search(r'"next"', pkg, re.I) or re.search(r'NextJS|next/app', js_src, re.I):
        fe.append({'name': 'Next.js', 'desc': 'React framework', 'color': 'gray'})
    elif re.search(r'"react"', pkg, re.I) or re.search(r'ReactDOM', js_src, re.I):
        fe.append({'name': 'React', 'desc': 'UI framework', 'color': 'cyan'})
    if re.search(r'"vue"', pkg, re.I):
        fe.append({'name': 'Vue.js', 'desc': 'Progressive UI framework', 'color': 'green'})
    if re.search(r'"svelte"', pkg, re.I):
        fe.append({'name': 'Svelte', 'desc': 'Compiled UI framework', 'color': 'orange'})
    return fe


def detect_concurrency(root: Path) -> dict:
    py_src = _read_all(root, '*.py')
    js_src = _read_all(root, '*.js') + _read_all(root, '*.ts')

    semaphores = [int(m.group(1)) for m in _RE['semaphore'].finditer(py_src)]
    has_lock = bool(_RE['asyncio_lock'].search(py_src))
    has_executor = bool(_RE['run_in_executor'].search(py_src))
    has_gather = bool(_RE['asyncio_gather'].search(py_src))

    batch_size = _first_int(_RE['batch_size'].search(py_src + js_src))
    chunk_size = _first_int(_RE['chunk_size'].search(py_src + js_src))

    return {
        'semaphores': semaphores,
        'has_lock': has_lock,
        'has_executor': has_executor,
        'has_gather': has_gather,
        'batch_size': batch_size,
        'chunk_size': chunk_size,
    }


def detect_llm(root: Path) -> dict:
    py_src = _read_all(root, '*.py')
    js_src = _read_all(root, '*.js') + _read_all(root, '*.ts')
    all_src = py_src + js_src

    providers = []
    if _RE['openai_chat'].search(all_src):
        providers.append('OpenAI')
    if _RE['anthropic_chat'].search(all_src):
        providers.append('Anthropic')
    if _RE['cohere_chat'].search(all_src):
        providers.append('Cohere')
    if _RE['bedrock_chat'].search(all_src):
        providers.append('AWS Bedrock')

    timeout = _first_int(_RE['llm_timeout'].search(all_src))
    retries = _first_int(_RE['llm_retries'].search(all_src))

    models = list({m.group(1) for m in _RE['model_name'].finditer(all_src)})[:3]

    embedding = []
    if _RE['openai_embed'].search(all_src):
        embedding.append('OpenAI text-embedding-3')
    if _RE['cohere_embed'].search(all_src):
        embedding.append('Cohere embed-english-v3')
    if _RE['hf_embed'].search(all_src):
        embedding.append('HuggingFace Embeddings')

    eval_framework = None
    if _RE['trulens'].search(all_src):
        eval_framework = 'TruLens RAG Triad'
    elif _RE['ragas'].search(all_src):
        eval_framework = 'RAGAS'
    elif _RE['langsmith'].search(all_src):
        eval_framework = 'LangSmith'

    return {
        'providers': providers,
        'timeout': timeout,
        'retries': retries,
        'models': models,
        'embedding': embedding,
        'eval_framework': eval_framework,
    }


def detect_storage(root: Path) -> list:
    compose = _read_file(root, 'docker-compose.prod.yml', 'docker-compose.yml', 'docker-compose.yaml')
    env = _read_file(root, '.env', '.env.example', '.env.sample')
    py_src = _read_all(root, '*.py')
    js_src = _read_all(root, '*.js') + _read_all(root, '*.ts')
    all_src = compose + env + py_src + js_src + _read_manifests(root)

    stores = []
    if _RE['qdrant'].search(all_src):
        stores.append({'name': 'Qdrant', 'type': 'vector', 'desc': 'HNSW vector DB', 'color': 'indigo'})
    if _RE['pinecone'].search(all_src):
        stores.append({'name': 'Pinecone', 'type': 'vector', 'desc': 'Managed vector DB', 'color': 'indigo'})
    if _RE['weaviate'].search(all_src):
        stores.append({'name': 'Weaviate', 'type': 'vector', 'desc': 'Vector DB', 'color': 'indigo'})
    if _RE['chromadb'].search(all_src):
        stores.append({'name': 'ChromaDB', 'type': 'vector', 'desc': 'Embedded vector DB', 'color': 'indigo'})
    if _RE['pgvector'].search(all_src):
        stores.append({'name': 'pgvector', 'type': 'vector', 'desc': 'Postgres vector ext', 'color': 'indigo'})
    if _RE['faiss'].search(all_src):
        stores.append({'name': 'FAISS', 'type': 'vector', 'desc': 'In-process ANN search', 'color': 'indigo'})
    if _RE['milvus'].search(all_src):
        stores.append({'name': 'Milvus', 'type': 'vector', 'desc': 'Distributed vector DB', 'color': 'indigo'})
    if _RE['postgres'].search(all_src):
        stores.append({'name': 'PostgreSQL', 'type': 'relational', 'desc': 'Primary database', 'color': 'blue'})
    if _RE['mysql'].search(all_src):
        stores.append({'name': 'MySQL', 'type': 'relational', 'desc': 'Relational database', 'color': 'blue'})
    if _RE['mongo'].search(all_src):
        stores.append({'name': 'MongoDB', 'type': 'nosql', 'desc': 'Document store', 'color': 'green'})
    if _RE['sqlite'].search(all_src):
        stores.append({'name': 'SQLite', 'type': 'relational', 'desc': 'Embedded / dev DB', 'color': 'gray'})
    if _RE['redis_cache'].search(all_src) or _RE['redis_db'].search(all_src):
        stores.append({'name': 'Redis', 'type': 'cache', 'desc': 'Cache / pub-sub', 'color': 'red'})
    if _RE['s3'].search(all_src):
        stores.append({'name': 'S3 / Object Store', 'type': 'object', 'desc': 'File storage', 'color': 'yellow'})
    return stores


def detect_queues(root: Path) -> list:
    all_src = _read_all(root, '*.py') + _read_all(root, '*.js') + _read_all(root, '*.ts')
    compose = _read_file(root, 'docker-compose.prod.yml', 'docker-compose.yml')
    combined = all_src + compose + _read_manifests(root)

    queues = []
    if _RE['celery'].search(combined):
        queues.append({'name': 'Celery', 'desc': 'Distributed task queue', 'color': 'green'})
    if _RE['bull'].search(combined):
        queues.append({'name': 'BullMQ', 'desc': 'Node.js job queue (Redis)', 'color': 'red'})
    if _RE['kafka'].search(combined):
        queues.append({'name': 'Kafka', 'desc': 'Event streaming', 'color': 'gray'})
    if _RE['rabbitmq'].search(combined):
        queues.append({'name': 'RabbitMQ', 'desc': 'AMQP message broker', 'color': 'orange'})
    if _RE['redis_queue'].search(combined):
        queues.append({'name': 'RQ (Redis Queue)', 'desc': 'Simple Redis job queue', 'color': 'red'})
    if _RE['sqs'].search(combined):
        queues.append({'name': 'AWS SQS', 'desc': 'Managed message queue', 'color': 'yellow'})
    return queues


def detect_external_sources(root: Path) -> list:
    all_src = _read_all(root, '*.py') + _read_all(root, '*.js') + _read_all(root, '*.ts')
    env = _read_file(root, '.env', '.env.example', '.env.sample')
    combined = all_src + env + _read_manifests(root)

    sources = []
    if _RE['jira'].search(combined):
        sources.append({'name': 'Jira', 'proto': 'Webhook + REST', 'auth': 'HMAC-SHA256', 'color': 'blue'})
    if _RE['ado'].search(combined):
        sources.append({'name': 'Azure DevOps', 'proto': 'Service Hooks + REST', 'auth': 'SHA1 secret', 'color': 'blue'})
    if _RE['slack'].search(combined):
        sources.append({'name': 'Slack', 'proto': 'Events API', 'auth': 'Signing secret', 'color': 'purple'})
    if _RE['github'].search(combined):
        sources.append({'name': 'GitHub', 'proto': 'Webhooks + API', 'auth': 'HMAC-SHA256', 'color': 'gray'})
    if _RE['stripe'].search(combined):
        sources.append({'name': 'Stripe', 'proto': 'Webhooks + API', 'auth': 'Webhook sig', 'color': 'purple'})
    if _RE['salesforce'].search(combined):
        sources.append({'name': 'Salesforce', 'proto': 'REST / SOAP', 'auth': 'OAuth2', 'color': 'blue'})
    if _RE['twilio'].search(combined):
        sources.append({'name': 'Twilio', 'proto': 'SMS / Voice API', 'auth': 'Account SID', 'color': 'red'})

    # Always add "Users / API Clients"
    sources.append({'name': 'Users / API Clients', 'proto': 'HTTPS / WebSocket', 'auth': 'JWT', 'color': 'green'})

    if re.search(r'cron|schedule|APScheduler|celery.*beat|crontab', all_src, re.I):
        sources.append({'name': 'Cron / Scheduler', 'proto': 'Internal trigger', 'auth': '—', 'color': 'yellow'})
    return sources


# ── Concurrency calculation ────────────────────────────────────────────────────

def compute_concurrency(workers: dict, gateway: dict | None, concur: dict, llm: dict) -> dict:
    uv = workers.get('uvicorn_workers') or 1
    gu = workers.get('gunicorn_workers') or (1 if not workers.get('uvicorn_workers') else 0)
    replicas = workers.get('replicas') or 1
    pm2 = workers.get('pm2_instances') or 1
    is_async = workers.get('is_async', False)

    # Total worker processes
    if workers.get('uvicorn_workers') or workers.get('gunicorn_workers'):
        total_workers = (uv + gu) * replicas
    elif workers.get('pm2_instances'):
        total_workers = pm2
    else:
        total_workers = 1

    # Per-worker concurrent I/O
    per_worker_io = 100 if is_async else 1

    # Total theoretical I/O concurrent
    total_io = total_workers * per_worker_io

    # Semaphore effective limit
    sem_limit = min(concur.get('semaphores', [999])) if concur.get('semaphores') else None

    # Practical throughput estimate
    # If LLM: ~50-200 req/min limited by OpenAI
    # If DB-only: much higher
    if llm.get('providers'):
        timeout = llm.get('timeout') or 30
        practical = f"~{max(10, 60 // max(timeout // 10, 1))}–{max(50, 600 // max(timeout // 10, 1))}/min"
        bottleneck = llm['providers'][0]
    elif sem_limit:
        practical = f"~{sem_limit * total_workers} concurrent tasks"
        bottleneck = 'Semaphore limit'
    else:
        practical = f"~{total_io} concurrent I/O"
        bottleneck = 'I/O event loop'

    # Rate limits
    rate_limit_str = None
    if gateway and gateway.get('rate_limits'):
        rl = gateway['rate_limits'][0]
        rate_limit_str = f"{rl['rate']} burst={rl['burst']}"

    return {
        'total_workers': total_workers,
        'per_worker_io': per_worker_io,
        'total_io': total_io,
        'sem_limit': sem_limit,
        'practical': practical,
        'bottleneck': bottleneck,
        'rate_limit_str': rate_limit_str,
        'worker_connections': gateway.get('worker_connections') if gateway else None,
        'is_async': is_async,
    }


# ── Flow inference ─────────────────────────────────────────────────────────────

def infer_flows(analysis: dict) -> list:
    flows = []
    api = analysis['api_server']
    llm = analysis['llm']
    ext = analysis['external_sources']
    queues = analysis['queues']
    storage = analysis['storage']
    concur = analysis['concurrency']
    gateway = analysis['gateway']

    # Write path: webhooks / ingestion
    webhook_sources = [s for s in ext if s.get('proto', '').lower().startswith('webhook') or 'webhook' in s.get('proto', '').lower()]
    if api.get('has_webhooks') or webhook_sources:
        steps = []
        if webhook_sources:
            steps.append({'title': f"{' / '.join(s['name'] for s in webhook_sources[:2])} fires webhook",
                          'desc': f"POST to /{analysis['api_server']['routes'][0].split()[1].strip('/').split('/')[0] if analysis['api_server']['routes'] else 'webhooks'}. Signature verified immediately.",
                          'code': ', '.join(s['auth'] for s in webhook_sources[:2] if s.get('auth') and s['auth'] != '—')[:40] or None})
        steps.append({'title': 'Instant acknowledgment', 'desc': 'API returns 202 immediately — processing continues async in event loop', 'code': '202 Accepted'})
        if concur.get('semaphores'):
            steps.append({'title': 'Privacy / preprocessing', 'desc': f"CPU-bound tasks offloaded to thread pool. Max {concur['semaphores'][0]} concurrent tasks (Semaphore).", 'code': f"Semaphore({concur['semaphores'][0]})"})
        vector_stores = [s for s in storage if s['type'] == 'vector']
        if vector_stores:
            steps.append({'title': 'Chunk → Embed → Index', 'desc': f"Text split into chunks. Embedded and upserted to {vector_stores[0]['name']}.", 'code': f"batch: {concur.get('batch_size') or 100} vectors"})
        flows.append({'title': 'Write Path — Webhook Ingestion', 'color': 'orange', 'steps': steps})

    # Read path: RAG query
    vector_stores = [s for s in storage if s['type'] == 'vector']
    if llm.get('providers') and vector_stores:
        steps = [
            {'title': 'Query from user / dashboard', 'desc': 'Auth token validated, user scope extracted (RBAC)', 'code': None},
            {'title': 'Semantic cache check', 'desc': f"Query embedded and compared against cache. Cache hit → return immediately (no LLM call).", 'code': 'cosine sim ≥ threshold'},
            {'title': f"Vector search in {vector_stores[0]['name']}", 'desc': 'RBAC-filtered similarity search returns top-K relevant chunks. Sub-100ms.', 'code': 'k=8 · metadata filter'},
            {'title': f"{', '.join(llm['providers'][:2])} inference", 'desc': f"LLM generates answer from retrieved context. {'Timeout: ' + str(llm['timeout']) + 's · ' if llm.get('timeout') else ''}Retries: {llm.get('retries') or 3}", 'code': f"{', '.join(llm['models'][:1]) or llm['providers'][0]}"},
        ]
        if llm.get('eval_framework'):
            steps.append({'title': f"{llm['eval_framework']} scoring", 'desc': 'Quality scores computed per response: groundedness, relevance. Logged.', 'code': None})
        flows.append({'title': 'Read Path — AI Query', 'color': 'green', 'steps': steps})

    # Queue / background job flow
    if queues:
        steps = [
            {'title': 'Task enqueued', 'desc': f"API handler publishes job to {queues[0]['name']}. Returns task ID immediately.", 'code': None},
            {'title': 'Worker picks up task', 'desc': f"{queues[0]['name']} worker dequeues and starts processing. Worker concurrency controlled.", 'code': None},
            {'title': 'Result stored', 'desc': 'Output written to database or returned via callback.', 'code': None},
        ]
        flows.append({'title': f"Async Background Jobs — {queues[0]['name']}", 'color': 'purple', 'steps': steps})

    # Generic HTTP flow (always add if nothing else)
    if not flows:
        steps = [
            {'title': 'Client sends request', 'desc': f"HTTPS request to {'nginx' if analysis['gateway'] else 'API server'}", 'code': None},
            {'title': 'Auth & validation', 'desc': f"{'JWT decode, ' if api['auth'].get('jwt') else ''}{'HMAC verify, ' if api['auth'].get('hmac') else ''}request validated", 'code': None},
            {'title': 'Handler executes', 'desc': f"{api['framework']} route handler processes request{', queries DB' if storage else ''}", 'code': None},
            {'title': 'Response returned', 'desc': 'JSON response sent back to client', 'code': None},
        ]
        flows.append({'title': 'HTTP Request Flow', 'color': 'blue', 'steps': steps})

    return flows


# ── HTML rendering ─────────────────────────────────────────────────────────────

CSS = """
:root{--bg:#0f172a;--bg2:#111827;--bg3:#161e2e;--bg4:#1a2535;
--border:#1e293b;--border2:#263347;--text:#f1f5f9;--muted:#64748b;--dim:#334155;
--sans:'IBM Plex Sans',system-ui,sans-serif;--mono:'JetBrains Mono',monospace}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.6}
.page{max-width:1440px;margin:0 auto;padding:40px 32px 80px}
h1{font-size:28px;font-weight:700;color:#f8fafc;margin-bottom:4px}
.subtitle{color:var(--muted);font-size:14px;margin-bottom:40px}
.section{margin-bottom:56px}
.section-title{font-size:13px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;
color:var(--muted);border-bottom:1px solid var(--border);padding-bottom:10px;margin-bottom:24px}
.stat-row{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:40px}
.stat-card{background:var(--bg3);border:1px solid var(--border);border-radius:12px;
padding:20px 24px;flex:1;min-width:160px}
.stat-card .val{font-size:36px;font-weight:700;font-family:var(--mono);line-height:1}
.stat-card .lbl{font-size:12px;color:var(--muted);margin-top:6px}
.stat-card .sub{font-size:11px;color:var(--dim);margin-top:2px;font-family:var(--mono)}
/* Architecture */
.arch-wrap{background:var(--bg3);border:1px solid var(--border);border-radius:14px;
padding:24px;overflow-x:auto}
.arch-layer{margin-bottom:0}
.arch-row-label{font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
color:#334155;margin-bottom:8px;padding-left:4px}
.arch-boxes{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:6px}
.arch-box{border:1.5px solid;border-radius:10px;padding:12px 16px;min-width:160px;flex:1;max-width:280px}
.arch-box .bname{font-weight:700;font-size:13px;margin-bottom:2px}
.arch-box .bdesc{font-size:11px;opacity:.7;margin-bottom:4px}
.arch-box .bcode{font-family:var(--mono);font-size:10px;opacity:.55;margin-top:2px}
.arch-arrow{text-align:center;color:#2d3f55;font-size:20px;line-height:1;padding:4px 0;
user-select:none}
/* Flows */
.flows{display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:20px}
.flow-card{background:var(--bg3);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.flow-header{padding:14px 18px;font-weight:600;font-size:13px;
display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--border)}
.flow-header .dot{width:10px;height:10px;border-radius:50%;flex-shrink:0}
.flow-step{display:flex;align-items:flex-start;gap:12px;padding:9px 18px;
border-bottom:1px solid var(--border)}
.flow-step:last-child{border-bottom:none}
.flow-step:hover{background:var(--bg4)}
.step-num{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;
justify-content:center;font-size:11px;font-weight:700;flex-shrink:0;margin-top:2px;
font-family:var(--mono)}
.step-title{font-weight:600;font-size:13px}
.step-desc{font-size:12px;color:var(--muted);margin-top:1px}
.step-code{font-family:var(--mono);font-size:11px;color:#06b6d4;
background:rgba(6,182,212,.08);border-radius:4px;padding:2px 6px;
margin-top:4px;display:inline-block}
/* Table */
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:11px;font-weight:600;text-transform:uppercase;
letter-spacing:.07em;color:var(--muted);padding:8px 14px;border-bottom:1px solid var(--border)}
td{padding:10px 14px;border-bottom:1px solid var(--border);font-size:13px;vertical-align:top}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--bg4)}
.tbl-wrap{background:var(--bg3);border:1px solid var(--border);border-radius:12px;overflow:hidden}
.tag{display:inline-block;font-family:var(--mono);font-size:11px;padding:2px 8px;
border-radius:4px;font-weight:600}
/* Bottleneck */
.bn-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px}
.bn-card{background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:16px 18px}
.bn-title{font-weight:600;font-size:13px;margin-bottom:8px;display:flex;
justify-content:space-between;align-items:center}
.bn-track{background:#0a0f1a;border-radius:4px;height:8px;margin-bottom:8px;overflow:hidden}
.bn-fill{height:100%;border-radius:4px}
.bn-meta{font-size:12px;color:var(--muted)}
footer{text-align:center;color:var(--dim);font-size:12px;margin-top:60px;
padding-top:20px;border-top:1px solid var(--border)}
code{font-family:var(--mono);font-size:11px;color:#06b6d4}
"""


def _box(name: str, desc: str, color: str, code: str = '', extra_desc: str = '') -> str:
    bg = C.get(f'{color}_d', '#1a2535')
    border = C.get(color, '#475569')
    full_desc = desc
    if extra_desc:
        full_desc = f"{desc} · {extra_desc}"
    code_line = f'<div class="bcode">{code}</div>' if code else ''
    return (
        f'<div class="arch-box" style="background:{bg};border-color:{border}">'
        f'<div class="bname" style="color:{border}">{name}</div>'
        f'<div class="bdesc">{full_desc}</div>{code_line}</div>'
    )


def _arrow() -> str:
    return '<div class="arch-arrow">↓</div>'


def render_arch(analysis: dict) -> str:
    ext = analysis['external_sources']
    gw = analysis['gateway']
    api = analysis['api_server']
    fe = analysis['frontend']
    llm = analysis['llm']
    storage = analysis['storage']
    queues = analysis['queues']
    workers = analysis['workers']
    concur = analysis['concurrency']

    parts = []

    def layer(label: str, boxes: list[str]) -> None:
        parts.append(f'<div class="arch-layer"><div class="arch-row-label">{label}</div>'
                     f'<div class="arch-boxes">{"".join(boxes)}</div></div>')
        parts.append(_arrow())

    # Row 0: External sources
    ext_boxes = []
    for s in ext[:5]:
        ext_boxes.append(_box(s['name'], s['proto'], s['color'], s.get('auth', '') or ''))
    if ext_boxes:
        layer('EXTERNAL SOURCES &amp; CLIENTS', ext_boxes)

    # Row 1: Gateway
    if gw:
        rl_summary = ''
        if gw.get('rate_limits'):
            rl_summary = ' · '.join(f"{r['rate']} burst={r['burst']}" for r in gw['rate_limits'][:2])
        extra = f"TLS · {rl_summary}" if rl_summary else 'TLS termination'
        layer('GATEWAY / REVERSE PROXY', [
            _box(gw['type'], f"worker_connections {gw.get('worker_connections') or '?'}", 'gray', extra)
        ])

    # Row 2: Application
    app_boxes = []
    fw_color = {'FastAPI': 'blue', 'Flask': 'green', 'Django': 'green',
                'Express': 'yellow', 'Gin (Go)': 'cyan', 'Spring Boot': 'orange'}.get(api['framework'], 'blue')
    worker_label = f"{'async ' if workers['is_async'] else ''}{(workers.get('uvicorn_workers') or 1)} worker{'s' if (workers.get('uvicorn_workers') or 1) > 1 else ''} × {workers['replicas']} replica{'s' if workers['replicas'] > 1 else ''}"
    auth_methods = ' · '.join(k for k, v in api['auth'].items() if v)
    app_boxes.append(_box(api['framework'], worker_label, fw_color, auth_methods or ''))
    for f in fe:
        app_boxes.append(_box(f['name'], f['desc'], f['color']))
    layer('APPLICATION LAYER', app_boxes)

    # Row 3: Processing
    proc_boxes = []
    if concur.get('semaphores'):
        proc_boxes.append(_box('Privacy / Preprocessing', 'CPU-bound — thread pool', 'purple',
                               f"Semaphore({min(concur['semaphores'])})"))
    for q in queues:
        proc_boxes.append(_box(q['name'], q['desc'], q['color']))
    if not proc_boxes and api['auth'].get('jwt'):
        proc_boxes.append(_box('Auth Middleware', 'JWT decode · RBAC scope check', 'yellow'))
    if proc_boxes:
        layer('PROCESSING &amp; QUEUE LAYER', proc_boxes)

    # Row 4: Intelligence
    intel_boxes = []
    if llm['providers']:
        for p in llm['providers'][:2]:
            timeout_str = f"timeout={llm['timeout']}s" if llm.get('timeout') else ''
            model_str = ', '.join(llm['models'][:1]) or p
            intel_boxes.append(_box(p, model_str, 'pink', timeout_str))
    if llm.get('embedding'):
        intel_boxes.append(_box('Embedding', llm['embedding'][0], 'cyan',
                                f"batch={concur.get('batch_size') or '?'}"))
    if llm.get('eval_framework'):
        intel_boxes.append(_box(llm['eval_framework'], 'Quality scoring', 'yellow', 'RAG Triad'))
    if intel_boxes:
        layer('AI / INTELLIGENCE LAYER', intel_boxes)

    # Row 5: Storage (no arrow after last)
    if storage:
        store_boxes = [_box(s['name'], s['desc'], s['color']) for s in storage[:6]]
        parts.append(
            f'<div class="arch-layer"><div class="arch-row-label">STORAGE &amp; PERSISTENCE</div>'
            f'<div class="arch-boxes">{"".join(store_boxes)}</div></div>'
        )

    return '\n'.join(parts)


def render_concurrency_table(analysis: dict, cap: dict) -> str:
    rows = ''
    gw = analysis['gateway']
    api = analysis['api_server']
    workers = analysis['workers']
    concur = analysis['concurrency']
    llm = analysis['llm']
    storage = analysis['storage']

    def row(layer, model, ceiling, factor, ref=''):
        tag_col = {'async': '#3b82f6', 'sync': '#f97316', 'cpu': '#a855f7',
                   'limit': '#22c55e', 'external': '#ef4444', 'io': '#06b6d4'}.get(ref, '#475569')
        badge = f'<span class="tag" style="background:rgba({int(tag_col[1:3],16)},{int(tag_col[3:5],16)},{int(tag_col[5:7],16)},.15);color:{tag_col}">{ceiling}</span>'
        return f'<tr><td><strong>{layer}</strong></td><td>{model}</td><td>{badge}</td><td><span style="font-size:12px;color:var(--muted)">{factor}</span></td></tr>'

    if gw:
        rows += row('Nginx / Gateway', 'Event-driven (epoll)',
                    f"{gw.get('worker_connections') or '1024'} connections",
                    f"worker_connections · {'Rate: ' + cap['rate_limit_str'] if cap.get('rate_limit_str') else 'no rate limit detected'}", 'limit')

    worker_str = f"{workers.get('uvicorn_workers') or workers.get('gunicorn_workers') or 1} × {workers['replicas']} = {cap['total_workers']} workers"
    rows += row(f"{analysis['api_server']['framework']} / App Server",
                f"{'asyncio event loop' if workers['is_async'] else 'thread-per-request'}",
                f"~{cap['total_io']} concurrent I/O",
                worker_str, 'async' if workers['is_async'] else 'sync')

    if concur.get('semaphores'):
        rows += row('CPU Task Semaphore', 'asyncio.Semaphore + thread pool',
                    f"{min(concur['semaphores'])} simultaneous",
                    'Prevents CPU/memory spike during bulk processing', 'cpu')
    if concur.get('has_executor'):
        rows += row('Thread Pool Executor', 'run_in_executor (concurrent.futures)',
                    'OS thread count',
                    'CPU-bound tasks offloaded from event loop', 'cpu')

    if llm.get('providers'):
        rows += row(f"{', '.join(llm['providers'][:2])} (LLM)",
                    'Synchronous HTTP',
                    cap['practical'],
                    f"{'Timeout: ' + str(llm['timeout']) + 's · ' if llm.get('timeout') else ''}Rate limit: tier-dependent", 'external')

    if concur.get('batch_size'):
        rows += row('Embedding batch', f"{'OpenAI' if 'OpenAI' in (llm.get('embedding') or []) else 'Embedding API'}",
                    f"{concur['batch_size']} texts/call",
                    'Amortises API latency per batch call', 'io')

    vector_stores = [s for s in storage if s['type'] == 'vector']
    if vector_stores:
        rows += row(vector_stores[0]['name'], 'HNSW vector index', '< 100ms search',
                    'Sub-linear at millions of vectors · metadata filters', 'io')

    redis_stores = [s for s in storage if s['type'] == 'cache']
    if redis_stores:
        rows += row('Redis / Cache', 'Single-threaded event loop',
                    '< 1ms GET/SET', 'In-memory · AOF persistence in prod', 'io')

    return f'<div class="tbl-wrap"><table><thead><tr><th>Layer</th><th>Concurrency Model</th><th>Ceiling</th><th>Limiting Factor</th></tr></thead><tbody>{rows}</tbody></table></div>'


def render_bottlenecks(analysis: dict, cap: dict) -> str:
    items = []
    llm = analysis['llm']
    concur = analysis['concurrency']
    workers = analysis['workers']

    def card(name: str, severity: str, pct: int, color: str, detail: str) -> str:
        return (
            f'<div class="bn-card">'
            f'<div class="bn-title"><span>{name}</span><span style="color:{color};font-family:var(--mono);font-size:12px">{severity}</span></div>'
            f'<div class="bn-track"><div class="bn-fill" style="width:{pct}%;background:{color}"></div></div>'
            f'<div class="bn-meta">{detail}</div></div>'
        )

    if llm.get('providers'):
        timeout = llm.get('timeout') or 30
        items.append(card(f"{llm['providers'][0]} (LLM)", 'CRITICAL', 95, '#ef4444',
                          f"Primary bottleneck. Each inference call takes {timeout}s timeout. "
                          f"Cache bypass required. Mitigate: semantic cache, smaller model for simple queries."))
    if concur.get('semaphores'):
        items.append(card('CPU Processing (Semaphore)', 'HIGH', 70, '#f97316',
                          f"asyncio.Semaphore({min(concur['semaphores'])}) limits parallel CPU tasks. "
                          f"Prevents memory spikes but caps throughput. Mitigate: increase limit or add workers."))

    if analysis['queues']:
        items.append(card(f"{analysis['queues'][0]['name']} Workers", 'MEDIUM', 55, '#eab308',
                          'Worker concurrency set at startup. Scale horizontally or increase Celery -c. Backpressure controls queue depth.'))

    if concur.get('batch_size'):
        items.append(card('Embedding API', 'MEDIUM', 45, '#eab308',
                          f"Batch size {concur['batch_size']} texts/call. Increase to reduce round-trips. "
                          f"Rate-limited by embedding API tier."))

    vector_stores = [s for s in analysis['storage'] if s['type'] == 'vector']
    if vector_stores:
        items.append(card(f"{vector_stores[0]['name']} Vector Search", 'LOW', 15, '#22c55e',
                          'HNSW search is sub-100ms at scale. Quantization reduces RAM 4×. Not a bottleneck at typical workloads.'))

    if not items:
        items.append(card('Network I/O', 'LOW', 20, '#22c55e',
                          'Event-loop driven I/O is efficient. Scale workers horizontally to increase throughput.'))

    return f'<div class="bn-grid">{"".join(items)}</div>'


def render_html(analysis: dict, project_name: str) -> str:
    today = datetime.date.today().strftime('%Y-%m-%d')
    cap = analysis['capacity']
    workers = analysis['workers']
    llm = analysis['llm']
    gateway = analysis['gateway']
    concur = analysis['concurrency']
    flows = analysis['flows']

    def stat(val: str, color: str, label: str, sub: str = '') -> str:
        sub_html = f'<div class="sub">{sub}</div>' if sub else ''
        return (f'<div class="stat-card">'
                f'<div class="val" style="color:{color}">{val}</div>'
                f'<div class="lbl">{label}</div>{sub_html}</div>')

    stats = stat(str(cap['total_workers']), '#22c55e', 'API Worker Processes',
                 f"{workers.get('uvicorn_workers') or workers.get('gunicorn_workers') or 1} workers × {workers['replicas']} replica(s)")
    stats += stat(f"~{cap['total_io']:,}", '#3b82f6', 'Max Concurrent Async I/O',
                  f"~{cap['per_worker_io']} per {'asyncio' if cap['is_async'] else 'sync'} worker")
    if concur.get('semaphores'):
        stats += stat(str(min(concur['semaphores'])), '#a855f7', 'Max Parallel CPU Tasks', 'asyncio.Semaphore limit')
    if cap.get('rate_limit_str'):
        stats += stat(cap['rate_limit_str'].split()[0], '#f97316', 'Rate Limit (Gateway)', cap['rate_limit_str'])
    stats += stat(cap['practical'], '#eab308', 'Practical Throughput', f"bottleneck: {cap['bottleneck']}")
    if llm.get('timeout') and llm.get('providers'):
        stats += stat(f"{llm['timeout']}s", '#06b6d4', 'LLM Timeout', ', '.join(llm['providers'][:1]))

    # Flow cards HTML
    flow_html = ''
    for fl in flows:
        color = fl['color']
        hex_c = C.get(color, '#475569')
        bg_c = C.get(f'{color}_d', '#1a2535')
        step_rows = ''
        for i, step in enumerate(fl['steps'], 1):
            code_line = f'<div class="step-code">{step["code"]}</div>' if step.get('code') else ''
            step_rows += (
                f'<div class="flow-step">'
                f'<div class="step-num" style="background:rgba({int(hex_c[1:3],16)},{int(hex_c[3:5],16)},{int(hex_c[5:7],16)},.15);color:{hex_c}">{i}</div>'
                f'<div><div class="step-title">{step["title"]}</div>'
                f'<div class="step-desc">{step["desc"]}</div>{code_line}</div></div>'
            )
        flow_html += (
            f'<div class="flow-card">'
            f'<div class="flow-header" style="background:rgba({int(hex_c[1:3],16)},{int(hex_c[3:5],16)},{int(hex_c[5:7],16)},.08)">'
            f'<div class="dot" style="background:{hex_c}"></div>{fl["title"]}</div>'
            f'{step_rows}</div>'
        )

    # Route list snippet
    routes = analysis['api_server'].get('routes', [])[:10]
    route_html = ''
    if routes:
        route_items = ''.join(f'<div style="font-family:var(--mono);font-size:11px;padding:3px 0;color:#64748b">{r}</div>' for r in routes)
        route_html = (
            f'<div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;'
            f'padding:16px 20px;margin-top:20px">'
            f'<div style="font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:10px">Detected API Routes ({len(routes)}{"+" if len(analysis["api_server"].get("routes",[]))>10 else ""})</div>'
            f'{route_items}</div>'
        )

    arch_html = render_arch(analysis)
    table_html = render_concurrency_table(analysis, cap)
    bn_html = render_bottlenecks(analysis, cap)

    ext_count = len(analysis['external_sources'])
    storage_count = len(analysis['storage'])
    component_count = (1 + ext_count + storage_count +
                       (1 if gateway else 0) +
                       len(analysis['queues']) +
                       (1 if llm['providers'] else 0))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{project_name} — System Workflow</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="page">
<h1>{project_name} — System Workflow</h1>
<p class="subtitle">Component communication map · concurrent request capacity · bottleneck analysis · {today}</p>

<div class="stat-row">{stats}</div>
<p style="font-size:11px;color:var(--muted);margin:-28px 0 40px">Capacity figures are static-analysis estimates (heuristic: ~100 concurrent tasks per async worker), not load-test results.</p>

<div class="section">
<div class="section-title">Full System Architecture — {component_count} Components</div>
<div class="arch-wrap">{arch_html}</div>
{route_html}
</div>

<div class="section">
<div class="section-title">Data Flow Paths — Step by Step</div>
<div class="flows">{flow_html}</div>
</div>

<div class="section">
<div class="section-title">Concurrency Model — Layer by Layer</div>
{table_html}
</div>

<div class="section">
<div class="section-title">Bottleneck Analysis — Where the System Saturates First</div>
{bn_html}
</div>

<footer>{project_name} · System Workflow · {component_count} components · {today} · workflow-generator</footer>
</div>
</body>
</html>"""


# ── collect + main ─────────────────────────────────────────────────────────────

def collect(root: Path) -> dict:
    workers = detect_workers(root)
    gateway = detect_gateway(root)
    api_server = detect_api_server(root)
    frontend = detect_frontend(root)
    concur = detect_concurrency(root)
    llm = detect_llm(root)
    storage = detect_storage(root)
    queues = detect_queues(root)
    external_sources = detect_external_sources(root)
    capacity = compute_concurrency(workers, gateway, concur, llm)
    flows = infer_flows({
        'external_sources': external_sources,
        'gateway': gateway,
        'api_server': api_server,
        'frontend': frontend,
        'concurrency': concur,
        'llm': llm,
        'storage': storage,
        'queues': queues,
        'workers': workers,
    })
    return {
        'workers': workers,
        'gateway': gateway,
        'api_server': api_server,
        'frontend': frontend,
        'concurrency': concur,
        'llm': llm,
        'storage': storage,
        'queues': queues,
        'external_sources': external_sources,
        'capacity': capacity,
        'flows': flows,
    }


def main():
    root   = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else root / 'WORKFLOW.html'

    project_name = detect_project_name(root) or root.resolve().name.replace('-', ' ').replace('_', ' ').title()
    analysis = collect(root)

    output.write_text(render_html(analysis, project_name))

    cap = analysis['capacity']
    print(f"Written: {output}")
    print(f"Framework: {analysis['api_server']['framework']} · Workers: {cap['total_workers']} · Concurrent I/O: ~{cap['total_io']}")
    print(f"Bottleneck: {cap['bottleneck']} · Practical throughput (estimated): {cap['practical']}")
    if analysis['gateway']:
        print(f"Gateway: {analysis['gateway']['type']} · {len(analysis['gateway']['rate_limits'])} rate limit zone(s)")
    if analysis['llm']['providers']:
        print(f"LLM: {', '.join(analysis['llm']['providers'])} · eval: {analysis['llm'].get('eval_framework') or 'none'}")
    print(f"Storage: {', '.join(s['name'] for s in analysis['storage'])}")
    print(f"External sources: {', '.join(s['name'] for s in analysis['external_sources'])}")


if __name__ == '__main__':
    main()
