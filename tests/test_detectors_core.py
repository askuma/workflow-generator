from conftest import write_project


def test_uvicorn_gunicorn_replicas_pm2_celery(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "docker-compose.yml": "command: uvicorn app:app --workers 4\nreplicas: 3\n",
        "Procfile": "web: gunicorn -w 2 app:app\n",
        "ecosystem.config.js": "module.exports = { apps: [{ instances: 5 }] }\n",
        "app.py": "from fastapi import FastAPI\n",
    })
    w = az.detect_workers(root)
    assert w["uvicorn_workers"] == 4
    assert w["gunicorn_workers"] == 2
    assert w["replicas"] == 3
    assert w["pm2_instances"] == 5
    assert w["is_async"] is True


def test_workers_defaults_when_nothing_detected(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('hello')\n"})
    w = az.detect_workers(root)
    assert w["uvicorn_workers"] is None
    assert w["gunicorn_workers"] is None
    assert w["replicas"] == 1
    assert w["is_async"] is False


def test_gateway_nginx_rate_limit_and_worker_connections(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "nginx.conf": (
            "worker_connections 1024;\n"
            "limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;\n"
            "limit_req zone=api burst=20;\n"
        ),
    })
    gw = az.detect_gateway(root)
    assert gw["type"] == "nginx"
    assert gw["worker_connections"] == 1024
    assert gw["rate_limits"] == [{"zone": "api", "rate": "60r/m", "burst": 20}]


def test_gateway_caddy_and_traefik(az_module, tmp_path):
    az = az_module
    caddy_root = write_project(tmp_path / "caddy", {"Caddyfile": "example.com { reverse_proxy app:8000 }\n"})
    assert az.detect_gateway(caddy_root)["type"] == "Caddy"

    traefik_root = write_project(tmp_path / "traefik", {"traefik.yml": "entryPoints:\n  web:\n"})
    assert az.detect_gateway(traefik_root)["type"] == "Traefik"


def test_gateway_none_when_nothing_present(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('hi')\n"})
    assert az.detect_gateway(root) is None


def test_api_server_fastapi_routes_and_auth(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "app.py": (
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "@app.get('/items/{item_id}')\n"
            "def get_item(): pass\n"
            "@app.post('/webhook/github')\n"
            "def hook():\n"
            "    hmac.new(b'x', b'y')\n"
        ),
    })
    api = az.detect_api_server(root)
    assert api["framework"] == "FastAPI"
    assert "GET /items/{item_id}" in api["routes"]
    assert "POST /webhook/github" in api["routes"]
    assert api["has_webhooks"] is True
    assert api["auth"]["hmac"] is True


def test_api_server_flask_and_slowapi_rate_limit(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "app.py": (
            "from flask import Flask\n"
            "app = Flask(__name__)\n"
            "@app.route('/ping')\n"
            "@limiter.limit(\"100 per minute\")\n"
            "def ping(): pass\n"
        ),
    })
    api = az.detect_api_server(root)
    assert api["framework"] == "Flask"
    assert "* /ping" in api["routes"]
    assert api["app_rate_limits"] == [{"rate": "100", "unit": "minute"}]


def test_api_server_express_routes(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "index.js": "const express = require('express');\napp.get('/health', handler);\n",
    })
    api = az.detect_api_server(root)
    assert api["framework"] == "Express"
    assert "GET /health" in api["routes"]


def test_frontend_detection(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "package.json": '{"dependencies": {"next": "^14.0.0"}}',
        "app.py": "import streamlit as st\n",
    })
    names = {f["name"] for f in az.detect_frontend(root)}
    assert names == {"Next.js", "Streamlit"}


def test_concurrency_semaphore_and_primitives(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "worker.py": (
            "import asyncio\n"
            "sem = asyncio.Semaphore(8)\n"
            "lock = asyncio.Lock()\n"
            "await loop.run_in_executor(None, fn)\n"
            "await asyncio.gather(a(), b())\n"
            "BATCH_SIZE = 32\n"
            "chunk_size = 512\n"
        ),
    })
    c = az.detect_concurrency(root)
    assert c["semaphores"] == [8]
    assert c["has_lock"] is True
    assert c["has_executor"] is True
    assert c["has_gather"] is True
    assert c["batch_size"] == 32
    assert c["chunk_size"] == 512
