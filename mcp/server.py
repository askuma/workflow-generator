#!/usr/bin/env python3
"""
workflow-generator MCP Server
Works with Claude Desktop, VS Code, Cursor, Zed, Windsurf, Continue, and any
MCP-compatible host.

Install:  pip install mcp
Run:      python3 ~/.claude/skills/workflow-generator/mcp/server.py
"""

import asyncio, json, os, subprocess, sys
from pathlib import Path

_HERE    = Path(__file__).parent
_SCRIPTS = _HERE.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

try:
    import analyze as _analyze
except ImportError:
    _analyze = None

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    import mcp.types as types
except ImportError:
    print("ERROR: mcp package not found. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)

server = Server("workflow-generator")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="generate_workflow",
            description=(
                "Scan a project directory and generate WORKFLOW.html — a visual system "
                "workflow showing all components, their communication paths, concurrency "
                "model, concurrent request capacity, and bottleneck analysis. Works with "
                "Python (FastAPI, Flask, Django), Node.js (Express, Nest.js), Go, and "
                "mixed projects. Detects: API frameworks, gateways, LLM providers, vector "
                "stores, databases, queues, rate limits, async primitives, and worker counts."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {
                        "type": "string",
                        "description": "Absolute path to the project root. Defaults to current working directory.",
                    },
                    "output_file": {
                        "type": "string",
                        "description": "Output path for WORKFLOW.html. Defaults to <project_dir>/WORKFLOW.html.",
                    },
                    "open_browser": {
                        "type": "boolean",
                        "description": "Open the generated file in the default browser.",
                        "default": True,
                    },
                },
                "required": [],
            },
        ),
        types.Tool(
            name="analyze_workflow",
            description=(
                "Scan a project and return the workflow analysis as structured JSON "
                "(no file written). Returns: framework, workers, capacity estimates, "
                "detected components (LLM, storage, queues, external sources), "
                "concurrency primitives (semaphores, rate limits), and bottleneck ranking."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_dir": {
                        "type": "string",
                        "description": "Absolute path to the project root.",
                    },
                },
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    project_dir = Path(arguments.get("project_dir") or os.getcwd()).resolve()

    if not project_dir.exists():
        return [types.TextContent(type="text", text=f"ERROR: Directory not found: {project_dir}")]

    if _analyze is None:
        return [types.TextContent(type="text",
            text="ERROR: analyze.py not found. Ensure ~/.claude/skills/workflow-generator/scripts/analyze.py exists.")]

    project_name = _analyze.detect_project_name(project_dir) or project_dir.name.replace("-", " ").replace("_", " ").title()
    analysis = _analyze.collect(project_dir)
    cap = analysis["capacity"]

    if name == "analyze_workflow":
        result = {
            "project": project_name,
            "framework": analysis["api_server"]["framework"],
            "capacity": {
                "total_workers": cap["total_workers"],
                "concurrent_io": cap["total_io"],
                "semaphore_limit": cap["sem_limit"],
                "practical_throughput": cap["practical"],
                "bottleneck": cap["bottleneck"],
                "rate_limit": cap.get("rate_limit_str"),
            },
            "gateway": analysis["gateway"]["type"] if analysis["gateway"] else None,
            "llm_providers": analysis["llm"]["providers"],
            "llm_models": analysis["llm"]["models"],
            "eval_framework": analysis["llm"].get("eval_framework"),
            "storage": [{"name": s["name"], "type": s["type"]} for s in analysis["storage"]],
            "queues": [q["name"] for q in analysis["queues"]],
            "external_sources": [s["name"] for s in analysis["external_sources"]],
            "concurrency": {
                "semaphores": analysis["concurrency"]["semaphores"],
                "has_async_lock": analysis["concurrency"]["has_lock"],
                "has_thread_pool": analysis["concurrency"]["has_executor"],
                "batch_size": analysis["concurrency"].get("batch_size"),
            },
            "detected_flows": [f["title"] for f in analysis["flows"]],
        }
        return [types.TextContent(type="text", text=json.dumps(result, indent=2))]

    if name == "generate_workflow":
        output_file = Path(
            arguments.get("output_file") or (project_dir / "WORKFLOW.html")
        ).resolve()

        html = _analyze.render_html(analysis, project_name)
        output_file.write_text(html)

        lines = [
            f"Workflow generated: {output_file}",
            f"Framework: {analysis['api_server']['framework']}",
            f"Workers: {cap['total_workers']} · Concurrent I/O: ~{cap['total_io']}",
            f"Practical throughput (estimated): {cap['practical']}",
            f"Bottleneck: {cap['bottleneck']}",
        ]
        if analysis["gateway"]:
            rl = analysis["gateway"].get("rate_limits", [])
            lines.append(f"Gateway: {analysis['gateway']['type']} · {len(rl)} rate limit zone(s)")
        if analysis["llm"]["providers"]:
            lines.append(f"LLM: {', '.join(analysis['llm']['providers'])}")
        if analysis["storage"]:
            lines.append(f"Storage: {', '.join(s['name'] for s in analysis['storage'])}")
        lines.append(f"Detected flows: {', '.join(f['title'] for f in analysis['flows'])}")

        if arguments.get("open_browser", True):
            for cmd in ["xdg-open", "open", "start"]:
                try:
                    subprocess.Popen([cmd, str(output_file)],
                                     stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
                    break
                except FileNotFoundError:
                    continue

        return [types.TextContent(type="text", text="\n".join(lines))]

    return [types.TextContent(type="text", text=f"Unknown tool: {name}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
