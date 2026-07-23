#!/usr/bin/env python3
"""
workflow-generator — project workflow analyzer
Scans a project directory, detects all components and their communication
patterns, computes concurrent request capacity, and writes WORKFLOW.html.

Usage:
    python3 analyze.py [project_dir] [output_file]
"""

import ast, datetime, json, re, sys
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
    'openai_chat':      re.compile(r'ChatOpenAI|openai\.OpenAI|AzureChatOpenAI|AzureOpenAI\(|\bimport\s+openai\b|from\s+openai\s+import', re.I),
    'anthropic_chat':   re.compile(r'ChatAnthropic|anthropic\.Anthropic|\bimport\s+anthropic\b|from\s+anthropic\s+import', re.I),
    'cohere_chat':      re.compile(r'ChatCohere|cohere\.Client', re.I),
    'bedrock_chat':     re.compile(r'ChatBedrock|boto3.*bedrock', re.I),
    'gemini_chat':      re.compile(r'ChatGoogleGenerativeAI|google\.generativeai|genai\.GenerativeModel', re.I),
    'mistral_chat':     re.compile(r'ChatMistralAI|MistralClient|mistralai\.', re.I),
    'groq_chat':        re.compile(r'ChatGroq|groq\.Groq|from\s+groq\s+import', re.I),
    'ollama_chat':      re.compile(r'ChatOllama|ollama\.Client|\bimport\s+ollama\b', re.I),
    'litellm_call':     re.compile(r'\blitellm\.(?:completion|acompletion)\b|\bimport\s+litellm\b', re.I),
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
    # External sources — require actual SDK usage / conventional env-var names,
    # not a bare word match (which fires on READMEs, CI badges, and comments).
    'jira':             re.compile(r'\bimport\s+jira\b|from\s+jira\b|JIRA_(API_TOKEN|BASE_URL|EMAIL)|atlassian\.net', re.I),
    'ado':              re.compile(r'azure.?devops|dev\.azure\.com|AzureDevOps|AZURE_DEVOPS_(PAT|TOKEN|ORG)', re.I),
    'slack':            re.compile(r'slack_sdk|slack_bolt|from\s+slack\b|import\s+slack\b|SLACK_(BOT_TOKEN|WEBHOOK_URL|SIGNING_SECRET)|@slack/(bolt|web-api)', re.I),
    'github':           re.compile(r'PyGithub|from\s+github\b|import\s+github\b|@octokit|X-Hub-Signature|GITHUB_(TOKEN|WEBHOOK_SECRET|APP_ID)\b', re.I),
    'stripe':           re.compile(r'import\s+stripe\b|stripe\.(api_key|Webhook|Charge|Customer)|STRIPE_(SECRET_KEY|WEBHOOK_SECRET|API_KEY)', re.I),
    'salesforce':       re.compile(r'simple_salesforce|from\s+salesforce\b|SALESFORCE_(USERNAME|PASSWORD|SECURITY_TOKEN)', re.I),
    'twilio':           re.compile(r'from\s+twilio\b|import\s+twilio\b|twilio\.rest|TWILIO_(ACCOUNT_SID|AUTH_TOKEN)', re.I),
    'sendgrid':         re.compile(r'sendgrid|mailgun|SES.*email', re.I),
    's3':               re.compile(r'boto3.*s3|s3://|S3Client', re.I),
    # Auth
    'jwt':              re.compile(r'JWT|PyJWT|jsonwebtoken|jose', re.I),
    'oauth':            re.compile(r'oauth|OAuth', re.I),
    'hmac_sig':         re.compile(r'HMAC|hmac\.new|X-Hub-Signature|signing.?secret', re.I),
    'api_key_auth':     re.compile(r'api.key|APIKey|api_key.*header', re.I),
    # API routes — Python
    'fastapi_route':    re.compile(r'@[\w.]+\.(get|post|put|delete|patch|websocket)\s*\(\s*["\']([^"\']+)["\']'),
    'flask_route':      re.compile(r'@[\w.]+\.route\s*\(\s*["\']([^"\']+)["\']'),
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


_read_all_cache: dict[tuple[str, str], str] = {}


def _read_all(root: Path, pattern: str) -> str:
    """Read all matching files (skipping vendored/venv dirs) and concatenate their contents.

    Memoized per (root, pattern): every detector in collect() independently
    asks for the same '*.py'/'*.js' full-tree read, so on a large repo this
    was re-walking and re-reading the whole tree ~8 times over. One process
    only ever analyzes one root, so a plain dict cache (no eviction) is safe.
    """
    key = (str(root.resolve()), pattern)
    cached = _read_all_cache.get(key)
    if cached is not None:
        return cached
    parts = []
    for p in root.rglob(pattern):
        if _is_excluded(root, p):
            continue
        try:
            parts.append(p.read_text(errors='ignore'))
        except Exception:
            pass
    result = '\n'.join(parts)
    _read_all_cache[key] = result
    return result


def _read_file(root: Path, *names: str) -> str:
    for name in names:
        p = root / name
        if p.exists():
            try:
                return p.read_text(errors='ignore')
            except Exception:
                pass
    return ''


_read_manifests_cache: dict[str, str] = {}


def _read_manifests(root: Path) -> str:
    """Dependency manifests: packages declared here are first-party signal,
    unlike the same names appearing inside vendored dependency source.
    Memoized — detect_llm() alone calls this once per provider spec."""
    key = str(root.resolve())
    cached = _read_manifests_cache.get(key)
    if cached is not None:
        return cached
    parts = []
    for name in ('requirements.txt', 'requirements-dev.txt', 'pyproject.toml',
                 'package.json', 'go.mod', 'Cargo.toml', 'Gemfile'):
        p = root / name
        if p.exists():
            try:
                parts.append(p.read_text(errors='ignore'))
            except Exception:
                pass
    result = '\n'.join(parts)
    _read_manifests_cache[key] = result
    return result


def _manifest_pkg(root: Path, *pkg_names: str) -> bool:
    """Whole-token package-name match against dependency manifests only
    (requirements.txt/pyproject.toml/package.json/go.mod/...). A declared
    dependency is real signal even when actual usage is hidden behind a
    custom abstraction the source regexes don't recognize."""
    text = _read_manifests(root)
    return any(re.search(r'[\'"/]?' + re.escape(name) + r'[\'"@=<>~^ ,\]]', text, re.I)
               for name in pkg_names)


# Cheap `in` substring pre-check before the real (often alternation-heavy)
# regex .search() — on a large repo, `all_src` can be tens of MB, and a
# detector doing 8-10 sequential .search() calls against it dominates
# runtime (profiled: ~70s of a 120s Dify run was regex .search()). A plain
# substring test is far cheaper per byte than backtracking regex search, and
# is a strictly *necessary* condition for each pattern below to ever match —
# every alternative in the corresponding _RE pattern contains at least one of
# these literals, so this can only skip searches that were guaranteed to
# fail; it can never suppress a real match. Keys without a safe single/few
# literal (rare) are simply absent here and always fall through to the real
# regex.
_LOWER_HINTS: dict[str, tuple[str, ...]] = {
    'openai_chat': ('openai',), 'anthropic_chat': ('anthropic',), 'cohere_chat': ('cohere',),
    'bedrock_chat': ('bedrock',), 'gemini_chat': ('generativeai', 'genai'),
    'mistral_chat': ('mistral',), 'groq_chat': ('groq',), 'ollama_chat': ('ollama',),
    'litellm_call': ('litellm',),
    'redis_cache': ('redis',), 'redis_db': ('redis',),
    'qdrant': ('qdrant',), 'pinecone': ('pinecone',), 'weaviate': ('weaviate',),
    'chromadb': ('chroma',), 'pgvector': ('pgvector', 'postgres'),
    'faiss': ('faiss',), 'milvus': ('milvus',), 'postgres': ('postgres', 'psycopg'), 'mysql': ('mysql',),
    'mongo': ('mongo', 'motor'), 'sqlite': ('sqlite',),
    'celery': ('celery',), 'bull': ('bull',), 'kafka': ('kafka',),
    'rabbitmq': ('rabbitmq', 'pika', 'amqp'), 'redis_queue': ('rq', 'redisqueue'), 'sqs': ('sqs',),
    'jira': ('jira', 'atlassian'), 'ado': ('devops', 'azure.com'), 'slack': ('slack',),
    'github': ('github', 'octokit', 'x-hub-signature'), 'stripe': ('stripe',),
    'salesforce': ('salesforce',), 'twilio': ('twilio',), 's3': ('s3',),
}


def _hinted_search(re_key: str, text: str, text_lower: str) -> re.Match | None:
    """`_RE[re_key].search(text)`, skipping the real regex when a required
    literal (see _LOWER_HINTS) is provably absent from text_lower."""
    hints = _LOWER_HINTS.get(re_key)
    if hints is not None and not any(h in text_lower for h in hints):
        return None
    return _RE[re_key].search(text)


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
    if framework == 'Django':
        for m in _RE['django_path'].finditer(py_src):
            routes.add(f"* {m.group(1)}")

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


def _extract_route_strings(text: str, framework: str) -> set[str]:
    """Same route-string construction detect_api_server() uses (routes.append
    lines above), applied to one file's text instead of the whole-repo
    concatenation — lets the graph/access-log overlay know *which* file
    declares a given route, without inventing a second detection method."""
    routes = set()
    for m in _RE['fastapi_route'].finditer(text):
        routes.add(f"{m.group(1).upper()} {m.group(2)}")
    for m in _RE['flask_route'].finditer(text):
        routes.add(f"* {m.group(1)}")
    for m in _RE['express_route'].finditer(text):
        routes.add(f"{m.group(1).upper()} {m.group(2)}")
    if framework == 'Django':
        for m in _RE['django_path'].finditer(text):
            routes.add(f"* {m.group(1)}")
    return routes


def _route_to_regex(path: str) -> re.Pattern:
    """Convert a detected route template (Flask/Django `<id>`, FastAPI `{id}`,
    Express `:id`) into a regex matching one concrete request path."""
    placeholder = re.compile(r'<[^>]+>|\{[^}]+\}|:[A-Za-z_][A-Za-z0-9_]*')
    literal_parts = [re.escape(part) for part in placeholder.split(path)]
    body = '[^/]+'.join(literal_parts).rstrip('/')
    return re.compile(r'^' + body + r'/?$')


_LOG_LINE_RE = re.compile(r'"(?P<method>[A-Z]+)\s+(?P<path>[^\s"]+)\s+HTTP/[\d.]+"\s+(?P<status>\d{3})')
_LOG_TS_RE = re.compile(r'\[(?P<ts>[^\]]+)\]')


def parse_access_log(path_str: str, routes: list) -> dict | None:
    """Parse an nginx/Apache Common/Combined Log Format or uvicorn/gunicorn
    access log into real per-route request counts. Returns None (with a
    stderr warning) if the file is missing/unreadable/empty of matching
    lines — absent log data must never fall back to a guessed number."""
    p = Path(path_str)
    if not p.exists():
        print(f"Warning: --access-log file not found: {path_str}", file=sys.stderr)
        return None

    route_specs = []
    for r in routes:
        method, _, tmpl = r.partition(' ')
        route_specs.append((method, tmpl, _route_to_regex(tmpl)))

    by_route: dict[str, int] = {}
    other = 0
    total = 0
    timestamps = []
    try:
        with p.open(errors='ignore') as f:
            for line in f:
                m = _LOG_LINE_RE.search(line)
                if not m:
                    continue
                total += 1
                method, raw_path = m.group('method'), m.group('path')
                path_only = raw_path.split('?', 1)[0]
                tm = _LOG_TS_RE.search(line)
                if tm:
                    try:
                        timestamps.append(datetime.datetime.strptime(tm.group('ts').split(' ')[0], '%d/%b/%Y:%H:%M:%S'))
                    except ValueError:
                        pass
                matched = None
                for rmethod, tmpl, rx in route_specs:
                    if rmethod not in ('*', method):
                        continue
                    if rx.match(path_only):
                        matched = f"{rmethod} {tmpl}"
                        break
                if matched:
                    by_route[matched] = by_route.get(matched, 0) + 1
                else:
                    other += 1
    except OSError as e:
        print(f"Warning: could not read --access-log {path_str}: {e}", file=sys.stderr)
        return None

    if total == 0:
        print(f"Warning: --access-log {path_str} had no recognizable request lines.", file=sys.stderr)
        return None

    rpm = None
    if len(timestamps) >= 2:
        span_min = (max(timestamps) - min(timestamps)).total_seconds() / 60
        if span_min > 0:
            rpm = total / span_min

    return {'total': total, 'by_route': by_route, 'other': other, 'rpm': rpm, 'source': path_str}


def _gen_k6_script(routes: list) -> str:
    """A ready-to-run k6 script hitting up to 5 detected routes, so the
    modeled throughput number has a direct path to being replaced by a real
    measurement instead of just being trusted."""
    def fill(path: str) -> str:
        return re.sub(r'<[^>]+>|\{[^}]+\}|:[A-Za-z_][A-Za-z0-9_]*', '1', path)

    picks = []
    for r in routes:
        method, _, tmpl = r.partition(' ')
        if method in ('*', 'GET'):
            picks.append(('GET', fill(tmpl)))
        if len(picks) >= 5:
            break
    if not picks:
        for r in routes[:5]:
            method, _, tmpl = r.partition(' ')
            picks.append((method if method != '*' else 'GET', fill(tmpl)))

    lines = [
        "import http from 'k6/http';",
        "import { sleep } from 'k6';",
        "",
        "// Generated by workflow-generator. Edit BASE_URL, add auth headers,",
        "// and replace any `1` path params with real IDs before running.",
        "// Run: k6 run --env BASE_URL=https://staging.example.com this_file.js",
        "const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';",
        "",
        "export const options = { vus: 10, duration: '30s' };",
        "",
        "export default function () {",
    ]
    for method, path in picks:
        lines.append(f"  http.{method.lower()}(`${{BASE_URL}}{path}`);")
    lines += ["  sleep(1);", "}"]
    return '\n'.join(lines)


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
    all_src_lower = all_src.lower()

    # Confirmed = matched an actual usage pattern in source. Declared = the
    # package is a real dependency (per manifest) but no usage pattern
    # matched — common when a codebase routes calls through its own
    # provider-abstraction layer instead of calling the SDK class directly.
    # Declared-only providers are shown, but with lower confidence, never as
    # a traced/confirmed fact (see render_arch's `declared` box + infer_flows).
    _PROVIDER_SPECS = [
        ('OpenAI', 'openai_chat', ('openai',)),
        ('Anthropic', 'anthropic_chat', ('anthropic',)),
        ('Cohere', 'cohere_chat', ('cohere',)),
        # No dedicated pip package for Bedrock — it's accessed via boto3,
        # which is also pulled in for plain S3/SQS use. boto3 alone isn't
        # Bedrock-specific signal, so this stays source-confirm-only (no
        # manifest fallback tuple).
        ('AWS Bedrock', 'bedrock_chat', ()),
        ('Google Gemini', 'gemini_chat', ('google-generativeai', 'google-genai')),
        ('Mistral', 'mistral_chat', ('mistralai',)),
        ('Groq', 'groq_chat', ('groq',)),
        ('Ollama', 'ollama_chat', ('ollama',)),
        ('LiteLLM (multi-provider)', 'litellm_call', ('litellm',)),
    ]
    providers, providers_declared = [], []
    for name, re_key, pkgs in _PROVIDER_SPECS:
        if _hinted_search(re_key, all_src, all_src_lower):
            providers.append(name)
        elif _manifest_pkg(root, *pkgs):
            providers_declared.append(name)

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
        'providers_declared': providers_declared,
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
    all_src_lower = all_src.lower()

    def hit(re_key):
        return _hinted_search(re_key, all_src, all_src_lower)

    stores = []
    if hit('qdrant'):
        stores.append({'name': 'Qdrant', 'type': 'vector', 'desc': 'HNSW vector DB', 'color': 'indigo'})
    if hit('pinecone'):
        stores.append({'name': 'Pinecone', 'type': 'vector', 'desc': 'Managed vector DB', 'color': 'indigo'})
    if hit('weaviate'):
        stores.append({'name': 'Weaviate', 'type': 'vector', 'desc': 'Vector DB', 'color': 'indigo'})
    if hit('chromadb'):
        stores.append({'name': 'ChromaDB', 'type': 'vector', 'desc': 'Embedded vector DB', 'color': 'indigo'})
    if hit('pgvector'):
        stores.append({'name': 'pgvector', 'type': 'vector', 'desc': 'Postgres vector ext', 'color': 'indigo'})
    if hit('faiss'):
        stores.append({'name': 'FAISS', 'type': 'vector', 'desc': 'In-process ANN search', 'color': 'indigo'})
    if hit('milvus'):
        stores.append({'name': 'Milvus', 'type': 'vector', 'desc': 'Distributed vector DB', 'color': 'indigo'})
    if hit('postgres'):
        stores.append({'name': 'PostgreSQL', 'type': 'relational', 'desc': 'Primary database', 'color': 'blue'})
    if hit('mysql'):
        stores.append({'name': 'MySQL', 'type': 'relational', 'desc': 'Relational database', 'color': 'blue'})
    if hit('mongo'):
        stores.append({'name': 'MongoDB', 'type': 'nosql', 'desc': 'Document store', 'color': 'green'})
    if hit('sqlite'):
        stores.append({'name': 'SQLite', 'type': 'relational', 'desc': 'Embedded / dev DB', 'color': 'gray'})
    if hit('redis_cache') or hit('redis_db'):
        stores.append({'name': 'Redis', 'type': 'cache', 'desc': 'Cache / pub-sub', 'color': 'red'})
    if hit('s3'):
        stores.append({'name': 'S3 / Object Store', 'type': 'object', 'desc': 'File storage', 'color': 'yellow'})
    return stores


def detect_queues(root: Path) -> list:
    all_src = _read_all(root, '*.py') + _read_all(root, '*.js') + _read_all(root, '*.ts')
    compose = _read_file(root, 'docker-compose.prod.yml', 'docker-compose.yml')
    combined = all_src + compose + _read_manifests(root)
    combined_lower = combined.lower()

    def hit(re_key):
        return _hinted_search(re_key, combined, combined_lower)

    queues = []
    if hit('celery'):
        queues.append({'name': 'Celery', 'desc': 'Distributed task queue', 'color': 'green'})
    if hit('bull'):
        queues.append({'name': 'BullMQ', 'desc': 'Node.js job queue (Redis)', 'color': 'red'})
    if hit('kafka'):
        queues.append({'name': 'Kafka', 'desc': 'Event streaming', 'color': 'gray'})
    if hit('rabbitmq'):
        queues.append({'name': 'RabbitMQ', 'desc': 'AMQP message broker', 'color': 'orange'})
    if hit('redis_queue'):
        queues.append({'name': 'RQ (Redis Queue)', 'desc': 'Simple Redis job queue', 'color': 'red'})
    if hit('sqs'):
        queues.append({'name': 'AWS SQS', 'desc': 'Managed message queue', 'color': 'yellow'})
    return queues


def detect_external_sources(root: Path) -> list:
    all_src = _read_all(root, '*.py') + _read_all(root, '*.js') + _read_all(root, '*.ts')
    env = _read_file(root, '.env', '.env.example', '.env.sample')
    combined = all_src + env + _read_manifests(root)
    combined_lower = combined.lower()

    def hit(re_key):
        return _hinted_search(re_key, combined, combined_lower)

    sources = []
    if hit('jira'):
        sources.append({'name': 'Jira', 'proto': 'Webhook + REST', 'auth': 'HMAC-SHA256', 'color': 'blue'})
    if hit('ado'):
        sources.append({'name': 'Azure DevOps', 'proto': 'Service Hooks + REST', 'auth': 'SHA1 secret', 'color': 'blue'})
    if hit('slack'):
        sources.append({'name': 'Slack', 'proto': 'Events API', 'auth': 'Signing secret', 'color': 'purple'})
    if hit('github'):
        sources.append({'name': 'GitHub', 'proto': 'Webhooks + API', 'auth': 'HMAC-SHA256', 'color': 'gray'})
    if hit('stripe'):
        sources.append({'name': 'Stripe', 'proto': 'Webhooks + API', 'auth': 'Webhook sig', 'color': 'purple'})
    if hit('salesforce'):
        sources.append({'name': 'Salesforce', 'proto': 'REST / SOAP', 'auth': 'OAuth2', 'color': 'blue'})
    if hit('twilio'):
        sources.append({'name': 'Twilio', 'proto': 'SMS / Voice API', 'auth': 'Account SID', 'color': 'red'})

    # Always add "Users / API Clients"
    sources.append({'name': 'Users / API Clients', 'proto': 'HTTPS / WebSocket', 'auth': 'JWT', 'color': 'green'})

    if re.search(r'cron|schedule|APScheduler|celery.*beat|crontab', all_src, re.I):
        sources.append({'name': 'Cron / Scheduler', 'proto': 'Internal trigger', 'auth': '—', 'color': 'yellow'})
    return sources


# ── Concurrency calculation ────────────────────────────────────────────────────

def _rate_str_to_per_min(rate_str: str) -> float | None:
    """Parse a 'Nr/m' or 'Nr/s' style rate string into requests-per-minute."""
    m = re.match(r'(\d+(?:\.\d+)?)r/([ms])', rate_str or '')
    if not m:
        return None
    val, unit = float(m.group(1)), m.group(2)
    return val * 60 if unit == 's' else val


def compute_concurrency(workers: dict, gateway: dict | None, concur: dict, llm: dict, api: dict | None = None) -> dict:
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
    sem_ceiling = sem_limit * total_workers if sem_limit else None

    # Concurrency ceiling = the tightest of the concurrency-shaped constraints.
    concurrency_candidates = [('I/O event loop' if is_async else 'Sync worker pool', total_io)]
    if sem_ceiling is not None:
        concurrency_candidates.append(('Semaphore limit', sem_ceiling))
    concurrency_label, concurrency_ceiling = min(concurrency_candidates, key=lambda c: c[1])

    # Throughput-shaped constraints (requests/min), only added when real evidence exists.
    # This is a genuine min() across whichever constraints were actually detected —
    # previously this picked one branch by priority and silently ignored the others.
    throughput_candidates = []

    if gateway and gateway.get('rate_limits'):
        rpm = _rate_str_to_per_min(gateway['rate_limits'][0]['rate'])
        if rpm:
            throughput_candidates.append((f"{gateway['type']} rate limit", rpm))

    if api and api.get('app_rate_limits'):
        arl = api['app_rate_limits'][0]
        try:
            rate_val = float(arl['rate'])
            unit = (arl.get('unit') or '').lower()
            rpm = rate_val * 60 if unit.startswith('sec') else rate_val
            throughput_candidates.append(('Application rate limit', rpm))
        except (KeyError, TypeError, ValueError):
            pass

    if llm.get('providers'):
        # Model each in-flight concurrency slot as tied up for one LLM call's timeout —
        # tied to the actually-detected worker/async/semaphore numbers, not a bare constant.
        timeout = llm.get('timeout') or 30
        llm_rpm = concurrency_ceiling * (60 / timeout)
        throughput_candidates.append((f"{llm['providers'][0]} latency", llm_rpm))

    # Rank whichever set of constraints is operative, tightest first. render_bottlenecks
    # derives its severities from this same ranking instead of keeping its own guess —
    # otherwise the stat row and the bottleneck cards could disagree with each other.
    if throughput_candidates:
        ranking = sorted(throughput_candidates, key=lambda c: c[1])
        ranking_kind = 'rpm'
        bottleneck, rpm = ranking[0]
        practical = f"~{int(rpm)}/min"
    else:
        ranking = sorted(concurrency_candidates, key=lambda c: c[1])
        ranking_kind = 'concurrency'
        bottleneck, concurrency_ceiling = ranking[0]
        practical = f"~{concurrency_ceiling} concurrent I/O"

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
        'ranking': ranking,
        'ranking_kind': ranking_kind,
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

    # Write path: webhooks / ingestion.
    # Previously this paired *any* detected external-source name with routes[0] —
    # literally the alphabetically-first route found anywhere in the app — and
    # presented the pairing as a traced fact ("GitHub fires webhook -> POST to /me").
    # The two signals are almost never actually connected. Now: only use a route if
    # its path genuinely contains "webhook", never assert signature verification
    # unless the HMAC/signing-secret pattern was actually detected in source, and
    # say "possible" / "not confirmed" wherever the link between signals is inferred
    # rather than observed.
    webhook_sources = [s for s in ext if 'webhook' in s.get('proto', '').lower()]
    webhook_routes = [r for r in api.get('routes', []) if 'webhook' in r.lower()]
    if api.get('has_webhooks') or webhook_sources:
        steps = []
        route_ref = webhook_routes[0] if webhook_routes else None
        hmac_detected = api.get('auth', {}).get('hmac', False)

        if webhook_sources and route_ref:
            names = ' / '.join(s['name'] for s in webhook_sources[:2])
            title, desc = f"Possible {names} webhook", f"Inbound webhook route detected: {route_ref}."
        elif route_ref:
            title, desc = 'Inbound webhook route', f"Detected route: {route_ref}."
        elif webhook_sources:
            names = ' / '.join(s['name'] for s in webhook_sources[:2])
            title = f"{names} referenced in code"
            desc = "Mentioned in source/env — no dedicated webhook route confirmed; verify manually."
        else:
            title, desc = 'Webhook pattern detected', "A /webhook-style path was found, but no specific route could be extracted."

        desc += (" Signature/HMAC verification code found in source."
                 if hmac_detected else
                 " No signature-verification code detected — confirm this endpoint validates its sender.")
        steps.append({'title': title, 'desc': desc, 'code': route_ref})
        steps.append({'title': 'Acknowledgment', 'desc': 'Check the actual handler for the response status and whether processing is deferred to a worker.', 'code': None})
        if concur.get('semaphores'):
            steps.append({'title': 'CPU-bound processing exists', 'desc': f"asyncio.Semaphore({concur['semaphores'][0]}) caps concurrent CPU-bound tasks somewhere in this codebase (not necessarily on this route).", 'code': f"Semaphore({concur['semaphores'][0]})"})
        vector_stores = [s for s in storage if s['type'] == 'vector']
        if vector_stores:
            steps.append({'title': 'Vector store present', 'desc': f"{vector_stores[0]['name']} is used somewhere in this codebase — common in ingestion pipelines, but not confirmed to be wired to this route.", 'code': None})
        flows.append({'title': 'Write Path — Webhook Ingestion (inferred, not traced)', 'color': 'orange', 'steps': steps})

    # Read path: RAG query. Same issue as above — an LLM provider and a vector store
    # being detected anywhere in the repo doesn't mean a single request path chains
    # them together. Keep genuinely detected specifics (provider, model, timeout,
    # retries, vector store name, eval framework); label the rest as a typical
    # pattern rather than an observed one.
    vector_stores = [s for s in storage if s['type'] == 'vector']
    if llm.get('providers') and vector_stores:
        steps = [
            {'title': 'Query received', 'desc': 'Typical pattern if this is a RAG endpoint — auth/scope handling not confirmed here.', 'code': None},
            {'title': f"Vector search in {vector_stores[0]['name']}", 'desc': f"{vector_stores[0]['name']} is used in this codebase; not confirmed to be called from the same path as the LLM call below.", 'code': None},
            {'title': f"{', '.join(llm['providers'][:2])} inference", 'desc': f"LLM call detected. {'Timeout: ' + str(llm['timeout']) + 's · ' if llm.get('timeout') else ''}Retries: {llm.get('retries') or 'not detected'}", 'code': f"{', '.join(llm['models'][:1]) or llm['providers'][0]}"},
        ]
        if llm.get('eval_framework'):
            steps.append({'title': f"{llm['eval_framework']} present", 'desc': f"{llm['eval_framework']} is used somewhere in this codebase — commonly for response scoring, not confirmed to run on this path.", 'code': None})
        flows.append({'title': 'Read Path — AI Query (typical pattern, not traced)', 'color': 'green', 'steps': steps})

    # Queue / background job flow — the queue name is real; the step narrative
    # (enqueue -> dequeue -> store) is the standard shape for this kind of
    # component, not something traced from this codebase's actual call sites.
    if queues:
        steps = [
            {'title': 'Task enqueued (typical)', 'desc': f"{queues[0]['name']} is used in this codebase. Typically an API handler publishes a job and returns immediately — verify the actual enqueue call site.", 'code': None},
            {'title': 'Worker picks up task (typical)', 'desc': f"A {queues[0]['name']} worker process would dequeue and process — confirm the worker entry point and concurrency setting in your own config.", 'code': None},
            {'title': 'Result stored (typical)', 'desc': 'Commonly written to a database or returned via callback — not confirmed here.', 'code': None},
        ]
        flows.append({'title': f"Async Background Jobs — {queues[0]['name']} (typical pattern, not traced)", 'color': 'purple', 'steps': steps})

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
:root[data-theme="light"]{--bg:#f8fafc;--bg2:#ffffff;--bg3:#ffffff;--bg4:#f1f5f9;
--border:#e2e8f0;--border2:#cbd5e1;--text:#0f172a;--muted:#64748b;--dim:#94a3b8}
:root[data-theme="light"] body{background-image:radial-gradient(circle,#cbd5e1 1.4px,transparent 1.4px);background-size:24px 24px}
:root[data-theme="light"] h1{color:#0f172a}
:root[data-theme="light"] code{color:#0891b2}
:root[data-theme="light"] .arch-wrap{box-shadow:0 1px 3px rgba(15,23,42,.06)}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:var(--sans);font-size:14px;line-height:1.6;transition:background .25s,color .25s}
.page{max-width:1440px;margin:0 auto;padding:40px 32px 80px}
h1{font-size:28px;font-weight:700;color:#f8fafc;margin-bottom:4px}
.theme-toggle{position:fixed;top:20px;right:24px;width:40px;height:40px;border-radius:50%;
border:1px solid var(--border);background:var(--bg3);color:var(--text);font-size:17px;
cursor:pointer;z-index:20;display:flex;align-items:center;justify-content:center;
box-shadow:0 2px 8px rgba(0,0,0,.15)}
.theme-toggle:hover{border-color:var(--border2)}
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
padding:24px;overflow-x:auto;position:relative}
.graph-wrap{background:var(--bg3);border:1px solid var(--border);border-radius:14px;
padding:16px;position:relative;height:640px}
.graph-wrap canvas{width:100%;height:100%;display:block;border-radius:10px;cursor:grab}
.graph-toolbar{position:absolute;top:26px;left:26px;right:26px;z-index:2;display:flex;
align-items:center;gap:10px;flex-wrap:wrap}
#graph-search{background:var(--bg2);
border:1px solid var(--border);border-radius:8px;padding:6px 10px;font-size:12px;
color:var(--text);width:180px;font-family:var(--sans)}
#graph-search:focus{outline:none;border-color:var(--border2)}
#graph-hide-isolated-wrap{display:flex;align-items:center;gap:5px;font-size:11px;
color:var(--muted);white-space:nowrap;cursor:pointer;user-select:none}
#graph-isolated-count{color:var(--muted)}
#graph-reset-view{background:var(--bg2);border:1px solid var(--border);border-radius:8px;
padding:6px 10px;font-size:11px;color:var(--muted);font-family:var(--sans);cursor:pointer}
#graph-reset-view:hover{color:var(--text);border-color:var(--border2)}
.graph-legend{position:absolute;bottom:26px;left:26px;right:26px;z-index:2;display:flex;gap:14px 20px;
flex-wrap:wrap;font-size:10.5px;color:var(--muted);background:rgba(0,0,0,.0)}
.graph-legend span{display:flex;align-items:center;gap:5px}
.graph-legend .lg-dot{width:9px;height:9px;border-radius:50%;background:#818cf8;display:inline-block}
.graph-legend .lg-square{width:9px;height:9px;background:#eab308;display:inline-block;border-radius:2px}
.graph-legend .lg-ring{width:9px;height:9px;border-radius:50%;border:1.5px solid var(--muted);display:inline-block}
.graph-tooltip{position:absolute;z-index:3;pointer-events:none;background:var(--bg2);border:1px solid var(--border2);
border-radius:8px;padding:8px 11px;font-size:11px;color:var(--text);box-shadow:0 4px 16px rgba(0,0,0,.25);
display:none;max-width:320px;line-height:1.5}
.graph-tooltip .tt-path{font-family:var(--mono);font-weight:600;word-break:break-all}
.graph-tooltip .tt-meta{color:var(--muted);font-size:10.5px;margin-top:3px}
.derivation{background:var(--bg3);border:1px solid var(--border);border-radius:10px;padding:12px 18px;margin:0 0 12px}
.derivation summary{cursor:pointer;font-size:12px;font-weight:600;color:var(--text);list-style:revert}
.derivation .muted-inline{font-weight:400;color:var(--muted);font-size:11px}
.derivation-body{margin-top:12px}
.deriv-row{display:flex;justify-content:space-between;font-family:var(--mono);font-size:11.5px;color:var(--muted);padding:3px 0}
.deriv-row span:last-child{color:var(--text)}
.deriv-divider{height:1px;background:var(--border);margin:10px 0}
.deriv-label{font-size:11px;font-weight:600;color:var(--muted);margin-bottom:4px}
.deriv-assumptions{font-size:11px;color:var(--muted);line-height:1.6}
.arch-layer{margin-bottom:0}
.arch-row-label{font-size:10px;font-weight:600;letter-spacing:.1em;text-transform:uppercase;
color:#334155;margin-bottom:8px;padding-left:4px}
.arch-boxes{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:6px}
.arch-box{border:1.5px solid;border-radius:10px;padding:12px 16px;min-width:160px;flex:1;max-width:280px;position:relative;color:#f1f5f9}
.arch-box.declared{border-style:dashed;opacity:.72}
.arch-box .bname{font-weight:700;font-size:13px;margin-bottom:2px}
.arch-box .bicon{margin-right:6px;font-size:13px}
.arch-box .bdesc{font-size:11px;opacity:.7;margin-bottom:4px}
.arch-box .bcode{font-family:var(--mono);font-size:10px;opacity:.55;margin-top:2px}
/* Nested storage groups */
.arch-group{border:1.5px dashed var(--border2);border-radius:12px;padding:14px 10px 10px;
display:flex;gap:12px;flex-wrap:wrap;position:relative;flex:1;min-width:200px}
.arch-group-label{position:absolute;top:-9px;left:12px;background:var(--bg3);padding:0 8px;
font-size:9px;font-weight:700;letter-spacing:.09em;text-transform:uppercase;color:var(--muted)}
/* Edge overlay: real node-to-node connections evidenced by a flow's step sequence */
#edge-overlay{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;overflow:visible}
.edge-path{fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;opacity:.85}
.edge-label{font-family:inherit;font-size:10px;font-weight:600;fill:var(--text);pointer-events:none}
.edge-label-bg{fill:var(--bg2);stroke:var(--border);stroke-width:1;pointer-events:none}
@media(prefers-reduced-motion:no-preference){
.edge-path.animated{stroke-dasharray:8 6;animation:edgeFlow 1s linear infinite}
}
@keyframes edgeFlow{to{stroke-dashoffset:-28}}
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
/* Animated flow: architecture arrows */
.arch-arrow{position:relative;height:26px}
.arrow-line{position:absolute;left:50%;top:0;bottom:0;width:2px;background:var(--border2);transform:translateX(-50%)}
.arrow-dot{position:absolute;left:50%;top:0;width:10px;height:10px;border-radius:50%;
background:#60a5fa;box-shadow:0 0 8px 2px #60a5fa,0 0 18px 4px rgba(96,165,250,.55);transform:translateX(-50%);opacity:0}
.arch-boxes{border-radius:14px;padding:6px;margin:-6px -6px 0 -6px}
@media(prefers-reduced-motion:no-preference){
.arrow-dot{animation:arrowFlow var(--t,4s) linear infinite;
animation-delay:calc(var(--i,0)/var(--n,1)*var(--t,4s))}
.arch-boxes{animation:rowPulse var(--t,4s) ease-in-out infinite;
animation-delay:calc(var(--i,0)/var(--n,1)*var(--t,4s))}
.step-num::after{animation:stepFlow var(--t,3s) linear infinite;
animation-delay:calc(var(--i,0)/var(--n,1)*var(--t,3s))}
}
@keyframes arrowFlow{0%{opacity:0;top:0}5%{opacity:1}45%{top:calc(100% - 10px);opacity:1}62%{opacity:0}100%{opacity:0}}
@keyframes rowPulse{0%,100%{background:transparent;box-shadow:none}
4%{background:rgba(96,165,250,.12);box-shadow:0 0 0 1px rgba(96,165,250,.4)}
22%{background:rgba(96,165,250,.12);box-shadow:0 0 0 1px rgba(96,165,250,.4)}
34%{background:transparent;box-shadow:none}}
/* Animated flow: step connectors */
.step-num{position:relative}
.step-num::before{content:'';position:absolute;left:50%;bottom:100%;width:2px;height:14px;
background:var(--border2);transform:translateX(-50%)}
.flow-step:first-child .step-num::before{display:none}
.step-num::after{content:'';position:absolute;left:50%;top:-14px;width:5px;height:5px;
border-radius:50%;background:currentColor;opacity:0;transform:translateX(-50%)}
@keyframes stepFlow{0%{opacity:0;top:-14px}8%{opacity:1}92%{top:0;opacity:1}100%{opacity:0}}
"""

EDGE_JS = """
(function(){
  var toggle = document.getElementById('theme-toggle');
  var root = document.documentElement;
  if (toggle) {
    toggle.addEventListener('click', function(){
      var goingLight = root.getAttribute('data-theme') !== 'light';
      root.setAttribute('data-theme', goingLight ? 'light' : 'dark');
      toggle.textContent = goingLight ? '\\ud83c\\udf19' : '\\u2600\\ufe0f';
      drawEdges();
      document.dispatchEvent(new Event('theme-changed'));
    });
  }

  var dataEl = document.getElementById('edges-data');
  var edges = [];
  try { edges = dataEl ? JSON.parse(dataEl.textContent) : []; } catch (e) { edges = []; }
  var svg = document.getElementById('edge-overlay');
  var wrap = document.querySelector('.arch-wrap');

  function nodeMap(){
    var map = {};
    if (!wrap) return map;
    wrap.querySelectorAll('[data-node]').forEach(function(el){
      map[el.getAttribute('data-node')] = el;
    });
    return map;
  }

  var SVG_NS = 'http://www.w3.org/2000/svg';

  function shortLabel(label){
    var s = (label || '').split(' (')[0];
    return s.length > 28 ? s.slice(0, 27) + '\\u2026' : s;
  }

  function drawEdges(){
    if (!svg || !wrap || !edges.length) return;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    var map = nodeMap();
    var wr = wrap.getBoundingClientRect();
    svg.setAttribute('width', wrap.scrollWidth);
    svg.setAttribute('height', wrap.scrollHeight);

    var defs = document.createElementNS(SVG_NS, 'defs');
    svg.appendChild(defs);
    var seenColors = {};
    edges.forEach(function(e){
      if (seenColors[e.color]) return;
      seenColors[e.color] = true;
      var markerId = 'arrow-' + e.color.replace('#', '');
      var marker = document.createElementNS(SVG_NS, 'marker');
      marker.setAttribute('id', markerId);
      marker.setAttribute('viewBox', '0 0 10 10');
      marker.setAttribute('refX', '8');
      marker.setAttribute('refY', '5');
      marker.setAttribute('markerWidth', '7');
      marker.setAttribute('markerHeight', '7');
      marker.setAttribute('orient', 'auto-start-reverse');
      var arrowPath = document.createElementNS(SVG_NS, 'path');
      arrowPath.setAttribute('d', 'M0,0 L10,5 L0,10 z');
      arrowPath.setAttribute('fill', e.color);
      marker.appendChild(arrowPath);
      defs.appendChild(marker);
    });

    edges.forEach(function(e){
      var fromEl = map[e.from];
      var toEl = map[e.to];
      if (!fromEl || !toEl) return;
      var fr = fromEl.getBoundingClientRect();
      var tr = toEl.getBoundingClientRect();
      var x1 = fr.left - wr.left + wrap.scrollLeft + fr.width / 2;
      var y1 = fr.top - wr.top + wrap.scrollTop + fr.height;
      var x2 = tr.left - wr.left + wrap.scrollLeft + tr.width / 2;
      var y2 = tr.top - wr.top + wrap.scrollTop;
      var midY = (y1 + y2) / 2;
      var d = 'M' + x1 + ',' + y1 + ' L' + x1 + ',' + midY + ' L' + x2 + ',' + midY + ' L' + x2 + ',' + y2;
      var path = document.createElementNS(SVG_NS, 'path');
      path.setAttribute('d', d);
      path.setAttribute('class', 'edge-path animated');
      path.setAttribute('stroke', e.color);
      path.setAttribute('marker-end', 'url(#arrow-' + e.color.replace('#', '') + ')');
      var title = document.createElementNS(SVG_NS, 'title');
      title.textContent = e.label;
      path.appendChild(title);
      svg.appendChild(path);

      var text = document.createElementNS(SVG_NS, 'text');
      text.setAttribute('class', 'edge-label');
      text.setAttribute('x', (x1 + x2) / 2);
      text.setAttribute('y', midY);
      text.setAttribute('text-anchor', 'middle');
      text.textContent = shortLabel(e.label);
      svg.appendChild(text);
      var bbox = text.getBBox();
      var bg = document.createElementNS(SVG_NS, 'rect');
      bg.setAttribute('class', 'edge-label-bg');
      bg.setAttribute('x', bbox.x - 4);
      bg.setAttribute('y', bbox.y - 2);
      bg.setAttribute('width', bbox.width + 8);
      bg.setAttribute('height', bbox.height + 4);
      bg.setAttribute('rx', 4);
      svg.insertBefore(bg, text);
    });
  }

  var resizeTimer;
  window.addEventListener('resize', function(){
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(drawEdges, 150);
  });

  drawEdges();
})();
"""

GRAPH_JS = """
(function(){
  var dataEl = document.getElementById('graph-data');
  if (!dataEl) return;
  var data = JSON.parse(dataEl.textContent);
  var canvas = document.getElementById('code-graph');
  if (!canvas || !data.nodes.length) return;
  var ctx = canvas.getContext('2d');
  var wrap = canvas.parentElement;
  var tooltip = document.getElementById('graph-tooltip');
  var reduceMotion = !window.matchMedia('(prefers-reduced-motion: no-preference)').matches;

  function hashStr(s){
    var h = 2166136261;
    for (var i = 0; i < s.length; i++){ h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
    return (h >>> 0);
  }
  function pkgColor(pkg){
    var h = hashStr(pkg);
    return 'hsl(' + (h % 360) + ',62%,58%)';
  }

  // Degree is computed once over the full graph (independent of the isolated-node
  // toggle below) so hiding zero-degree nodes never changes an in/out count.
  var byIdAll = {};
  data.nodes.forEach(function(n){ byIdAll[n.id] = n; });
  var allLinks = data.links.filter(function(l){ return byIdAll[l.s] && byIdAll[l.t]; }).map(function(l){
    return Object.assign({}, l, {phase: (hashStr(l.s + l.t) % 1000) / 1000});
  });
  var degree = {};
  allLinks.forEach(function(l){
    degree[l.s] = degree[l.s] || {in: 0, out: 0};
    degree[l.t] = degree[l.t] || {in: 0, out: 0};
    degree[l.s].out++;
    degree[l.t].in++;
  });
  var isolatedIds = {}, isolatedCount = 0;
  data.nodes.forEach(function(n){
    var d = degree[n.id];
    if (!d || (d.in === 0 && d.out === 0)){ isolatedIds[n.id] = true; isolatedCount++; }
  });

  function nodeRadius(n){
    if (n.kind === 'service' || n.kind === 'entry') return 15;
    if (n.kind === 'dir') return Math.max(6, Math.min(20, 5 + Math.sqrt(n.file_count || 1) * 3));
    return Math.max(3, Math.min(14, 3 + Math.sqrt(n.loc || 1) * 0.55));
  }
  function nodeFill(n){
    if (n.kind === 'service' || n.kind === 'entry') return n.color;
    return pkgColor(n.pkg);
  }

  // ── Force simulation: O(n^2) repulsion + spring edges + centering. n is
  // capped (file cap / directory aggregation upstream), so this stays cheap. ──
  var nodes, links, byId, alpha, view = {x: 0, y: 0, scale: 1};
  function tick(){
    var n = nodes.length;
    for (var i = 0; i < n; i++){
      var a = nodes[i];
      if (a.fixed) continue;
      var fx = -a.x * 0.004, fy = -a.y * 0.004; // gentle centering
      for (var j = 0; j < n; j++){
        if (i === j) continue;
        var b = nodes[j];
        var dx = a.x - b.x, dy = a.y - b.y;
        var d2 = dx*dx + dy*dy + 0.01;
        var f = 1400 / d2;
        fx += dx * f; fy += dy * f;
      }
      a.vx = (a.vx + fx * alpha) * 0.82;
      a.vy = (a.vy + fy * alpha) * 0.82;
    }
    links.forEach(function(l){
      var s = byId[l.s], t = byId[l.t];
      var dx = t.x - s.x, dy = t.y - s.y;
      var dist = Math.sqrt(dx*dx + dy*dy) || 1;
      var target = 90;
      var f = (dist - target) * 0.012 * alpha;
      var ux = dx / dist, uy = dy / dist;
      if (!s.fixed){ s.vx += ux * f; s.vy += uy * f; }
      if (!t.fixed){ t.vx -= ux * f; t.vy -= uy * f; }
    });
    nodes.forEach(function(a){
      if (a.fixed) return;
      // Clamp per-tick speed: near-coincident starting positions push d2 toward
      // its floor and the 1400/d2 repulsion term spikes, which without this cap
      // throws nodes to thousands of units away and off the visible canvas.
      var speed = Math.sqrt(a.vx * a.vx + a.vy * a.vy), maxSpeed = 40;
      if (speed > maxSpeed){ a.vx *= maxSpeed / speed; a.vy *= maxSpeed / speed; }
      a.x += a.vx; a.y += a.vy;
    });
    alpha = Math.max(0.02, alpha * 0.985);
  }

  // Fit the view to wherever the settled layout actually landed, rather than
  // assuming it fits a {x:0,y:0,scale:1} viewport — the settled bounding box
  // scales with node count and link topology, not a fixed canvas size.
  function fitView(){
    var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    nodes.forEach(function(n){
      if (n.x < minX) minX = n.x; if (n.x > maxX) maxX = n.x;
      if (n.y < minY) minY = n.y; if (n.y > maxY) maxY = n.y;
    });
    var w = Math.max(1, maxX - minX), h = Math.max(1, maxY - minY);
    var r = canvas.getBoundingClientRect();
    var cw = r.width || 800, ch = r.height || 500;
    var scale = Math.min(1.4, Math.max(0.06, Math.min(cw / w, ch / h) * 0.85));
    var cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
    view = {x: -cx * scale, y: -cy * scale, scale: scale};
  }

  var selected = null, hovered = null, searchMatch = null;

  // Rebuilds the node/link set (optionally excluding zero-degree nodes), re-settles
  // the force layout from fresh hashed starting positions, and re-fits the view —
  // used both for the initial paint and whenever the "hide isolated" toggle changes.
  function buildLayout(hideIsolated){
    var visible = hideIsolated ? data.nodes.filter(function(n){ return !isolatedIds[n.id]; }) : data.nodes;
    nodes = visible.map(function(n){
      var h1 = hashStr(n.id), h2 = hashStr(n.id + ':r');
      var angle = (h1 % 6283) / 1000;
      var radius = 60 + (h2 % 260);
      return Object.assign({}, n, {
        x: Math.cos(angle) * radius, y: Math.sin(angle) * radius, vx: 0, vy: 0, fixed: false,
      });
    });
    byId = {};
    nodes.forEach(function(n){ byId[n.id] = n; });
    links = allLinks.filter(function(l){ return byId[l.s] && byId[l.t]; });
    alpha = 1;
    for (var i = 0; i < 220; i++) tick(); // settle to a deterministic resting layout before first paint
    fitView();
    selected = null; hovered = null; searchMatch = null;
  }

  var hideIsolatedEl = document.getElementById('graph-hide-isolated');
  var isolatedCountEl = document.getElementById('graph-isolated-count');
  var hideIsolatedWrapEl = document.getElementById('graph-hide-isolated-wrap');
  if (isolatedCountEl) isolatedCountEl.textContent = isolatedCount ? ' (' + isolatedCount + ')' : '';
  if (!isolatedCount && hideIsolatedWrapEl) hideIsolatedWrapEl.style.display = 'none';
  if (hideIsolatedEl) hideIsolatedEl.checked = isolatedCount > 0;
  buildLayout(hideIsolatedEl ? hideIsolatedEl.checked : false);
  if (hideIsolatedEl) hideIsolatedEl.addEventListener('change', function(){
    dragging = null; panStart = null; moved = false;
    buildLayout(hideIsolatedEl.checked);
  });
  var resetViewEl = document.getElementById('graph-reset-view');
  if (resetViewEl) resetViewEl.addEventListener('click', function(){ fitView(); });

  function worldToScreen(x, y){
    var r = canvas.getBoundingClientRect();
    return [r.width/2 + view.x + x * view.scale, r.height/2 + view.y + y * view.scale];
  }
  function screenToWorld(sx, sy){
    var r = canvas.getBoundingClientRect();
    return [(sx - r.width/2 - view.x) / view.scale, (sy - r.height/2 - view.y) / view.scale];
  }

  function related(id){
    var set = {};
    set[id] = true;
    links.forEach(function(l){
      if (l.s === id) set[l.t] = true;
      if (l.t === id) set[l.s] = true;
    });
    return set;
  }

  var cs = getComputedStyle(document.documentElement);
  var colors = {};
  function refreshColors(){
    cs = getComputedStyle(document.documentElement);
    colors.text = cs.getPropertyValue('--text').trim() || '#f1f5f9';
    colors.muted = cs.getPropertyValue('--muted').trim() || '#64748b';
    colors.edge = cs.getPropertyValue('--border2').trim() || '#334155';
    colors.bg = cs.getPropertyValue('--bg3').trim() || '#161e2e';
  }
  refreshColors();
  document.addEventListener('theme-changed', refreshColors);

  var particleSpeed = 0.00025;
  var lastT = null;

  function draw(t){
    if (lastT === null) lastT = t;
    var dt = t - lastT; lastT = t;
    var r = canvas.getBoundingClientRect();
    if (canvas.width !== Math.round(r.width * devicePixelRatio)){
      canvas.width = r.width * devicePixelRatio;
      canvas.height = r.height * devicePixelRatio;
    }
    ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    ctx.clearRect(0, 0, r.width, r.height);

    var highlightSet = selected ? related(selected) : (searchMatch || null);

    links.forEach(function(l){
      var s = byId[l.s], t2 = byId[l.t];
      var p1 = worldToScreen(s.x, s.y), p2 = worldToScreen(t2.x, t2.y);
      var dim = highlightSet && !(highlightSet[l.s] && highlightSet[l.t]);
      ctx.beginPath();
      ctx.moveTo(p1[0], p1[1]);
      ctx.lineTo(p2[0], p2[1]);
      ctx.strokeStyle = colors.edge;
      ctx.globalAlpha = dim ? 0.08 : (l.kind === 'service' ? 0.55 : 0.35);
      ctx.lineWidth = Math.min(2.5, 0.6 + (l.w || 1) * 0.15);
      ctx.stroke();
      ctx.globalAlpha = 1;

      if (!reduceMotion && !dim){
        if (!l._phase) l._phase = l.phase;
        // Real observed-traffic weight (from --access-log) speeds the
        // particle up (log-scaled — raw request counts span orders of
        // magnitude); unweighted edges just show dependency direction.
        var hasTraffic = l.kind === 'entry' && l.w;
        var speedMul = hasTraffic ? Math.min(5, 1 + Math.log2(l.w + 1) * 0.5) : 1;
        l._phase = (l._phase + dt * particleSpeed * speedMul) % 1;
        [l._phase, (l._phase + 0.5) % 1].forEach(function(ph){
          var px = p1[0] + (p2[0]-p1[0]) * ph, py = p1[1] + (p2[1]-p1[1]) * ph;
          ctx.beginPath();
          ctx.arc(px, py, 1.8, 0, 7);
          ctx.fillStyle = hasTraffic ? '#f59e0b' : (l.kind === 'service' ? '#60a5fa' : colors.muted);
          ctx.globalAlpha = 0.9;
          ctx.fill();
          ctx.globalAlpha = 1;
        });
      }
    });

    nodes.forEach(function(n){
      var p = worldToScreen(n.x, n.y);
      var rad = nodeRadius(n) * Math.max(0.6, Math.min(1.4, view.scale));
      var dim = highlightSet && !highlightSet[n.id];
      ctx.globalAlpha = dim ? 0.15 : 1;
      ctx.beginPath();
      if (n.kind === 'service' || n.kind === 'entry'){
        var s2 = rad * 1.5;
        ctx.fillStyle = nodeFill(n);
        ctx.strokeStyle = colors.bg;
        ctx.lineWidth = 2;
        ctx.roundRect ? ctx.roundRect(p[0]-s2/2, p[1]-s2/2, s2, s2, 4) : ctx.rect(p[0]-s2/2, p[1]-s2/2, s2, s2);
        ctx.fill(); ctx.stroke();
      } else {
        ctx.arc(p[0], p[1], rad, 0, 7);
        ctx.fillStyle = nodeFill(n);
        ctx.fill();
      }
      var showLabel = n.kind !== 'file' || view.scale > 1.6 || n.id === hovered || (highlightSet && highlightSet[n.id]);
      if (showLabel && !dim){
        ctx.font = (n.kind === 'service' || n.kind === 'entry' ? '600 ' : '') + '10px system-ui,sans-serif';
        ctx.fillStyle = colors.text;
        ctx.fillText((n.icon ? n.icon + ' ' : '') + n.label, p[0] + rad + 4, p[1] + 3);
      }
      ctx.globalAlpha = 1;
    });

    if (alpha > 0.03){ tick(); }
    if (running) requestAnimationFrame(draw);
  }

  // ── Interaction: wheel zoom (cursor-anchored), drag pan/move, click select ──
  var dragging = null, panStart = null, moved = false;
  canvas.addEventListener('wheel', function(e){
    e.preventDefault();
    var r = canvas.getBoundingClientRect();
    var mx = e.clientX - r.left, my = e.clientY - r.top;
    var before = screenToWorld(mx, my);
    var factor = Math.exp(-e.deltaY * 0.001);
    // Floor matches fitView's floor (0.06) so wheel zoom-out can always reach back to,
    // or past, the initial auto-fit scale — a stricter floor here would leave large
    // graphs permanently more zoomed-in than their starting view with no way back.
    view.scale = Math.max(0.05, Math.min(6, view.scale * factor));
    var after = worldToScreen(before[0], before[1]);
    view.x += mx - after[0]; view.y += my - after[1];
  }, {passive: false});

  function pick(mx, my){
    var w = screenToWorld(mx, my);
    var best = null, bestD = 1e9;
    nodes.forEach(function(n){
      var d = Math.hypot(n.x - w[0], n.y - w[1]);
      var rad = nodeRadius(n) + 3;
      if (d < rad && d < bestD){ best = n; bestD = d; }
    });
    return best;
  }

  canvas.addEventListener('mousedown', function(e){
    var r = canvas.getBoundingClientRect();
    var mx = e.clientX - r.left, my = e.clientY - r.top;
    var hit = pick(mx, my);
    moved = false;
    if (hit){ dragging = hit; hit.fixed = true; }
    else { panStart = {x: e.clientX - view.x, y: e.clientY - view.y}; }
  });
  window.addEventListener('mousemove', function(e){
    var r = canvas.getBoundingClientRect();
    var mx = e.clientX - r.left, my = e.clientY - r.top;
    if (dragging){
      moved = true;
      var w = screenToWorld(mx, my);
      dragging.x = w[0]; dragging.y = w[1];
      alpha = Math.max(alpha, 0.3);
      tooltip.style.display = 'none';
    } else if (panStart){
      moved = true;
      tooltip.style.display = 'none';
      view.x = e.clientX - panStart.x; view.y = e.clientY - panStart.y;
    } else {
      var hit = pick(mx, my);
      hovered = hit ? hit.id : null;
      canvas.style.cursor = hit ? 'pointer' : 'grab';
      if (hit){
        var deg = degree[hit.id] || {in: 0, out: 0};
        var metaBits = [];
        if (hit.kind === 'file') metaBits.push(hit.loc + ' line' + (hit.loc === 1 ? '' : 's'));
        if (hit.kind === 'dir') metaBits.push(hit.file_count + ' file' + (hit.file_count === 1 ? '' : 's') + ' aggregated', hit.loc + ' total lines');
        metaBits.push(deg.in + ' in \\u2192 node \\u2192 ' + deg.out + ' out');
        tooltip.innerHTML = '<div class="tt-path">' + (hit.icon ? hit.icon + ' ' : '') + hit.id + '</div>'
          + '<div class="tt-meta">' + metaBits.join(' \\u00b7 ') + '</div>';
        tooltip.style.display = 'block';
        var flip = mx > r.width * 0.6;
        tooltip.style.left = (flip ? mx - 14 : mx + 14) + 'px';
        tooltip.style.top = (my + 16) + 'px';
        tooltip.style.transform = flip ? 'translateX(-100%)' : '';
      } else {
        tooltip.style.display = 'none';
      }
    }
  });
  window.addEventListener('mouseup', function(){
    if (dragging) dragging.fixed = false;
    dragging = null; panStart = null;
  });
  canvas.addEventListener('mouseleave', function(){
    hovered = null;
    tooltip.style.display = 'none';
  });
  canvas.addEventListener('click', function(e){
    if (moved) return;
    var r = canvas.getBoundingClientRect();
    var hit = pick(e.clientX - r.left, e.clientY - r.top);
    selected = hit ? (selected === hit.id ? null : hit.id) : null;
  });

  var search = document.getElementById('graph-search');
  if (search){
    search.addEventListener('input', function(){
      var q = search.value.trim().toLowerCase();
      if (!q){ searchMatch = null; return; }
      var set = {};
      nodes.forEach(function(n){ if (n.label.toLowerCase().indexOf(q) !== -1) set[n.id] = true; });
      searchMatch = set;
    });
  }

  var running = false;
  var obs = new IntersectionObserver(function(entries){
    entries.forEach(function(en){
      if (en.isIntersecting && !running){ running = true; requestAnimationFrame(draw); }
      else if (!en.isIntersecting){ running = false; }
    });
  }, {threshold: 0.01});
  obs.observe(wrap);
  running = true;
  requestAnimationFrame(draw);
})();
"""


def _box(name: str, desc: str, color: str, code: str = '', extra_desc: str = '', declared: bool = False, icon: str = '') -> str:
    bg = C.get(f'{color}_d', '#1a2535')
    border = C.get(color, '#475569')
    glow = f"rgba({int(border[1:3],16)},{int(border[3:5],16)},{int(border[5:7],16)},.45)"
    full_desc = desc
    if extra_desc:
        full_desc = f"{desc} · {extra_desc}"
    code_line = f'<div class="bcode">{code}</div>' if code else ''
    # Declared-only boxes (dependency found in manifest, no usage pattern
    # confirmed in source) get no data-node — they must never anchor an
    # edge in compute_edges(), since usage isn't confirmed. They also skip
    # the icon: showing one would imply more confidence than the dashed
    # styling already signals.
    cls = 'arch-box declared' if declared else 'arch-box'
    node_attr = '' if declared else f' data-node="{name}"'
    icon_span = f'<span class="bicon">{icon}</span>' if (icon and not declared) else ''
    return (
        f'<div class="{cls}"{node_attr} style="background:{bg};border-color:{border};--gc:{glow}">'
        f'<div class="bname" style="color:{border}">{icon_span}{name}</div>'
        f'<div class="bdesc">{full_desc}</div>{code_line}</div>'
    )


_STORE_ICONS = {'vector': '🔍', 'relational': '🗄️', 'nosql': '🗂️', 'cache': '⚡', 'object': '📦'}


def _cap_diverse(items: list, n: int) -> list:
    """Cap a list to n items, round-robin across distinct `type` values first —
    so a real multi-type result isn't silently narrowed to one type just
    because that type happened to be appended first upstream."""
    buckets: dict = {}
    for it in items:
        buckets.setdefault(it['type'], []).append(it)
    order = list(buckets.keys())
    result: list = []
    idx = {k: 0 for k in order}
    while len(result) < n and any(idx[k] < len(buckets[k]) for k in order):
        for k in order:
            if len(result) >= n:
                break
            if idx[k] < len(buckets[k]):
                result.append(buckets[k][idx[k]])
                idx[k] += 1
    return result


def _arrow(i: int) -> str:
    return (f'<div class="arch-arrow" style="--i:{i}">'
            f'<div class="arrow-line"></div><div class="arrow-dot"></div></div>')


def render_arch(analysis: dict) -> tuple[str, set]:
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
    layer_idx = 0
    box_names: set = set()

    def box(name: str, desc: str, color: str, code: str = '', extra_desc: str = '', icon: str = '') -> str:
        box_names.add(name)
        return _box(name, desc, color, code, extra_desc, icon=icon)

    def layer(label: str, boxes: list[str]) -> None:
        nonlocal layer_idx
        parts.append(f'<div class="arch-layer"><div class="arch-row-label">{label}</div>'
                     f'<div class="arch-boxes" style="--i:{layer_idx}">{"".join(boxes)}</div></div>')
        parts.append(_arrow(layer_idx))
        layer_idx += 1

    # Row 0: External sources
    ext_boxes = []
    for s in ext[:5]:
        ext_boxes.append(box(s['name'], s['proto'], s['color'], s.get('auth', '') or '', icon='🌐'))
    if ext_boxes:
        layer('EXTERNAL SOURCES &amp; CLIENTS', ext_boxes)

    # Row 1: Gateway
    if gw:
        rl_summary = ''
        if gw.get('rate_limits'):
            rl_summary = ' · '.join(f"{r['rate']} burst={r['burst']}" for r in gw['rate_limits'][:2])
        extra = f"TLS · {rl_summary}" if rl_summary else 'TLS termination'
        layer('GATEWAY / REVERSE PROXY', [
            box(gw['type'], f"worker_connections {gw.get('worker_connections') or '?'}", 'gray', extra, icon='🚦')
        ])

    # Row 2: Application
    app_boxes = []
    fw_color = {'FastAPI': 'blue', 'Flask': 'green', 'Django': 'green',
                'Express': 'yellow', 'Gin (Go)': 'cyan', 'Spring Boot': 'orange'}.get(api['framework'], 'blue')
    worker_label = f"{'async ' if workers['is_async'] else ''}{(workers.get('uvicorn_workers') or 1)} worker{'s' if (workers.get('uvicorn_workers') or 1) > 1 else ''} × {workers['replicas']} replica{'s' if workers['replicas'] > 1 else ''}"
    auth_methods = ' · '.join(k for k, v in api['auth'].items() if v)
    app_boxes.append(box(api['framework'], worker_label, fw_color, auth_methods or '', icon='⚙️'))
    for f in fe:
        app_boxes.append(box(f['name'], f['desc'], f['color'], icon='🖥️'))
    layer('APPLICATION LAYER', app_boxes)

    # Row 3: Processing
    proc_boxes = []
    if concur.get('semaphores'):
        proc_boxes.append(box('Privacy / Preprocessing', 'CPU-bound — thread pool', 'purple',
                               f"Semaphore({min(concur['semaphores'])})", icon='🧮'))
    for q in queues:
        proc_boxes.append(box(q['name'], q['desc'], q['color'], icon='📨'))
    if not proc_boxes and api['auth'].get('jwt'):
        proc_boxes.append(box('Auth Middleware', 'JWT decode · RBAC scope check', 'yellow', icon='🔑'))
    if proc_boxes:
        layer('PROCESSING &amp; QUEUE LAYER', proc_boxes)

    # Row 4: Intelligence
    intel_boxes = []
    if llm['providers']:
        for p in llm['providers'][:2]:
            timeout_str = f"timeout={llm['timeout']}s" if llm.get('timeout') else ''
            model_str = ', '.join(llm['models'][:1]) or p
            intel_boxes.append(box(p, model_str, 'pink', timeout_str, icon='🧠'))
    if llm.get('embedding'):
        intel_boxes.append(box('Embedding', llm['embedding'][0], 'cyan',
                                f"batch={concur.get('batch_size') or '?'}", icon='🔎'))
    if llm.get('eval_framework'):
        intel_boxes.append(box(llm['eval_framework'], 'Quality scoring', 'yellow', 'RAG Triad', icon='📊'))
    # Declared-but-unconfirmed providers: real dependency (per manifest), no
    # usage pattern matched in source — rendered dashed via _box(..., declared=True)
    # directly (bypassing the box() closure) so they never enter box_names and
    # can never anchor a compute_edges() connection.
    for p in llm.get('providers_declared', [])[:3]:
        intel_boxes.append(_box(p, 'Declared dependency', 'gray',
                                 extra_desc='usage pattern not matched in source', declared=True))
    if intel_boxes:
        layer('AI / INTELLIGENCE LAYER', intel_boxes)

    # Row 5: Storage (no arrow after last) — grouped by real detect_storage() `type`
    # field when 2+ distinct types are present, otherwise flat as before.
    if storage:
        limited = _cap_diverse(storage, 6)
        distinct_types = {s['type'] for s in limited}
        if len(distinct_types) >= 2:
            groups: dict = {}
            for s in limited:
                groups.setdefault(s['type'], []).append(s)
            group_html = ''.join(
                f'<div class="arch-group"><div class="arch-group-label">{t}</div>'
                f'{"".join(box(s["name"], s["desc"], s["color"], icon=_STORE_ICONS.get(s["type"], "")) for s in items)}</div>'
                for t, items in groups.items()
            )
            store_inner = f'<div class="arch-boxes" style="--i:{layer_idx}">{group_html}</div>'
        else:
            store_boxes = [box(s['name'], s['desc'], s['color'], icon=_STORE_ICONS.get(s['type'], '')) for s in limited]
            store_inner = f'<div class="arch-boxes" style="--i:{layer_idx}">{"".join(store_boxes)}</div>'
        parts.append(
            f'<div class="arch-layer"><div class="arch-row-label">STORAGE &amp; PERSISTENCE</div>{store_inner}</div>'
        )
        n = layer_idx + 1
    else:
        n = layer_idx

    total = n * 0.9 + 1.6
    html = f'<div class="arch-flow" style="--n:{n};--t:{total}s">' + '\n'.join(parts) + '</div>'
    return html, box_names


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


_SEVERITY_STEPS = [
    ('CRITICAL', 95, '#ef4444'),
    ('HIGH', 70, '#f97316'),
    ('MEDIUM', 50, '#eab308'),
    ('LOW', 25, '#22c55e'),
]


def _mitigation_for(label: str) -> str:
    l = label.lower()
    if 'latency' in l:
        return 'Mitigate: response/semantic caching, a smaller model for simple queries, or fan-out so one slow call does not hold a whole worker slot.'
    if 'rate limit' in l:
        return 'Mitigate: raise the configured limit if the backend can sustain it, or add client-side backoff/queueing.'
    if 'semaphore' in l:
        return 'Mitigate: raise the semaphore limit if memory/CPU allows, or add more worker processes.'
    if 'i/o event loop' in l or 'sync worker pool' in l:
        return 'Mitigate: add more workers/replicas, or move to an async framework to raise per-worker I/O concurrency.'
    return 'Review whether this constraint is expected at current load.'


def render_bottlenecks(analysis: dict, cap: dict) -> str:
    items = []
    concur = analysis['concurrency']

    def card(name: str, severity: str, pct: int, color: str, detail: str) -> str:
        return (
            f'<div class="bn-card">'
            f'<div class="bn-title"><span>{name}</span><span style="color:{color};font-family:var(--mono);font-size:12px">{severity}</span></div>'
            f'<div class="bn-track"><div class="bn-fill" style="width:{pct}%;background:{color}"></div></div>'
            f'<div class="bn-meta">{detail}</div></div>'
        )

    # Ranked from the same min() comparison used for the "Practical Throughput" stat —
    # severity here is derived from that real ranking, not a fixed per-signal-type table,
    # so this section can no longer disagree with the stat row above it.
    ranking = cap.get('ranking') or []
    unit = 'requests/min' if cap.get('ranking_kind') == 'rpm' else 'units of concurrent capacity'
    for i, (label, value) in enumerate(ranking):
        severity, pct, color = _SEVERITY_STEPS[min(i, len(_SEVERITY_STEPS) - 1)]
        if i == 0:
            detail = f"Tightest ceiling among detected constraints: ~{int(value)} {unit}. {_mitigation_for(label)}"
        else:
            detail = f"Looser than the binding constraint above (~{int(value)} {unit}) — only matters once that one is relieved."
        items.append(card(label, severity, pct, color, detail))

    # Informational notes appended after the real ranking — these are context, not
    # ranked constraints, since there's no reliable way to compare their cost against
    # the ranked list above from static analysis alone.
    if concur.get('batch_size'):
        items.append(card('Embedding batch size', 'LOW', 20, '#22c55e',
                          f"Batch size {concur['batch_size']} texts/call — detected in source, not assumed."))

    vector_stores = [s for s in analysis['storage'] if s['type'] == 'vector']
    if vector_stores:
        items.append(card(f"{vector_stores[0]['name']} (vector store)", 'LOW', 15, '#22c55e',
                          'Present in this codebase. Typically sub-100ms at moderate scale, but not measured here.'))

    if not items:
        items.append(card('Network I/O', 'LOW', 20, '#22c55e',
                          'Event-loop driven I/O is efficient. Scale workers horizontally to increase throughput.'))

    return f'<div class="bn-grid">{"".join(items)}</div>'


def compute_edges(flows: list, box_names: set) -> list:
    """Real node-to-node edges: only drawn when consecutive steps within one
    already-vetted flow each unambiguously (whole-word, single-match) name a
    box that render_arch() actually rendered. Zero/multi-match steps are
    skipped rather than guessed."""
    edges, seen = [], set()
    for fl in flows:
        matched = []
        for step in fl['steps']:
            text = ' '.join(filter(None, [step.get('title', ''), step.get('desc', ''), step.get('code') or '']))
            hits = {n for n in box_names if re.search(r'\b' + re.escape(n) + r'\b', text)}
            matched.append(next(iter(hits)) if len(hits) == 1 else None)
        for a, b in zip(matched, matched[1:]):
            if a and b and a != b and (a, b) not in seen:
                seen.add((a, b))
                edges.append({'from': a, 'to': b, 'color': C.get(fl['color'], '#475569'), 'label': fl['title']})
    return edges


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
    stats += stat(cap['practical'], '#eab308', 'Modeled Throughput', f"static model, not a load test — bottleneck: {cap['bottleneck']}")
    if llm.get('timeout') and llm.get('providers'):
        stats += stat(f"{llm['timeout']}s", '#06b6d4', 'LLM Timeout', ', '.join(llm['providers'][:1]))
    access_log_stat = analysis.get('access_log')
    if access_log_stat and access_log_stat.get('rpm'):
        stats += stat(f"~{access_log_stat['rpm']:,.0f}/min", '#f59e0b', 'Observed Traffic',
                       f"measured — {access_log_stat['total']:,} requests in {Path(access_log_stat['source']).name}")

    # Derivation panel: the *inputs* behind "Modeled Throughput", not just its
    # output — every value here is one compute_concurrency() already returns.
    deriv_rows = (
        f'<div class="deriv-row"><span>Worker processes</span><span>{cap["total_workers"]}</span></div>'
        f'<div class="deriv-row"><span>Per-worker concurrency (assumed)</span><span>{cap["per_worker_io"]} '
        f'{"(async — ~100 concurrent tasks/worker is a heuristic, not measured)" if cap["is_async"] else "(sync — one request at a time)"}</span></div>'
        f'<div class="deriv-row"><span>{cap["total_workers"]} workers × {cap["per_worker_io"]}</span><span>= {cap["total_io"]} concurrency ceiling</span></div>'
    )
    if cap.get('sem_limit'):
        deriv_rows += f'<div class="deriv-row"><span>Semaphore limit × workers</span><span>{cap["sem_limit"]} × {cap["total_workers"]}</span></div>'
    ranking_rows = ''.join(
        f'<div class="deriv-row"><span>{i+1}. {label}</span><span>{f"{value:,.0f}/min" if cap["ranking_kind"]=="rpm" else f"{value:,.0f} concurrent"}</span></div>'
        for i, (label, value) in enumerate(cap.get('ranking', []))
    )
    derivation_html = f"""
<details class="derivation">
<summary>How was "Modeled Throughput" computed? <span class="muted-inline">(static model — click to expand)</span></summary>
<div class="derivation-body">
{deriv_rows}
<div class="deriv-divider"></div>
<div class="deriv-label">Ranked constraints (tightest wins — this is the bottleneck):</div>
{ranking_rows}
<div class="deriv-divider"></div>
<div class="deriv-assumptions">Assumptions baked into this model: ~100 concurrent tasks per async worker
is a heuristic, not a measurement; an in-flight LLM call is modeled as occupying its slot for the full
configured timeout{f" ({llm['timeout']}s)" if llm.get('timeout') else ''}, though real completions are usually
faster. Treat this number as a starting estimate, not a capacity guarantee.</div>
</div>
</details>
<details class="derivation">
<summary>Verify with a real load test <span class="muted-inline">(generated k6 script — click to expand)</span></summary>
<div class="derivation-body">
<p style="margin:0 0 10px;font-size:11.5px;color:var(--muted)">Pre-filled with up to 5 detected routes. Run this against a staging deploy to replace the model above with a measurement.</p>
<pre id="k6-script" style="background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:12px 14px;font-size:11px;overflow-x:auto;margin:0 0 10px">{_gen_k6_script(analysis['api_server'].get('routes', []))}</pre>
<button type="button" onclick="navigator.clipboard.writeText(document.getElementById('k6-script').textContent);this.textContent='Copied!';setTimeout(()=>this.textContent='Copy script',1500)" style="background:var(--bg2);border:1px solid var(--border);border-radius:6px;padding:6px 12px;font-size:11px;color:var(--text);cursor:pointer;font-family:var(--sans)">Copy script</button>
</div>
</details>
""" if analysis['api_server'].get('routes') else ''

    # Flow cards HTML
    flow_html = ''
    for fl in flows:
        color = fl['color']
        hex_c = C.get(color, '#475569')
        bg_c = C.get(f'{color}_d', '#1a2535')
        n_steps = len(fl['steps'])
        step_total = n_steps * 0.8 + 1.2
        step_rows = ''
        for i, step in enumerate(fl['steps'], 1):
            code_line = f'<div class="step-code">{step["code"]}</div>' if step.get('code') else ''
            step_rows += (
                f'<div class="flow-step">'
                f'<div class="step-num" style="background:rgba({int(hex_c[1:3],16)},{int(hex_c[3:5],16)},{int(hex_c[5:7],16)},.15);color:{hex_c};--i:{i-1}">{i}</div>'
                f'<div><div class="step-title">{step["title"]}</div>'
                f'<div class="step-desc">{step["desc"]}</div>{code_line}</div></div>'
            )
        flow_html += (
            f'<div class="flow-card" style="--n:{n_steps};--t:{step_total}s">'
            f'<div class="flow-header" style="background:rgba({int(hex_c[1:3],16)},{int(hex_c[3:5],16)},{int(hex_c[5:7],16)},.08)">'
            f'<div class="dot" style="background:{hex_c}"></div>{fl["title"]}</div>'
            f'{step_rows}</div>'
        )

    # Route list snippet — gains a real "requests" column when --access-log
    # was supplied; the counts are parsed, never estimated.
    routes = analysis['api_server'].get('routes', [])[:10]
    access_log_for_routes = analysis.get('access_log')
    route_html = ''
    if routes:
        if access_log_for_routes:
            by_route = access_log_for_routes['by_route']
            route_items = ''.join(
                f'<div style="display:flex;justify-content:space-between;font-family:var(--mono);font-size:11px;padding:3px 0;color:#64748b">'
                f'<span>{r}</span><span style="color:var(--text)">{by_route.get(r, 0):,}</span></div>'
                for r in routes
            )
            total_line = (
                f'<div style="margin-top:8px;padding-top:8px;border-top:1px solid var(--border);font-size:10.5px;color:var(--muted)">'
                f'{access_log_for_routes["total"]:,} requests parsed from <code>{access_log_for_routes["source"]}</code>'
                f'{" · " + str(access_log_for_routes["other"]) + " matched no known route" if access_log_for_routes["other"] else ""}</div>'
            )
        else:
            route_items = ''.join(f'<div style="font-family:var(--mono);font-size:11px;padding:3px 0;color:#64748b">{r}</div>' for r in routes)
            total_line = ''
        route_html = (
            f'<div style="background:var(--bg3);border:1px solid var(--border);border-radius:10px;'
            f'padding:16px 20px;margin-top:20px">'
            f'<div style="font-size:11px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin-bottom:10px">Detected API Routes ({len(routes)}{"+" if len(analysis["api_server"].get("routes",[]))>10 else ""})</div>'
            f'{route_items}{total_line}</div>'
        )

    arch_html, box_names = render_arch(analysis)
    edges = compute_edges(flows, box_names)
    edges_json = json.dumps(edges)
    table_html = render_concurrency_table(analysis, cap)
    bn_html = render_bottlenecks(analysis, cap)

    graph = analysis.get('graph') or {'nodes': [], 'links': [], 'meta': {'files': 0, 'links': 0, 'aggregated': False, 'shown_nodes': 0, 'has_access_log': False}}
    graph_json = json.dumps(graph)
    gm = graph['meta']
    graph_note = (
        f"{gm['files']} files aggregated into {gm['shown_nodes']} directories" if gm['aggregated']
        else f"{gm['shown_nodes']} modules"
    )
    graph_section = ''
    if graph['nodes']:
        access_log = analysis.get('access_log')
        traffic_note = (
            f" Amber particles on entry edges are <b>real</b> traffic, weighted by request count from <code>{access_log['source']}</code> ({access_log['total']:,} requests parsed)."
            if gm.get('has_access_log') and access_log else
            " This is <b>static analysis, not live monitoring</b> — particle motion shows dependency direction (importer → imported), not request traffic. Pass <code>--access-log &lt;path&gt;</code> to overlay real per-route request counts instead."
        )
        graph_section = f"""
<div class="section">
<div class="section-title">Codebase Graph — {graph_note} · {gm['links']} real connections</div>
<p style="font-size:11px;color:var(--muted);margin:-4px 0 16px">Every node is a real file{' or directory' if gm['aggregated'] else ''} in this repo; every line is an actual import statement, or a pattern-confirmed service call scanned per-file (the same signal behind the summary below, localized to its source).{traffic_note} Drag a node, scroll to zoom, click to isolate its connections, or search below.</p>
<div class="graph-wrap">
<canvas id="code-graph"></canvas>
<div id="graph-tooltip" class="graph-tooltip"></div>
<div class="graph-toolbar">
<input id="graph-search" placeholder="filter modules…">
<label id="graph-hide-isolated-wrap"><input type="checkbox" id="graph-hide-isolated">hide isolated files<span id="graph-isolated-count"></span></label>
<button id="graph-reset-view" type="button" title="Restore the default zoom and pan">reset view</button>
</div>
<div class="graph-legend">
<span><span class="lg-dot" style="background:#22c55e"></span>entry (HTTP clients)</span>
<span><span class="lg-dot" style="border-radius:2px"></span>module (colored by package)</span>
<span><span class="lg-square"></span>external service (pattern-confirmed)</span>
<span>→ arrow = "imports / calls" (static — not live traffic{" unless amber" if gm.get('has_access_log') else ""})</span>
<span><span class="lg-ring"></span><b style="color:var(--text)">click a node</b>&nbsp;to isolate its call paths (dims everything else); click empty space to clear, type in the search box to highlight by name</span>
</div>
</div>
<script type="application/json" id="graph-data">{graph_json}</script>
</div>
"""

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
<button id="theme-toggle" class="theme-toggle" aria-label="Toggle light/dark theme" title="Toggle theme">&#9728;&#65039;</button>
<div class="page">
<h1>{project_name} — System Workflow</h1>
<p class="subtitle">Component communication map · concurrent request capacity · bottleneck analysis · {today}</p>

<div class="stat-row">{stats}</div>
<p style="font-size:11px;color:var(--muted);margin:-28px 0 20px">Capacity figures are static-analysis estimates (heuristic: ~100 concurrent tasks per async worker), not load-test results.</p>
{derivation_html}
{graph_section}
<div class="section">
<div class="section-title">Full System Architecture — {component_count} Components</div>
<p style="font-size:11px;color:var(--muted);margin:-4px 0 16px">Detection is pattern-based static analysis. Dashed boxes are dependencies declared in your manifest but not matched to a usage pattern in source — may be wired through a custom abstraction. Solid boxes are pattern-confirmed in source. A component not shown here isn't confirmed absent from the project — only undetected.</p>
<div class="arch-wrap">{arch_html}<svg id="edge-overlay"></svg><script type="application/json" id="edges-data">{edges_json}</script></div>
{f'<p style="font-size:11px;color:var(--muted);margin-top:10px">{len(edges)} edge{"s" if len(edges) != 1 else ""} shown — drawn only where a data-flow step names two rendered components consecutively; not a claim about every real connection.</p>' if edges else ''}
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
<script>{EDGE_JS}</script>
<script>{GRAPH_JS}</script>
</body>
</html>"""


# ── Codebase graph — every source file as a node, real imports/service calls
# as edges. Complements the curated architecture summary above with the full
# picture: nothing here is inferred, every edge is either a parsed import
# statement or the same _RE pattern that already backs the component summary,
# scanned per-file instead of repo-wide. ──────────────────────────────────────

_GRAPH_EXTS = ('.py', '.js', '.jsx', '.ts', '.tsx', '.go', '.java', '.rs', '.rb')
_GRAPH_FILE_CAP = 350
_GRAPH_WARN_FILES = 800  # console heads-up when --graph-detail=files forces a very large render
_GRAPH_MAX_BYTES = 1_500_000

# name -> _RE key, used to attach a per-file edge to an already-detected
# component (same signal detect_llm/detect_storage/etc. already surfaced —
# this just localizes *which* files matched it).
_LLM_RE_KEYS = {
    'OpenAI': 'openai_chat', 'Anthropic': 'anthropic_chat', 'Cohere': 'cohere_chat',
    'AWS Bedrock': 'bedrock_chat', 'Google Gemini': 'gemini_chat', 'Mistral': 'mistral_chat',
    'Groq': 'groq_chat', 'Ollama': 'ollama_chat', 'LiteLLM (multi-provider)': 'litellm_call',
}
_STORAGE_RE_KEYS = {
    'Qdrant': 'qdrant', 'Pinecone': 'pinecone', 'Weaviate': 'weaviate', 'ChromaDB': 'chromadb',
    'pgvector': 'pgvector', 'FAISS': 'faiss', 'Milvus': 'milvus', 'PostgreSQL': 'postgres',
    'MySQL': 'mysql', 'MongoDB': 'mongo', 'SQLite': 'sqlite', 'Redis': 'redis_cache',
    'S3 / Object Store': 's3',
}
_QUEUE_RE_KEYS = {
    'Celery': 'celery', 'BullMQ': 'bull', 'Kafka': 'kafka', 'RabbitMQ': 'rabbitmq',
    'RQ (Redis Queue)': 'redis_queue', 'AWS SQS': 'sqs',
}
_EXTSRC_RE_KEYS = {
    'Jira': 'jira', 'Azure DevOps': 'ado', 'Slack': 'slack', 'GitHub': 'github',
    'Stripe': 'stripe', 'Salesforce': 'salesforce', 'Twilio': 'twilio',
}
_GRAPH_ENTRY_ID = 'entry:http'


def _py_module_name(root: Path, p: Path) -> str:
    rel = p.relative_to(root).with_suffix('')
    parts = rel.parts
    if parts and parts[-1] == '__init__':
        parts = parts[:-1]
    return '.'.join(parts)


def _collect_graph_files(root: Path) -> list[Path]:
    files = []
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix not in _GRAPH_EXTS or _is_excluded(root, p):
            continue
        try:
            if p.stat().st_size > _GRAPH_MAX_BYTES:
                continue
        except OSError:
            continue
        files.append(p)
    return files


def _load_ts_path_aliases(root: Path) -> list[tuple[str, Path]]:
    """Reads compilerOptions.baseUrl/paths out of tsconfig.json / jsconfig.json
    (lightly JSONC-tolerant: strips // comments and trailing commas) so `@/foo`
    style aliases resolve to real files instead of being treated as an
    unresolvable bare specifier — the same mistake as an unresolved npm import,
    but for a path that's actually internal to the repo."""
    aliases: list[tuple[str, Path]] = []
    skip_dirs = {'node_modules', '.git', 'dist', 'build', '.next', '.venv', 'venv'}
    for cfg_name in ('tsconfig.json', 'jsconfig.json'):
        for cfg_path in root.rglob(cfg_name):
            if any(part in skip_dirs for part in cfg_path.parts):
                continue
            try:
                raw = cfg_path.read_text(encoding='utf-8', errors='ignore')
                raw = re.sub(r'/\*.*?\*/', '', raw, flags=re.S)
                raw = re.sub(r'//[^\n]*', '', raw)
                raw = re.sub(r',(\s*[}\]])', r'\1', raw)
                cfg = json.loads(raw)
            except (OSError, json.JSONDecodeError):
                continue
            opts = cfg.get('compilerOptions', {}) if isinstance(cfg, dict) else {}
            paths = opts.get('paths', {})
            if not isinstance(paths, dict):
                continue
            cfg_root = (cfg_path.parent / opts.get('baseUrl', '.')).resolve()
            for pattern, targets in paths.items():
                if not isinstance(targets, list) or not targets:
                    continue
                prefix = pattern.split('*')[0]
                target = str(targets[0]).split('*')[0]
                aliases.append((prefix, (cfg_root / target).resolve()))
    aliases.sort(key=lambda a: -len(a[0]))  # longest/most-specific prefix wins
    return aliases


def _resolve_js_spec(spec: str, from_file: Path, js_paths: set, alias_map: list[tuple[str, Path]] = ()) -> Path | None:
    if spec.startswith('.'):
        base = (from_file.parent / spec).resolve()
    else:
        base = None
        for prefix, target_dir in alias_map:
            if spec.startswith(prefix):
                base = (target_dir / spec[len(prefix):]).resolve()
                break
        if base is None:
            return None  # bare specifier (npm package) — external, not a repo edge
    candidates = [base] + [base.with_suffix(ext) for ext in ('.ts', '.tsx', '.js', '.jsx')]
    candidates += [base / f'index{ext}' for ext in ('.ts', '.tsx', '.js', '.jsx')]
    for c in candidates:
        if c in js_paths:
            return c
    return None


def build_code_graph(root: Path, analysis: dict, detail: str = 'auto') -> dict:
    """Full module-dependency graph: every source file is a node, every real
    import is an edge, every file matching a detected component's own _RE
    pattern gets an edge to that component. Best-effort only — anything that
    can't be confidently resolved (dynamic imports, unusual layouts, Go
    without a parseable go.mod) is silently skipped rather than guessed."""
    files = _collect_graph_files(root)
    total_files = len(files)
    file_ids = {p: p.relative_to(root).as_posix() for p in files}
    file_text: dict[Path, str] = {}
    file_text_lower: dict[Path, str] = {}
    for p in files:
        try:
            file_text[p] = p.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            file_text[p] = ''
        file_text_lower[p] = file_text[p].lower()

    nodes: dict[str, dict] = {}
    for p in files:
        fid = file_ids[p]
        pkg_parts = Path(fid).parts[:-1]
        nodes[fid] = {
            'id': fid, 'label': Path(fid).name,
            'pkg': pkg_parts[0] if pkg_parts else '(root)',
            'loc': file_text[p].count('\n') + 1 if file_text[p] else 0,
            'kind': 'file',
        }

    edges: list[dict] = []
    seen: set = set()

    def add_edge(s, t, kind, w=None):
        if not s or not t or s == t:
            return
        key = (s, t, kind)
        if key in seen:
            return
        seen.add(key)
        edge = {'s': s, 't': t, 'kind': kind}
        if w is not None:
            edge['w'] = w
        edges.append(edge)

    # --- Python: real AST-parsed imports, including relative imports ---
    py_files = [p for p in files if p.suffix == '.py']
    py_mod_map = {_py_module_name(root, p): p for p in py_files}
    # Absolute imports are written relative to whatever directory is actually on
    # sys.path at runtime (e.g. `backend/`, `src/`), not the scanned repo root, so
    # `from app.core.config import x` in backend/app/core/config.py never matches
    # the root-relative name `backend.app.core.config` above. Add every dropped-
    # leading-segment suffix as a fallback candidate, but only where it's still
    # unambiguous (exactly one file could produce it) so we never guess a wrong edge.
    _suffix_owners: dict[str, set] = {}
    for p in py_files:
        parts = _py_module_name(root, p).split('.')
        for i in range(1, len(parts)):
            _suffix_owners.setdefault('.'.join(parts[i:]), set()).add(p)
    for suffix, owners in _suffix_owners.items():
        if suffix and suffix not in py_mod_map and len(owners) == 1:
            py_mod_map[suffix] = next(iter(owners))
    for p in py_files:
        fid = file_ids[p]
        try:
            tree = ast.parse(file_text[p], filename=str(p))
        except (SyntaxError, ValueError):
            continue
        dir_parts = Path(fid).parts[:-1]
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = py_mod_map.get(alias.name)
                    if target is not None:
                        add_edge(fid, file_ids[target], 'import')
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = dir_parts[:len(dir_parts) - (node.level - 1)] if node.level > 1 else dir_parts
                    if node.module:
                        mod = '.'.join((*base, node.module))
                        target = py_mod_map.get(mod)
                        if target is not None:
                            add_edge(fid, file_ids[target], 'import')
                        else:
                            for alias in node.names:
                                t2 = py_mod_map.get('.'.join((*base, node.module, alias.name)))
                                if t2 is not None:
                                    add_edge(fid, file_ids[t2], 'import')
                    else:
                        for alias in node.names:
                            target = py_mod_map.get('.'.join((*base, alias.name)))
                            if target is not None:
                                add_edge(fid, file_ids[target], 'import')
                elif node.module:
                    target = py_mod_map.get(node.module)
                    if target is not None:
                        add_edge(fid, file_ids[target], 'import')

    # --- JS/TS: regex-extracted specifiers, relative ones plus tsconfig/jsconfig aliases ---
    js_files = [p for p in files if p.suffix in ('.js', '.jsx', '.ts', '.tsx')]
    js_path_set = set(js_files)
    js_alias_map = _load_ts_path_aliases(root)
    js_import_re = re.compile(r'''(?:import\s+(?:[\w*{}\s,]+\s+from\s+)?|export\s+(?:[\w*{}\s,]+\s+from\s+)?|require\()\s*['"]([^'"]+)['"]''')
    for p in js_files:
        fid = file_ids[p]
        for m in js_import_re.finditer(file_text[p]):
            target = _resolve_js_spec(m.group(1), p, js_path_set, js_alias_map)
            if target is not None:
                add_edge(fid, file_ids[target], 'import')

    # --- Go: only when go.mod gives us a module prefix to resolve against ---
    go_files = [p for p in files if p.suffix == '.go']
    if go_files:
        gomod = _read_file(root, 'go.mod')
        m = re.search(r'^module\s+(\S+)', gomod, re.M)
        if m:
            mod_prefix = m.group(1)
            dir_to_files: dict[str, list[Path]] = {}
            for p in go_files:
                dir_to_files.setdefault(Path(file_ids[p]).parent.as_posix(), []).append(p)
            go_import_re = re.compile(r'"([^"]+)"')
            for p in go_files:
                fid = file_ids[p]
                in_block = False
                for line in file_text[p].splitlines():
                    s = line.strip()
                    if s.startswith('import ('):
                        in_block = True
                        continue
                    if in_block and s == ')':
                        in_block = False
                        continue
                    if in_block or s.startswith('import '):
                        gm = go_import_re.search(s)
                        if not gm:
                            continue
                        path = gm.group(1)
                        if path == mod_prefix:
                            rel_dir = ''
                        elif path.startswith(mod_prefix + '/'):
                            rel_dir = path[len(mod_prefix) + 1:]
                        else:
                            continue
                        for target in dir_to_files.get(rel_dir, []):
                            add_edge(fid, file_ids[target], 'import')

    # --- Java: package declaration + class-name-from-filename gives an FQN
    # map; only explicit `import` statements become edges (no same-package
    # sibling guessing — Java doesn't require importing same-package
    # classes, so we have no signal there and don't invent one). ---
    java_files = [p for p in files if p.suffix == '.java']
    if java_files:
        java_pkg_re = re.compile(r'^\s*package\s+([\w.]+)\s*;', re.M)
        java_import_re = re.compile(r'^\s*import\s+(?:static\s+)?([\w.]+)\s*;', re.M)
        java_fqn_map: dict[str, Path] = {}
        for p in java_files:
            m = java_pkg_re.search(file_text[p])
            pkg = m.group(1) if m else ''
            class_name = p.stem
            fqn = f'{pkg}.{class_name}' if pkg else class_name
            java_fqn_map[fqn] = p
        for p in java_files:
            fid = file_ids[p]
            for m in java_import_re.finditer(file_text[p]):
                imported = m.group(1)
                target = java_fqn_map.get(imported)
                if target is None and imported.endswith('.*'):
                    continue  # wildcard import — no single target file to point at
                if target is not None:
                    add_edge(fid, file_ids[target], 'import')

    # --- Rust: `mod foo;` (sibling file/dir) and `use crate::a::b::Item`
    # (resolved from the crate root, if Cargo.toml locates one). ---
    rust_files = [p for p in files if p.suffix == '.rs']
    if rust_files:
        rust_path_set = set(rust_files)
        mod_re = re.compile(r'^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)\s*;', re.M)
        use_re = re.compile(r'^\s*(?:pub\s+)?use\s+crate::([\w:]+)\s*;', re.M)
        cargo_toml = next(root.rglob('Cargo.toml'), None)
        src_root = cargo_toml.parent / 'src' if cargo_toml else None
        for p in rust_files:
            fid = file_ids[p]
            for m in mod_re.finditer(file_text[p]):
                name = m.group(1)
                for cand in (p.parent / f'{name}.rs', p.parent / name / 'mod.rs'):
                    if cand in rust_path_set:
                        add_edge(fid, file_ids[cand], 'import')
                        break
            if src_root is not None:
                for m in use_re.finditer(file_text[p]):
                    segs = m.group(1).split('::')
                    base = src_root.joinpath(*segs)
                    candidates = [base.with_suffix('.rs'), base / 'mod.rs']
                    if len(segs) > 1:
                        base2 = src_root.joinpath(*segs[:-1])
                        candidates += [base2.with_suffix('.rs'), base2 / 'mod.rs']
                    for cand in candidates:
                        if cand in rust_path_set:
                            add_edge(fid, file_ids[cand], 'import')
                            break

    # --- Ruby: `require_relative` (resolved against the file's own dir) and
    # `require` (probed against a conventional lib/ layout only — a bare
    # `require 'json'` for a stdlib/gem is correctly left unresolved). ---
    ruby_files = [p for p in files if p.suffix == '.rb']
    if ruby_files:
        ruby_path_set = set(ruby_files)
        rel_re = re.compile(r'require_relative\s+[\'"]([^\'"]+)[\'"]')
        req_re = re.compile(r'(?<!_)require\s+[\'"]([^\'"]+)[\'"]')
        for p in ruby_files:
            fid = file_ids[p]
            for m in rel_re.finditer(file_text[p]):
                # .resolve() to collapse any '../' before the set lookup —
                # require_relative commonly reaches into a sibling directory.
                cand = (p.parent / m.group(1)).resolve().with_suffix('.rb')
                if cand in ruby_path_set:
                    add_edge(fid, file_ids[cand], 'import')
            for m in req_re.finditer(file_text[p]):
                cand = root / 'lib' / (m.group(1) + '.rb')
                if cand in ruby_path_set:
                    add_edge(fid, file_ids[cand], 'import')

    # --- Service edges: same _RE pattern that already backs the summary,
    # scanned per-file so the graph shows *which* files actually call it. ---
    def add_service_group(items, name_key, re_map, icon_fn):
        for item in items:
            name = item[name_key] if isinstance(item, dict) else item
            re_key = re_map.get(name)
            if not re_key:
                continue
            sid = f'svc:{name}'
            matched = False
            for p in files:
                if _hinted_search(re_key, file_text[p], file_text_lower[p]):
                    add_edge(file_ids[p], sid, 'service')
                    matched = True
            if matched:
                color_key = item.get('color', 'gray') if isinstance(item, dict) else 'pink'
                nodes[sid] = {
                    'id': sid, 'label': name, 'pkg': '(service)', 'loc': 0,
                    'kind': 'service', 'color': C.get(color_key, C['gray']),
                    'icon': icon_fn(item),
                }

    add_service_group(analysis['llm'].get('providers', []), None, _LLM_RE_KEYS, lambda i: '🧠')
    add_service_group(analysis['storage'], 'name', _STORAGE_RE_KEYS, lambda i: _STORE_ICONS.get(i['type'], '📦'))
    add_service_group(analysis['queues'], 'name', _QUEUE_RE_KEYS, lambda i: '📨')
    add_service_group([s for s in analysis['external_sources'] if s['name'] in _EXTSRC_RE_KEYS],
                       'name', _EXTSRC_RE_KEYS, lambda i: '🌐')

    # --- Entry node: HTTP clients -> every file with a route decorator.
    # When an --access-log was supplied, weight each edge with the real
    # request count observed for the routes that specific file declares
    # (same route-string construction detect_api_server() uses — see
    # _extract_route_strings — just applied per file). No log -> no weight,
    # never a guessed one. ---
    route_patterns = [_RE['fastapi_route'], _RE['flask_route'], _RE['django_path'], _RE['express_route']]
    access_log = analysis.get('access_log')
    framework = analysis.get('framework')
    entry_used = False
    for p in files:
        text = file_text[p]
        if any(pat.search(text) for pat in route_patterns):
            w = None
            if access_log:
                file_routes = _extract_route_strings(text, framework)
                observed = sum(access_log['by_route'].get(r, 0) for r in file_routes)
                w = observed or None
            add_edge(_GRAPH_ENTRY_ID, file_ids[p], 'entry', w=w)
            entry_used = True
    if entry_used:
        nodes[_GRAPH_ENTRY_ID] = {
            'id': _GRAPH_ENTRY_ID, 'label': 'HTTP Clients', 'pkg': '(entry)',
            'loc': 0, 'kind': 'entry', 'color': C['green'], 'icon': '🌐',
        }

    file_node_count = sum(1 for n in nodes.values() if n['kind'] == 'file')
    should_aggregate = (detail == 'dirs') or (detail == 'auto' and file_node_count > _GRAPH_FILE_CAP)
    aggregated = False
    if should_aggregate:
        nodes, edges = _aggregate_graph_dirs(nodes, edges)
        aggregated = True
    elif detail == 'files' and file_node_count > _GRAPH_WARN_FILES:
        print(f"Warning: --graph-detail=files forcing {file_node_count} file-level nodes — rendering may be sluggish.", file=sys.stderr)

    return {
        'nodes': list(nodes.values()),
        'links': edges,
        'meta': {
            'files': total_files,
            'links': len(edges),
            'aggregated': aggregated,
            'shown_nodes': len(nodes),
            'has_access_log': bool(access_log),
        },
    }


def _aggregate_graph_dirs(nodes: dict, edges: list, depth: int = 2) -> tuple[dict, list]:
    """Collapse file nodes into directory nodes (service/entry nodes untouched)
    when the file-level graph would be too dense to render usefully. Parallel
    edges between the same pair are merged into one, weighted edge."""
    def dir_id(fid: str) -> str:
        parts = Path(fid).parts[:-1][:depth] or ('(root)',)
        return 'dir:' + '/'.join(parts)

    remap: dict[str, str] = {}
    dir_nodes: dict[str, dict] = {}
    other_nodes: dict[str, dict] = {}
    for nid, n in nodes.items():
        if n['kind'] != 'file':
            other_nodes[nid] = n
            continue
        did = dir_id(nid)
        remap[nid] = did
        d = dir_nodes.setdefault(did, {'id': did, 'label': did.split(':', 1)[1], 'pkg': n['pkg'],
                                        'loc': 0, 'kind': 'dir', 'file_count': 0})
        d['loc'] += n['loc']
        d['file_count'] += 1

    merged: dict[tuple, dict] = {}
    for e in edges:
        s2, t2 = remap.get(e['s'], e['s']), remap.get(e['t'], e['t'])
        if s2 == t2:
            continue
        key = (s2, t2, e['kind'])
        # 'w' on a pre-aggregation edge is a real observed count (access-log
        # weighted entry edges); absent 'w' just means "one edge" — sum
        # either way so real request counts survive aggregation intact
        # instead of being overwritten by a duplicate-count of 1.
        w = e.get('w', 1)
        if key in merged:
            merged[key]['w'] += w
        else:
            merged[key] = {'s': s2, 't': t2, 'kind': e['kind'], 'w': w}

    return {**dir_nodes, **other_nodes}, list(merged.values())


# ── collect + main ─────────────────────────────────────────────────────────────

def collect(root: Path, graph_detail: str = 'auto', access_log_path: str | None = None) -> dict:
    # Resolve once, up front: the graph builder compares Path objects for set
    # membership (js_paths, byId), and an unresolved relative root (the default —
    # `analyze.py .` is the most common invocation) makes every file path relative
    # while resolved candidate paths downstream are absolute, so equality silently
    # never matches and every JS/TS edge is dropped without error.
    root = root.resolve()
    workers = detect_workers(root)
    gateway = detect_gateway(root)
    api_server = detect_api_server(root)
    frontend = detect_frontend(root)
    concur = detect_concurrency(root)
    llm = detect_llm(root)
    storage = detect_storage(root)
    queues = detect_queues(root)
    external_sources = detect_external_sources(root)
    capacity = compute_concurrency(workers, gateway, concur, llm, api_server)
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
    access_log = parse_access_log(access_log_path, api_server.get('routes', [])) if access_log_path else None
    graph = build_code_graph(root, {
        'llm': llm, 'storage': storage, 'queues': queues, 'external_sources': external_sources,
        'framework': api_server.get('framework'), 'access_log': access_log,
    }, detail=graph_detail)
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
        'graph': graph,
        'access_log': access_log,
    }


def main():
    # Manual flag parsing (no argparse dependency) so the existing positional
    # usage — `analyze.py [dir] [out]` — keeps working unchanged.
    argv = sys.argv[1:]
    graph_detail = 'auto'
    access_log_path = None
    positional = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ('--graph-detail',) and i + 1 < len(argv):
            graph_detail = argv[i + 1]; i += 2; continue
        if a.startswith('--graph-detail='):
            graph_detail = a.split('=', 1)[1]; i += 1; continue
        if a in ('--access-log',) and i + 1 < len(argv):
            access_log_path = argv[i + 1]; i += 2; continue
        if a.startswith('--access-log='):
            access_log_path = a.split('=', 1)[1]; i += 1; continue
        positional.append(a); i += 1

    if graph_detail not in ('auto', 'files', 'dirs'):
        print(f"Warning: unknown --graph-detail={graph_detail!r} (expected auto|files|dirs) — using 'auto'.", file=sys.stderr)
        graph_detail = 'auto'

    root   = Path(positional[0]) if len(positional) > 0 else Path('.')
    output = Path(positional[1]) if len(positional) > 1 else root / 'WORKFLOW.html'

    project_name = detect_project_name(root) or root.resolve().name.replace('-', ' ').replace('_', ' ').title()
    analysis = collect(root, graph_detail=graph_detail, access_log_path=access_log_path)

    output.write_text(render_html(analysis, project_name))

    cap = analysis['capacity']
    print(f"Written: {output}")
    print(f"Framework: {analysis['api_server']['framework']} · Workers: {cap['total_workers']} · Concurrent I/O: ~{cap['total_io']}")
    print(f"Bottleneck: {cap['bottleneck']} · Practical throughput (estimated): {cap['practical']}")
    if analysis['gateway']:
        print(f"Gateway: {analysis['gateway']['type']} · {len(analysis['gateway']['rate_limits'])} rate limit zone(s)")
    if analysis['llm']['providers']:
        print(f"LLM: {', '.join(analysis['llm']['providers'])} · eval: {analysis['llm'].get('eval_framework') or 'none'}")
    if analysis['llm'].get('providers_declared'):
        print(f"LLM (declared dependency, unconfirmed usage): {', '.join(analysis['llm']['providers_declared'])}")
    print(f"Storage: {', '.join(s['name'] for s in analysis['storage'])}")
    print(f"External sources: {', '.join(s['name'] for s in analysis['external_sources'])}")
    gm = analysis['graph']['meta']
    print(f"Graph: {gm['files']} files · {gm['links']} import/service links{' (aggregated to ' + str(gm['shown_nodes']) + ' dir nodes)' if gm['aggregated'] else ''}")


if __name__ == '__main__':
    main()
