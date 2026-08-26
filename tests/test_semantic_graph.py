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
