from conftest import write_project


def test_route_to_regex_handles_all_placeholder_styles(az_module):
    az = az_module
    for tmpl in ('/items/<id>', '/items/{id}', '/items/:id'):
        rx = az._route_to_regex(tmpl)
        assert rx.match('/items/42')
        assert not rx.match('/items/42/extra')


def test_parse_access_log_matches_routes_and_buckets_other(az_module, tmp_path):
    az = az_module
    log = tmp_path / "access.log"
    log.write_text(
        '127.0.0.1 - - [10/Oct/2023:13:55:00 +0000] "GET /items/1 HTTP/1.1" 200 512\n'
        '127.0.0.1 - - [10/Oct/2023:13:55:30 +0000] "GET /items/2 HTTP/1.1" 200 512\n'
        '127.0.0.1 - - [10/Oct/2023:13:56:00 +0000] "POST /webhook/github HTTP/1.1" 204 0\n'
        '127.0.0.1 - - [10/Oct/2023:13:56:30 +0000] "GET /unmatched HTTP/1.1" 404 128\n'
    )
    routes = ['GET /items/{id}', 'POST /webhook/github']
    result = az.parse_access_log(str(log), routes)
    assert result is not None
    assert result['total'] == 4
    assert result['by_route']['GET /items/{id}'] == 2
    assert result['by_route']['POST /webhook/github'] == 1
    assert result['other'] == 1
    assert result['rpm'] is not None
    assert result['rpm'] > 0


def test_parse_access_log_missing_file_returns_none(az_module, tmp_path):
    az = az_module
    missing = tmp_path / "nope.log"
    assert az.parse_access_log(str(missing), ['GET /items/{id}']) is None


def test_parse_access_log_no_matching_lines_returns_none(az_module, tmp_path):
    az = az_module
    log = tmp_path / "empty.log"
    log.write_text("this is not a log line at all\njust some text\n")
    assert az.parse_access_log(str(log), ['GET /items/{id}']) is None


def test_gen_k6_script_picks_up_to_five_get_routes_and_fills_params(az_module):
    az = az_module
    routes = [f"GET /items/{{id}}{i}" for i in range(7)]
    script = az._gen_k6_script(routes)
    assert script.count("http.get(") == 5
    assert "{id}" not in script
    assert "BASE_URL" in script


def test_gen_k6_script_falls_back_to_non_get_when_no_get_routes(az_module):
    az = az_module
    routes = ['POST /webhook/github', 'PUT /items/{id}']
    script = az._gen_k6_script(routes)
    assert "http.post(" in script or "http.put(" in script
