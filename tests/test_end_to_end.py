from conftest import write_project

PROJECT_FILES = {
    "app.py": (
        "from fastapi import FastAPI\n"
        "import uvicorn\n"
        "from openai import OpenAI\n"
        "import redis\n"
        "from celery import Celery\n"
        "\n"
        "app = FastAPI()\n"
        "client = OpenAI()\n"
        "r = redis.Redis(host='localhost')\n"
        "celery_app = Celery('tasks')\n"
        "\n"
        "@app.get('/items/{item_id}')\n"
        "def get_item(item_id: int):\n"
        "    return {'id': item_id}\n"
    ),
    "docker-compose.yml": "command: uvicorn app:app --workers 4\n",
    "nginx.conf": (
        "limit_req_zone $binary_remote_addr zone=api:10m rate=60r/m;\n"
        "limit_req zone=api burst=20;\n"
    ),
    "requirements.txt": "fastapi\nuvicorn\nopenai\nredis\ncelery\n",
}


def test_full_pipeline_collect_and_render(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, PROJECT_FILES)
    analysis = az.collect(root)

    assert analysis['api_server']['framework'] == 'FastAPI'
    assert 'OpenAI' in analysis['llm']['providers']
    assert any(s['name'] == 'Redis' for s in analysis['storage'])
    assert any(q['name'] == 'Celery' for q in analysis['queues'])
    assert analysis['gateway']['type'] == 'nginx'

    graph = analysis['graph']
    assert graph['meta']['files'] >= 1
    assert graph['meta']['shown_nodes'] <= graph['meta']['files'] + len(
        [n for n in graph['nodes'] if n['kind'] != 'file']
    )

    html = az.render_html(analysis, "test-project")
    assert '<html' in html.lower()
    assert 'FastAPI' in html
    assert 'Redis' in html
    assert 'Celery' in html


def test_full_pipeline_with_access_log(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, PROJECT_FILES)
    log = root / "access.log"
    log.write_text(
        '127.0.0.1 - - [10/Oct/2023:13:55:00 +0000] "GET /items/1 HTTP/1.1" 200 100\n'
        '127.0.0.1 - - [10/Oct/2023:13:55:30 +0000] "GET /items/2 HTTP/1.1" 200 100\n'
    )
    analysis = az.collect(root, access_log_path=str(log))
    assert analysis['access_log'] is not None
    assert analysis['access_log']['total'] == 2
    assert analysis['graph']['meta']['has_access_log'] is True

    html = az.render_html(analysis, "test-project")
    assert '<html' in html.lower()
