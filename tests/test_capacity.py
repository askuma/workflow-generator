def test_semaphore_tightest_wins_concurrency_ranking(az_module):
    az = az_module
    workers = {"uvicorn_workers": 4, "gunicorn_workers": None, "replicas": 1,
               "pm2_instances": None, "is_async": True}
    concur = {"semaphores": [2]}
    cap = az.compute_concurrency(workers, gateway=None, concur=concur, llm={}, api=None)
    # total_io = 4 workers * 100 = 400; sem_ceiling = 2 * 4 = 8 -> semaphore is tighter
    assert cap["bottleneck"] == "Semaphore limit"
    assert cap["practical"] == "~8 concurrent I/O"


def test_gateway_rate_limit_beats_looser_app_rate_limit(az_module):
    az = az_module
    workers = {"uvicorn_workers": 1, "gunicorn_workers": None, "replicas": 1,
               "pm2_instances": None, "is_async": True}
    gateway = {"type": "nginx", "rate_limits": [{"zone": "api", "rate": "30r/m", "burst": 10}]}
    api = {"app_rate_limits": [{"rate": "100", "unit": "minute"}]}
    cap = az.compute_concurrency(workers, gateway=gateway, concur={}, llm={}, api=api)
    assert cap["bottleneck"] == "nginx rate limit"
    assert cap["practical"] == "~30/min"


def test_app_rate_limit_tighter_than_gateway(az_module):
    az = az_module
    workers = {"uvicorn_workers": 1, "gunicorn_workers": None, "replicas": 1,
               "pm2_instances": None, "is_async": True}
    gateway = {"type": "nginx", "rate_limits": [{"zone": "api", "rate": "500r/m", "burst": 10}]}
    api = {"app_rate_limits": [{"rate": "20", "unit": "minute"}]}
    cap = az.compute_concurrency(workers, gateway=gateway, concur={}, llm={}, api=api)
    assert cap["bottleneck"] == "Application rate limit"
    assert cap["practical"] == "~20/min"


def test_llm_timeout_derived_ceiling_uses_actual_worker_count(az_module):
    az = az_module
    workers = {"uvicorn_workers": 2, "gunicorn_workers": None, "replicas": 1,
               "pm2_instances": None, "is_async": True}
    llm = {"providers": ["OpenAI"], "timeout": 30}
    cap = az.compute_concurrency(workers, gateway=None, concur={}, llm=llm, api=None)
    # concurrency_ceiling = 2 workers * 100 = 200; llm_rpm = 200 * (60/30) = 400
    assert cap["bottleneck"] == "OpenAI latency"
    assert cap["practical"] == "~400/min"


def test_ranking_and_bottleneck_never_disagree(az_module):
    az = az_module
    workers = {"uvicorn_workers": 4, "gunicorn_workers": None, "replicas": 2,
               "pm2_instances": None, "is_async": True}
    gateway = {"type": "nginx", "rate_limits": [{"zone": "api", "rate": "50r/m", "burst": 5}]}
    llm = {"providers": ["Anthropic"], "timeout": 10}
    api = {"app_rate_limits": []}
    cap = az.compute_concurrency(workers, gateway=gateway, concur={"semaphores": [3]}, llm=llm, api=api)
    assert cap["ranking"][0][0] == cap["bottleneck"]
    assert cap["ranking"] == sorted(cap["ranking"], key=lambda c: c[1])


def test_no_evidence_falls_back_to_concurrency_ceiling(az_module):
    az = az_module
    workers = {"uvicorn_workers": None, "gunicorn_workers": None, "replicas": 1,
               "pm2_instances": None, "is_async": False}
    cap = az.compute_concurrency(workers, gateway=None, concur={}, llm={}, api=None)
    assert cap["ranking_kind"] == "concurrency"
    assert cap["practical"] == "~1 concurrent I/O"
