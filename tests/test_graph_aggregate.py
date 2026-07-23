from conftest import write_project

EMPTY_ANALYSIS = {
    'llm': {'providers': []}, 'storage': [], 'queues': [], 'external_sources': [],
    'framework': None, 'access_log': None,
}


def test_aggregate_sums_weights_instead_of_overwriting(az_module):
    az = az_module
    nodes = {
        "pkg_a/x.py": {"id": "pkg_a/x.py", "label": "x.py", "pkg": "pkg_a", "loc": 10, "kind": "file"},
        "pkg_a/y.py": {"id": "pkg_a/y.py", "label": "y.py", "pkg": "pkg_a", "loc": 5, "kind": "file"},
        "pkg_b/z.py": {"id": "pkg_b/z.py", "label": "z.py", "pkg": "pkg_b", "loc": 8, "kind": "file"},
    }
    # Two distinct file-level edges between the same directory pair, one with
    # a real access-log weight, one without — both must survive as a summed
    # weight on the single merged dir-to-dir edge, not overwrite each other.
    edges = [
        {"s": "pkg_a/x.py", "t": "pkg_b/z.py", "kind": "import"},
        {"s": "pkg_a/y.py", "t": "pkg_b/z.py", "kind": "import", "w": 7},
    ]
    agg_nodes, agg_edges = az._aggregate_graph_dirs(nodes, edges)
    assert "dir:pkg_a" in agg_nodes
    assert "dir:pkg_b" in agg_nodes
    assert agg_nodes["dir:pkg_a"]["file_count"] == 2
    assert agg_nodes["dir:pkg_a"]["loc"] == 15
    merged = [e for e in agg_edges if e["s"] == "dir:pkg_a" and e["t"] == "dir:pkg_b"]
    assert len(merged) == 1
    assert merged[0]["w"] == 1 + 7


def test_aggregate_drops_self_loops_after_collapsing_to_same_dir(az_module):
    az = az_module
    nodes = {
        "pkg/x.py": {"id": "pkg/x.py", "label": "x.py", "pkg": "pkg", "loc": 1, "kind": "file"},
        "pkg/y.py": {"id": "pkg/y.py", "label": "y.py", "pkg": "pkg", "loc": 1, "kind": "file"},
    }
    edges = [{"s": "pkg/x.py", "t": "pkg/y.py", "kind": "import"}]
    agg_nodes, agg_edges = az._aggregate_graph_dirs(nodes, edges)
    assert agg_edges == []


def test_aggregate_leaves_service_and_entry_nodes_untouched(az_module):
    az = az_module
    nodes = {
        "pkg/x.py": {"id": "pkg/x.py", "label": "x.py", "pkg": "pkg", "loc": 1, "kind": "file"},
        "svc:Redis": {"id": "svc:Redis", "label": "Redis", "pkg": "(service)", "loc": 0, "kind": "service"},
    }
    edges = [{"s": "pkg/x.py", "t": "svc:Redis", "kind": "service"}]
    agg_nodes, agg_edges = az._aggregate_graph_dirs(nodes, edges)
    assert "svc:Redis" in agg_nodes
    assert agg_nodes["svc:Redis"]["kind"] == "service"
    assert agg_edges == [{"s": "dir:pkg", "t": "svc:Redis", "kind": "service", "w": 1}]


def test_build_code_graph_auto_aggregates_past_file_cap(az_module, tmp_path):
    az = az_module
    files = {f"pkg/m{i}.py": "" for i in range(az._GRAPH_FILE_CAP + 10)}
    root = write_project(tmp_path, files)
    graph = az.build_code_graph(root, EMPTY_ANALYSIS, detail='auto')
    assert graph['meta']['aggregated'] is True
    assert graph['meta']['files'] == az._GRAPH_FILE_CAP + 10
    assert graph['meta']['shown_nodes'] < graph['meta']['files']


def test_build_code_graph_files_detail_never_aggregates(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {"a.py": "import b\n", "b.py": ""})
    graph = az.build_code_graph(root, EMPTY_ANALYSIS, detail='files')
    assert graph['meta']['aggregated'] is False
    assert graph['meta']['files'] == graph['meta']['shown_nodes']
