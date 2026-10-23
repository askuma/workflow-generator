from conftest import write_project

ANALYSIS = {
    'llm': {'providers': ['OpenAI']}, 'storage': [], 'queues': [], 'external_sources': [],
    'framework': None, 'access_log': None,
}


def test_is_test_path(az_module):
    az = az_module
    for rel in ('tests/helpers.py', 'pkg/test_x.py', 'pkg/x_test.go', 'conftest.py',
                'web/a.spec.ts', 'web/a.test.jsx', 'src/test/java/FooTest.java', 'lib/a_spec.rb'):
        assert az._is_test_path(rel), rel
    for rel in ('app/main.py', 'pkg/testing_utils.py', 'src/latest.ts', 'Manifest.java'):
        assert not az._is_test_path(rel), rel


def test_tests_split_into_their_own_graph(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "app.py": "import util\n",
        "util.py": "",
        "tests/test_app.py": "import app\nfrom openai import OpenAI\nOpenAI().chat.completions.create()\n",
    })
    main, tests = az.build_code_graphs(root, ANALYSIS, detail='files')
    main_ids = {n['id'] for n in main['nodes']}
    test_ids = {n['id'] for n in tests['nodes']}

    assert main_ids == {'app.py', 'util.py'}
    assert main['meta']['files'] == 2
    # A service only a test reaches must not leak into the main graph.
    assert 'svc:OpenAI' not in main_ids

    assert test_ids == {'tests/test_app.py', 'app.py', 'svc:OpenAI'}
    assert tests['meta']['files'] == 1
    assert all(e['s'] == 'tests/test_app.py' for e in tests['links'])


def test_render_codebase_sections_have_flow_and_graph_views(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "app.py": "import util\n",
        "util.py": "",
        "tests/test_app.py": "import app\n",
    })
    html = az.render_html(az.collect(root), "p")
    assert 'id="section-flow"' not in html  # merged into the Codebase section
    for P in ('graph-', 'test-graph-'):
        for suffix in ('tab-flow', 'tab-force', 'flow-canvas', 'canvas', 'data', 'animate'):
            assert f'id="{P}{suffix}"' in html, P + suffix
    assert html.index('id="section-graph"') < html.index('id="section-test-graph"')
    # Small graphs open on the Flow view.
    assert 'id="section-graph" data-default-view="flow"' in html
