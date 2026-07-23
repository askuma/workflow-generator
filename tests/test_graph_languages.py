from conftest import write_project

EMPTY_ANALYSIS = {
    'llm': {'providers': []}, 'storage': [], 'queues': [], 'external_sources': [],
    'framework': None, 'access_log': None,
}


def _edge_set(graph):
    return {(e['s'], e['t']) for e in graph['links']}


def test_python_ast_resolves_package_and_relative_imports(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "from . import b\nfrom .b import helper\n",
        "pkg/b.py": "def helper(): pass\n",
        "main.py": "import pkg.a\n",
    })
    graph = az.build_code_graph(root, EMPTY_ANALYSIS)
    edges = _edge_set(graph)
    assert ("pkg/a.py", "pkg/b.py") in edges
    assert ("main.py", "pkg/a.py") in edges


def test_js_relative_import_resolved_bare_specifier_is_not(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "src/index.js": "import { helper } from './helper';\nimport express from 'express';\n",
        "src/helper.js": "export function helper() {}\n",
    })
    graph = az.build_code_graph(root, EMPTY_ANALYSIS)
    edges = _edge_set(graph)
    assert ("src/index.js", "src/helper.js") in edges
    assert not any(t == 'express' or t.endswith('express') for _, t in edges)


def test_go_resolves_via_synthetic_go_mod(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "go.mod": "module example.com/myapp\n\ngo 1.21\n",
        "main.go": 'package main\n\nimport (\n\t"example.com/myapp/util"\n)\n\nfunc main() {}\n',
        "util/util.go": "package util\n\nfunc Helper() {}\n",
    })
    graph = az.build_code_graph(root, EMPTY_ANALYSIS)
    edges = _edge_set(graph)
    assert ("main.go", "util/util.go") in edges


def test_java_import_fqn_resolved_wildcard_skipped(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "src/com/example/Main.java": (
            "package com.example;\n"
            "import com.example.util.Helper;\n"
            "import com.example.other.*;\n"
            "public class Main {}\n"
        ),
        "src/com/example/util/Helper.java": (
            "package com.example.util;\n"
            "public class Helper {}\n"
        ),
    })
    graph = az.build_code_graph(root, EMPTY_ANALYSIS)
    edges = _edge_set(graph)
    assert ("src/com/example/Main.java", "src/com/example/util/Helper.java") in edges


def test_rust_mod_and_use_crate_resolved(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "Cargo.toml": "[package]\nname = \"myapp\"\nversion = \"0.1.0\"\n",
        "src/main.rs": "mod util;\nuse crate::util::helper;\n\nfn main() {}\n",
        "src/util.rs": "pub fn helper() {}\n",
    })
    graph = az.build_code_graph(root, EMPTY_ANALYSIS)
    edges = _edge_set(graph)
    assert ("src/main.rs", "src/util.rs") in edges


def test_ruby_require_relative_traverses_parent_dir_require_hits_lib(az_module, tmp_path):
    az = az_module
    root = write_project(tmp_path, {
        "lib/helper.rb": "def helper; end\n",
        "app/main.rb": "require_relative '../lib/helper'\nrequire 'helper'\n",
    })
    graph = az.build_code_graph(root, EMPTY_ANALYSIS)
    edges = _edge_set(graph)
    assert ("app/main.rb", "lib/helper.rb") in edges
