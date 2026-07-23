from conftest import write_project

LLM_SNIPPETS = {
    "OpenAI": "from openai import OpenAI\nclient = OpenAI()\n",
    "Anthropic": "from anthropic import Anthropic\nclient = Anthropic()\n",
    "Cohere": "client = cohere.Client('key')\n",
    "AWS Bedrock": "client = boto3.client('bedrock-runtime')\n",
    "Google Gemini": "import google.generativeai as genai\n",
    "Mistral": "client = MistralClient()\n",
    "Groq": "from groq import Groq\n",
    "Ollama": "import ollama\n",
    "LiteLLM (multi-provider)": "import litellm\nlitellm.completion(model='gpt-4')\n",
}


def test_detect_llm_all_providers_confirmed(az_module, tmp_path):
    az = az_module
    src = "\n".join(LLM_SNIPPETS.values())
    root = write_project(tmp_path, {"app.py": src})
    llm = az.detect_llm(root)
    assert set(llm["providers"]) == set(LLM_SNIPPETS.keys())


def test_detect_llm_declared_vs_confirmed(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "requirements.txt": "mistralai==0.5.0\n",
        "app.py": "# calls Mistral through our own wrapper, not the SDK class directly\n",
    })
    llm = az.detect_llm(root)
    assert llm["providers"] == []
    assert "Mistral" in llm["providers_declared"]


def test_detect_llm_timeout_retries_models(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "app.py": (
            "from openai import OpenAI\n"
            "client = OpenAI(request_timeout=45, max_retries=3)\n"
            "model = 'gpt-4o-mini'\n"
        ),
    })
    llm = az.detect_llm(root)
    assert llm["timeout"] == 45
    assert llm["retries"] == 3
    assert "gpt-4o-mini" in llm["models"]


STORAGE_SNIPPETS = {
    "Qdrant": ("vector", "from qdrant_client import QdrantClient\n"),
    "Pinecone": ("vector", "import pinecone\n"),
    "Weaviate": ("vector", "import weaviate\n"),
    "ChromaDB": ("vector", "import chromadb\n"),
    "pgvector": ("vector", "# uses pgvector extension on postgres\n"),
    "FAISS": ("vector", "import faiss\n"),
    "Milvus": ("vector", "from pymilvus import connections\n"),
    "PostgreSQL": ("relational", "psycopg2.connect(dsn)\n"),
    "MySQL": ("relational", "import pymysql\n"),
    "MongoDB": ("nosql", "import motor.motor_asyncio\n"),
    "SQLite": ("relational", "engine = create_engine('sqlite:///db.sqlite3')\n"),
    "Redis": ("cache", "r = redis.Redis(host='localhost')\n"),
    "S3 / Object Store": ("object", "s3 = boto3.client('s3')\n"),
}


def test_detect_storage_all_types(az_module, tmp_path):
    az = az_module
    src = "\n".join(s for _, s in STORAGE_SNIPPETS.values())
    root = write_project(tmp_path, {"app.py": src})
    stores = az.detect_storage(root)
    names = {s["name"] for s in stores}
    assert names == set(STORAGE_SNIPPETS.keys())
    for s in stores:
        expected_type = STORAGE_SNIPPETS[s["name"]][0]
        assert s["type"] == expected_type


def test_detect_storage_postgres_via_psycopg_prefilter(az_module, tmp_path):
    # Regression test for the exact bug this session caught: 'psycopg' alone
    # (no literal "postgres" substring) must still register PostgreSQL —
    # the _LOWER_HINTS prefilter for 'postgres' must include 'psycopg'.
    az = az_module
    root = write_project(tmp_path, {"db.py": "import psycopg2\nconn = psycopg2.connect(dsn)\n"})
    names = {s["name"] for s in az.detect_storage(root)}
    assert "PostgreSQL" in names


QUEUE_SNIPPETS = {
    "Celery": "from celery import Celery\napp = Celery('tasks')\n",
    "BullMQ": "const { Queue } = require('bullmq');\n",
    "Kafka": "from kafka import KafkaProducer\n",
    "RabbitMQ": "import pika\nconn = pika.BlockingConnection()\n",
    "RQ (Redis Queue)": "from rq import Queue\n",
    "AWS SQS": "sqs = boto3.client('sqs')\n",
}


def test_detect_queues_all(az_module, tmp_path):
    az = az_module
    src = "\n".join(QUEUE_SNIPPETS.values())
    root = write_project(tmp_path, {"tasks.py": src})
    names = {q["name"] for q in az.detect_queues(root)}
    assert names == set(QUEUE_SNIPPETS.keys())


EXTSRC_SNIPPETS = {
    "Jira": "JIRA_API_TOKEN = os.environ['JIRA_API_TOKEN']\n",
    "Azure DevOps": "AZURE_DEVOPS_PAT = os.environ['AZURE_DEVOPS_PAT']\n",
    "Slack": "from slack_sdk import WebClient\n",
    "GitHub": "from github import Github\n",
    "Stripe": "import stripe\nstripe.api_key = 'sk_test'\n",
    "Salesforce": "from simple_salesforce import Salesforce\n",
    "Twilio": "from twilio.rest import Client\n",
}


def test_detect_external_sources_all_plus_users_and_cron(az_module, tmp_path):
    az = az_module
    src = "\n".join(EXTSRC_SNIPPETS.values()) + "\nCRON = '0 * * * *'\nAPScheduler()\n"
    root = write_project(tmp_path, {"integrations.py": src})
    names = {s["name"] for s in az.detect_external_sources(root)}
    assert names == set(EXTSRC_SNIPPETS.keys()) | {"Users / API Clients", "Cron / Scheduler"}


def test_detect_external_sources_always_includes_users(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"app.py": "print('nothing detected here')\n"})
    names = {s["name"] for s in az.detect_external_sources(root)}
    assert names == {"Users / API Clients"}
