"""Formalizes the ad hoc 102-case harness built during the codebase-graph
session: for every _LOWER_HINTS key, a realistic snippet that the real regex
matches must also survive _hinted_search — i.e. the literal-substring
prefilter used to skip expensive regex .search() calls on large repos must
never be a false negative for real-world phrasing. This is exactly the class
of bug caught this session (the 'postgres' hint originally missed 'psycopg').
"""
import pytest
from conftest import write_project

# One realistic matching snippet per _LOWER_HINTS key.
MATCHING_SNIPPETS = {
    "openai_chat": "from openai import OpenAI",
    "anthropic_chat": "from anthropic import Anthropic",
    "cohere_chat": "cohere.Client('key')",
    "bedrock_chat": "boto3.client('bedrock-runtime')",
    "gemini_chat": "import google.generativeai as genai",
    "mistral_chat": "MistralClient()",
    "groq_chat": "from groq import Groq",
    "ollama_chat": "import ollama",
    "litellm_call": "import litellm",
    "redis_cache": "redis.Redis(host='localhost')",
    "redis_db": "image: redis:7-alpine",
    "qdrant": "from qdrant_client import QdrantClient",
    "pinecone": "import pinecone",
    "weaviate": "import weaviate",
    "chromadb": "import chromadb",
    "pgvector": "CREATE EXTENSION pgvector;",
    "faiss": "import faiss",
    "milvus": "from pymilvus import connections",
    # The exact regression: 'psycopg' alone, no literal 'postgres' substring.
    "postgres": "import psycopg2",
    "mysql": "import pymysql",
    "mongo": "import motor.motor_asyncio",
    "sqlite": "sqlite:///db.sqlite3",
    "celery": "from celery import Celery",
    "bull": "require('bullmq')",
    "kafka": "from kafka import KafkaProducer",
    "rabbitmq": "import pika",
    "redis_queue": "from rq import Queue",
    "sqs": "boto3.client('sqs')",
    "jira": "JIRA_API_TOKEN = 'x'",
    "ado": "AZURE_DEVOPS_PAT = 'x'",
    "slack": "from slack_sdk import WebClient",
    "github": "from github import Github",
    "stripe": "import stripe",
    "salesforce": "from simple_salesforce import Salesforce",
    "twilio": "from twilio.rest import Client",
    "s3": "boto3.client('s3')",
}


def test_every_lower_hints_key_has_a_matching_snippet(az_module):
    az = az_module
    missing = set(az._LOWER_HINTS) - set(MATCHING_SNIPPETS)
    assert not missing, f"no test snippet for _LOWER_HINTS keys: {missing}"


@pytest.mark.parametrize("re_key", sorted(MATCHING_SNIPPETS))
def test_hinted_search_does_not_suppress_real_match(az_module, re_key):
    az = az_module
    snippet = MATCHING_SNIPPETS[re_key]
    assert az._RE[re_key].search(snippet), (
        f"fixture snippet for {re_key!r} doesn't even match the real regex — fix the fixture"
    )
    result = az._hinted_search(re_key, snippet, snippet.lower())
    assert result is not None, (
        f"_LOWER_HINTS[{re_key!r}] incorrectly suppressed a real regex match for {snippet!r}"
    )
