import json

from conftest import write_project


# ── detect_crons ──────────────────────────────────────────────────────────

def test_detect_crons_celery_beat(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "tasks.py": "from celery import Celery\napp = Celery('t')\nbeat_schedule = {}\n",
    })
    crons = az.detect_crons(root)
    assert any(c["type"] == "celery" for c in crons)


def test_detect_crons_apscheduler(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "sched.py": "from apscheduler.schedulers.background import BackgroundScheduler\n",
    })
    crons = az.detect_crons(root)
    assert any(c["type"] == "apscheduler" for c in crons)


def test_detect_crons_schedule_library(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "sched.py": "import schedule\nschedule.every(10).minutes.do(job)\n",
    })
    crons = az.detect_crons(root)
    assert any(c["type"] == "schedule" for c in crons)


def test_detect_crons_github_actions_schedule(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        ".github/workflows/nightly.yml": "on:\n  schedule:\n    - cron: '0 3 * * *'\n",
    })
    crons = az.detect_crons(root)
    assert any(c["type"] == "github_actions" for c in crons)


def test_detect_crons_empty_when_nothing_matches(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('hello')\n"})
    assert az.detect_crons(root) == []


# ── detect_tools ──────────────────────────────────────────────────────────

def test_detect_tools_langchain(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "tools.py": "from langchain.tools import tool\n\n@tool\ndef search(q: str): ...\n",
    })
    tools = az.detect_tools(root)
    assert any(t["type"] == "langchain_tools" for t in tools)


def test_detect_tools_openai_functions_requires_openai_hint(az_module, tmp_path):
    az = az_module
    # tools=[...] alone (no OpenAI SDK signal) should NOT be misattributed to OpenAI.
    root = write_project(tmp_path, {"app.py": "tools = [1, 2, 3]\n"})
    tools = az.detect_tools(root)
    assert not any(t["type"] == "openai_functions" for t in tools)


def test_detect_tools_openai_functions_with_hint(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "app.py": (
            "from openai import OpenAI\n"
            "client = OpenAI()\n"
            "tools = [{'type': 'function', 'function': {'name': 'get_weather'}}]\n"
        ),
    })
    tools = az.detect_tools(root)
    assert any(t["type"] == "openai_functions" for t in tools)


def test_detect_tools_empty_when_nothing_matches(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('hello')\n"})
    assert az.detect_tools(root) == []


# ── detect_agents ─────────────────────────────────────────────────────────

def test_detect_agents_langchain_executor(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "agent.py": "from langchain.agents import AgentExecutor, create_react_agent\n",
    })
    agents = az.detect_agents(root)
    assert any(a["type"] == "langchain_agent" for a in agents)


def test_detect_agents_crewai_requires_crewai_hint(az_module, tmp_path):
    az = az_module
    # A bare "Agent(" call with no crewai import shouldn't be misattributed.
    root = write_project(tmp_path, {"app.py": "x = Agent(name='x')\n"})
    agents = az.detect_agents(root)
    assert not any(a["type"] == "crewai_agent" for a in agents)


def test_detect_agents_crewai_with_hint(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "agent.py": "from crewai import Agent\nresearcher = Agent(role='researcher')\n",
    })
    agents = az.detect_agents(root)
    assert any(a["type"] == "crewai_agent" for a in agents)


def test_detect_agents_empty_when_nothing_matches(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('hello')\n"})
    assert az.detect_agents(root) == []


# ── detect_composition_root ───────────────────────────────────────────────

def test_detect_composition_root_fastapi(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "app/main.py": (
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "app.add_middleware(CORSMiddleware)\n"
        ),
    })
    comp = az.detect_composition_root(root)
    assert comp is not None
    assert comp["framework"] == "FastAPI"
    assert comp["file"] == "app/main.py"
    assert comp["has_middleware"] is True


def test_detect_composition_root_flask(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "app.py": "from flask import Flask\napp = Flask(__name__)\n",
    })
    comp = az.detect_composition_root(root)
    assert comp is not None
    assert comp["framework"] == "Flask"


def test_detect_composition_root_express(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "server.js": "const express = require('express');\nconst app = express();\napp.use(cors());\n",
    })
    comp = az.detect_composition_root(root)
    assert comp is not None
    assert comp["framework"] == "Express"
    assert comp["has_middleware"] is True


def test_detect_composition_root_none_when_no_framework(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"script.py": "print('just a script')\n"})
    assert az.detect_composition_root(root) is None


# ── build_semantic_graph ──────────────────────────────────────────────────

def _fastapi_project(tmp_path):
    return write_project(tmp_path, {
        "app/main.py": (
            "from fastapi import FastAPI\n"
            "app = FastAPI()\n"
            "app.add_middleware(CORSMiddleware)\n"
        ),
        "app/api/routes/users.py": (
            "from fastapi import APIRouter\n"
            "from app import crud\n"
            "router = APIRouter()\n"
            "@router.get('/{user_id}')\n"
            "def get_user(user_id: str):\n"
            "    return crud.get_user_by_email(email='x')\n"
        ),
        "app/api/routes/items.py": (
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n"
            "@router.get('/')\n"
            "def list_items():\n"
            "    return []\n"
        ),
        "app/crud.py": (
            "def get_user_by_email(email):\n"
            "    return None\n"
        ),
    })


def test_build_semantic_graph_creates_composition_root_and_entries(az_module, tmp_path):
    az = az_module
    root = _fastapi_project(tmp_path)
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': az.detect_composition_root(root),
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    kinds = {n['kind'] for n in sg['graph']['nodes']}
    assert 'service' in kinds  # composition root + crud service
    assert 'entry' in kinds
    labels = {n['label'] for n in sg['graph']['nodes']}
    assert 'Users API' in labels
    assert 'Items API' in labels


def test_build_semantic_graph_links_entry_to_service_only_when_referenced(az_module, tmp_path):
    # users.py imports+calls crud.py -> should get a 'calls' edge to the CRUD
    # service node. items.py does NOT reference crud.py -> must NOT get one.
    # (Regression test for the N x M edge-fanout bug found during manual review.)
    az = az_module
    root = _fastapi_project(tmp_path)
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': az.detect_composition_root(root),
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    edges = sg['graph']['edges']
    users_to_crud = [e for e in edges if e['from'] == 'entry-users' and e['to'] == 'service-crud']
    items_to_crud = [e for e in edges if e['from'] == 'entry-items' and e['to'] == 'service-crud']
    assert len(users_to_crud) == 1
    assert len(items_to_crud) == 0


def test_build_semantic_graph_node_members_tracks_file_paths(az_module, tmp_path):
    az = az_module
    root = _fastapi_project(tmp_path)
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': az.detect_composition_root(root),
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    members = sg['node_members']
    assert 'app/api/routes/users.py' in members['entry-users']
    assert 'app/crud.py' in members['service-crud']


def test_build_semantic_graph_excludes_non_integration_external_sources(az_module, tmp_path):
    # "Users / API Clients" and "Cron / Scheduler" are synthetic entries
    # detect_external_sources() always/sometimes adds; neither is a real
    # third-party integration and both must be filtered out of the semantic
    # graph's external nodes (regression test for the bug found during review).
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('x')\n"})
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [
            {'name': 'Users / API Clients'},
            {'name': 'Cron / Scheduler'},
            {'name': 'Stripe'},
        ],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': None,
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    ext_labels = {n['label'] for n in sg['graph']['nodes'] if n['kind'] == 'external'}
    assert ext_labels == {'Stripe'}


def test_build_semantic_graph_stats_reflect_zero_ai_for_non_ai_repo(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('x')\n"})
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': None,
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    assert sg['stats'] == {'agents': 0, 'models': 0, 'tools': 0, 'integrations': 0}


def test_build_semantic_graph_agent_only_created_when_tools_present(az_module, tmp_path):
    # An agent framework match with no tool signal shouldn't fabricate an
    # agent node in isolation from the rest of the "never guess" philosophy
    # this function follows elsewhere.
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('x')\n"})
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [{'type': 'langchain_agent', 'name': 'LangChain Agent', 'framework': 'LangChain'}],
        'composition_root': None,
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    assert not any(n['kind'] == 'agent' for n in sg['graph']['nodes'])


def test_build_semantic_graph_agent_created_with_tools_present(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('x')\n"})
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [],
        'crons': [],
        'tools': [{'type': 'langchain_tools', 'name': 'LangChain Tools'}],
        'agents': [{'type': 'langchain_agent', 'name': 'LangChain Agent', 'framework': 'LangChain'}],
        'composition_root': None,
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    assert any(n['kind'] == 'agent' for n in sg['graph']['nodes'])
    assert sg['stats']['agents'] == 1


def test_build_semantic_graph_store_domain_from_known_brand(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('x')\n"})
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [{'name': 'PostgreSQL', 'type': 'relational'}],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': None,
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    store_nodes = [n for n in sg['graph']['nodes'] if n['kind'] == 'store']
    assert len(store_nodes) == 1
    assert store_nodes[0]['domain'] == 'postgresql.org'


def test_build_semantic_graph_cron_links_to_composition_root_not_all_services(az_module, tmp_path):
    # Regression test: a detected cron pattern must not be wired to every
    # service found anywhere in the repo (an honest "never fabricate a
    # connection we can't confirm" constraint) — it should only link to the
    # composition root, if one exists.
    az = az_module
    root = _fastapi_project(tmp_path)
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [],
        'crons': [{'type': 'celery', 'name': 'Celery Beat', 'detail': 'Periodic tasks'}],
        'tools': [],
        'agents': [],
        'composition_root': az.detect_composition_root(root),
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    cron_edges = [e for e in sg['graph']['edges'] if e['from'] == 'cron-celery']
    assert len(cron_edges) == 1
    assert cron_edges[0]['to'] == 'app-root'


def test_build_semantic_graph_caps_nodes_at_60(az_module, tmp_path):
    az = az_module
    files = {f"app/routes/r{i}.py": f"from fastapi import APIRouter\nrouter = APIRouter()\n@router.get('/{i}')\ndef h(): ...\n" for i in range(80)}
    root = write_project(tmp_path, files)
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': None,
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    assert len(sg['graph']['nodes']) <= 60


def test_build_semantic_graph_top_integrations_populated(az_module, tmp_path):
    # Regression test: topIntegrations used an undefined `ext_id` variable
    # in its list comprehension (UnboundLocalError), only surfaced when
    # build_semantic_graph() actually ran end-to-end against a repo with a
    # real external integration (caught while regenerating the FastAPI
    # template demo, not by any prior unit test).
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('x')\n"})
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [{'name': 'Stripe'}],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': None,
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    assert sg['topIntegrations'] == [{'id': 'stripe', 'label': 'Stripe', 'domain': 'stripe.com'}]


def _orm_session_project(tmp_path):
    # crud.py never spells out "postgresql" anywhere (the connection lives
    # in a separate core/db.py this fixture doesn't even need) — it only
    # talks to the store through a generic SQLModel/SQLAlchemy-style
    # session, which is how most layered ORM apps actually look.
    return write_project(tmp_path, {
        "app/crud.py": (
            "from sqlmodel import Session\n"
            "def create_user(session: Session, user):\n"
            "    session.add(user)\n"
            "    session.commit()\n"
            "    session.refresh(user)\n"
            "    return user\n"
        ),
    })


def test_build_semantic_graph_links_orm_session_to_sole_store(az_module, tmp_path):
    # Regression test: Postgres was showing up with zero edges in the real
    # FastAPI template demo because the literal-name heuristic requires
    # "postgres" to appear in crud.py's own text, which it never does for
    # SQLModel/SQLAlchemy-style layered apps. When exactly one non-cache
    # store is detected repo-wide, a generic session.add()/session.exec()
    # call is enough to honestly infer the connection.
    az = az_module
    root = _orm_session_project(tmp_path)
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [{'name': 'PostgreSQL', 'type': 'relational'}],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': None,
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    edges = sg['graph']['edges']
    to_store = [e for e in edges if e['to'] == 'store-postgresql']
    assert len(to_store) == 1
    assert to_store[0]['from'] == 'service-crud'


def test_build_semantic_graph_orm_session_skips_ambiguous_multi_store(az_module, tmp_path):
    # With two non-cache stores present, a bare session.add() doesn't say
    # which one it means — never fabricate a connection when it's genuinely
    # ambiguous which store is meant.
    az = az_module
    root = _orm_session_project(tmp_path)
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [
            {'name': 'PostgreSQL', 'type': 'relational'},
            {'name': 'MongoDB', 'type': 'nosql'},
        ],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': None,
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    edges = sg['graph']['edges']
    service_to_store = [e for e in edges if e['from'] == 'service-crud' and e['to'].startswith('store-')]
    assert service_to_store == []


# ── enrich_service_labels (local `claude` CLI shell-out, opt-in) ─────────────
# All of these mock the subprocess boundary — a real `claude` process is never
# invoked in tests: that would be non-deterministic, slow, and require auth.

def _semantic_graph_with_one_service(az, tmp_path):
    root = _fastapi_project(tmp_path)
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': az.detect_composition_root(root),
        'llm': {'providers': []},
    }
    return root, az.build_semantic_graph(root, analysis)


def test_enrich_service_labels_noop_when_claude_not_on_path(az_module, tmp_path, monkeypatch):
    az = az_module
    root, sg = _semantic_graph_with_one_service(az, tmp_path)
    monkeypatch.setattr(az.shutil, 'which', lambda _: None)

    def _boom(*a, **k):
        raise AssertionError("subprocess.run must not be called when claude isn't on PATH")
    monkeypatch.setattr(az.subprocess, 'run', _boom)

    before = [dict(n) for n in sg['graph']['nodes']]
    out = az.enrich_service_labels(root, sg)
    assert out['graph']['nodes'] == before


def test_collect_never_shells_out_when_enrich_labels_false(az_module, tmp_path, monkeypatch):
    # The default (enrich_labels=False) path must never touch the subprocess
    # boundary at all, regardless of whether claude happens to be on PATH.
    az = az_module
    root = _fastapi_project(tmp_path)

    def _boom(*a, **k):
        raise AssertionError("subprocess.run must not be called when enrich_labels=False")
    monkeypatch.setattr(az.subprocess, 'run', _boom)
    monkeypatch.setattr(az.shutil, 'which', lambda _: '/usr/bin/claude')

    az.collect(root, enrich_labels=False)  # must not raise


def test_enrich_service_labels_applies_valid_relabel(az_module, tmp_path, monkeypatch):
    az = az_module
    root, sg = _semantic_graph_with_one_service(az, tmp_path)
    monkeypatch.setattr(az.shutil, 'which', lambda _: '/usr/bin/claude')

    payload = json.dumps([
        {'id': 'service-crud', 'label': 'User records', 'sub': 'reads/writes user rows', 'detail': 'x'},
    ])

    class _FakeProc:
        returncode = 0
        stdout = json.dumps({'result': payload})

    monkeypatch.setattr(az.subprocess, 'run', lambda *a, **k: _FakeProc())
    out = az.enrich_service_labels(root, sg)
    crud = next(n for n in out['graph']['nodes'] if n['id'] == 'service-crud')
    assert crud['label'] == 'User records'
    assert crud['sub'] == 'reads/writes user rows'
    # untouched fields
    assert crud['kind'] == 'service'
    assert crud['sourceRef'] == 'app/crud.py'


def test_enrich_service_labels_truncates_oversized_fields(az_module, tmp_path, monkeypatch):
    az = az_module
    root, sg = _semantic_graph_with_one_service(az, tmp_path)
    monkeypatch.setattr(az.shutil, 'which', lambda _: '/usr/bin/claude')

    long_label = 'X' * 200
    payload = json.dumps([{'id': 'service-crud', 'label': long_label}])

    class _FakeProc:
        returncode = 0
        stdout = json.dumps({'result': payload})

    monkeypatch.setattr(az.subprocess, 'run', lambda *a, **k: _FakeProc())
    out = az.enrich_service_labels(root, sg)
    crud = next(n for n in out['graph']['nodes'] if n['id'] == 'service-crud')
    assert len(crud['label']) == az._ENRICH_LABEL_MAX


def test_enrich_service_labels_ignores_unknown_ids(az_module, tmp_path, monkeypatch):
    az = az_module
    root, sg = _semantic_graph_with_one_service(az, tmp_path)
    monkeypatch.setattr(az.shutil, 'which', lambda _: '/usr/bin/claude')
    before_label = next(n for n in sg['graph']['nodes'] if n['id'] == 'service-crud')['label']

    payload = json.dumps([{'id': 'service-does-not-exist', 'label': 'Whatever'}])

    class _FakeProc:
        returncode = 0
        stdout = json.dumps({'result': payload})

    monkeypatch.setattr(az.subprocess, 'run', lambda *a, **k: _FakeProc())
    out = az.enrich_service_labels(root, sg)
    crud = next(n for n in out['graph']['nodes'] if n['id'] == 'service-crud')
    assert crud['label'] == before_label


def test_enrich_service_labels_handles_malformed_json_response(az_module, tmp_path, monkeypatch):
    az = az_module
    root, sg = _semantic_graph_with_one_service(az, tmp_path)
    monkeypatch.setattr(az.shutil, 'which', lambda _: '/usr/bin/claude')
    before = [dict(n) for n in sg['graph']['nodes']]

    class _FakeProc:
        returncode = 0
        stdout = 'not json at all'

    monkeypatch.setattr(az.subprocess, 'run', lambda *a, **k: _FakeProc())
    out = az.enrich_service_labels(root, sg)
    assert out['graph']['nodes'] == before


def test_enrich_service_labels_handles_nonzero_exit(az_module, tmp_path, monkeypatch):
    az = az_module
    root, sg = _semantic_graph_with_one_service(az, tmp_path)
    monkeypatch.setattr(az.shutil, 'which', lambda _: '/usr/bin/claude')
    before = [dict(n) for n in sg['graph']['nodes']]

    class _FakeProc:
        returncode = 1
        stdout = ''

    monkeypatch.setattr(az.subprocess, 'run', lambda *a, **k: _FakeProc())
    out = az.enrich_service_labels(root, sg)
    assert out['graph']['nodes'] == before


def test_enrich_service_labels_handles_timeout(az_module, tmp_path, monkeypatch):
    az = az_module
    root, sg = _semantic_graph_with_one_service(az, tmp_path)
    monkeypatch.setattr(az.shutil, 'which', lambda _: '/usr/bin/claude')
    before = [dict(n) for n in sg['graph']['nodes']]

    def _timeout(*a, **k):
        raise az.subprocess.TimeoutExpired(cmd='claude', timeout=45)
    monkeypatch.setattr(az.subprocess, 'run', _timeout)

    out = az.enrich_service_labels(root, sg)
    assert out['graph']['nodes'] == before


def test_enrich_service_labels_noop_when_no_service_nodes(az_module, tmp_path, monkeypatch):
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('x')\n"})
    analysis = {
        'project_name': 'Demo',
        'api_server': {'routes': []},
        'storage': [],
        'external_sources': [],
        'crons': [],
        'tools': [],
        'agents': [],
        'composition_root': None,
        'llm': {'providers': []},
    }
    sg = az.build_semantic_graph(root, analysis)
    assert not any(n['kind'] == 'service' for n in sg['graph']['nodes'])
    monkeypatch.setattr(az.shutil, 'which', lambda _: '/usr/bin/claude')

    def _boom(*a, **k):
        raise AssertionError("subprocess.run must not be called when there are no service nodes")
    monkeypatch.setattr(az.subprocess, 'run', _boom)

    az.enrich_service_labels(root, sg)  # must not raise
