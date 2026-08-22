#!/usr/bin/env python3
"""Build and serve the loopback Graphify station map (no GPU)."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from operator_output import load_prefs  # noqa: E402

DEFAULT_PORT = 4174
STATE_DIR = Path(
    os.environ.get(
        "AI_STATION_GRAPHIFY_VIEW_STATE_DIR",
        "/srv/ai-station/runtime/graphify",
    )
)
STATE_FILE = STATE_DIR / "view-server.json"
LOG_FILE = STATE_DIR / "view-server.log"


def graphify_bin() -> Path:
    override = os.environ.get("AI_STATION_GRAPHIFY_BIN")
    if override:
        return Path(override)
    return Path("/opt/ai-station/.venvs/graphify/bin/graphify")


def process_matches(pid: int, directory: Path) -> bool:
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
    except OSError:
        return False
    return "http.server" in command and str(directory) in command


def load_state() -> dict[str, object] | None:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def port_available(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def healthy(port: int, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=timeout) as response:
            return response.status == 200
    except (OSError, urllib.error.HTTPError):
        return False


def run_graphify(args: list[str]) -> None:
    binary = graphify_bin()
    if not binary.is_file():
        raise FileNotFoundError(f"graphify CLI missing: {binary}")
    completed = subprocess.run(
        [str(binary), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(detail or f"graphify exited {completed.returncode}")


def station_map_html(
    node_count: int,
    link_count: int,
    media_dir: str,
    graphify_dir: str,
    export_dir: str,
    has_tree: bool,
) -> str:
    tree_card = ""
    if has_tree:
        tree_card = """
      <a class="card" href="GRAPH_TREE.html">
        <strong>Module tree</strong>
        Collapsible tree. Needs outbound HTTPS for D3.
      </a>"""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Station map</title>
  <style>
    :root {{
      --bg: #0f1419;
      --panel: #1a222c;
      --text: #e7ecf1;
      --muted: #9aa7b5;
      --line: #2b3642;
      --accent: #6ea8fe;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 16px/1.45 "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    main {{
      max-width: 920px;
      margin: 0 auto;
      padding: 32px 20px 64px;
    }}
    h1 {{ font-size: 1.6rem; margin: 0 0 8px; }}
    p {{ color: var(--muted); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 12px;
      margin: 24px 0;
    }}
    a.card {{
      display: block;
      padding: 16px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--text);
      text-decoration: none;
    }}
    a.card:hover, a.card:focus {{
      border-color: var(--accent);
    }}
    a.card strong {{ display: block; margin-bottom: 4px; color: var(--accent); }}
    code {{
      font: 13px/1.4 ui-monospace, monospace;
      color: var(--text);
      word-break: break-all;
    }}
    .note {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
      background: var(--panel);
    }}
  </style>
</head>
<body>
  <main>
    <h1>AI Station map</h1>
    <p>Read-only operator map. Start, stop, and model load stay on the
      <code>ai</code> CLI and Windows Manager. Graph: {node_count} nodes,
      {link_count} links.</p>
    <div class="grid">
      <a class="card" href="graph.html">
        <strong>Code graph</strong>
        Force-directed Graphify view (self-contained).
      </a>{tree_card}
      <a class="card" href="GRAPH_REPORT.md">
        <strong>Graph report</strong>
        Communities and hubs as Markdown.
      </a>
      <a class="card" href="http://127.0.0.1:3000">
        <strong>Open WebUI</strong>
        Human chat and Knowledge notebooks.
      </a>
      <a class="card" href="http://127.0.0.1:4000/ui">
        <strong>LiteLLM admin</strong>
        Application API keys.
      </a>
      <a class="card" href="http://127.0.0.1:8889">
        <strong>SearXNG</strong>
        Local metasearch.
      </a>
      <a class="card" href="http://127.0.0.1:8188">
        <strong>ComfyUI</strong>
        Experimental media UI (off by default).
      </a>
    </div>
    <div class="note">
      <p><strong>Output directories</strong></p>
      <p>Media: <code>{media_dir}</code></p>
      <p>Graphify: <code>{graphify_dir}</code></p>
      <p>Export: <code>{export_dir}</code></p>
      <p>Change with <code>ai output set media|graphify|export PATH</code>.</p>
    </div>
  </main>
</body>
</html>
"""


def generate(graph_json: Path) -> Path:
    if not graph_json.is_file():
        raise FileNotFoundError(f"graph.json not found: {graph_json}")
    out_dir = graph_json.parent
    run_graphify(["export", "html", "--graph", str(graph_json)])
    tree_html = out_dir / "GRAPH_TREE.html"
    tree_args = [
        "tree",
        "--graph",
        str(graph_json),
        "--output",
        str(tree_html),
        "--label",
        "ai-station",
    ]
    try:
        run_graphify(tree_args)
    except RuntimeError as exc:
        print(f"WARNING: module tree skipped: {exc}", file=sys.stderr)
    payload = json.loads(graph_json.read_text(encoding="utf-8"))
    nodes = payload.get("nodes") if isinstance(payload, dict) else []
    links = payload.get("links") if isinstance(payload, dict) else []
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(links, list):
        links = []
    prefs = load_prefs()
    html = station_map_html(
        node_count=len(nodes),
        link_count=len(links),
        media_dir=prefs["outputs"]["media"],
        graphify_dir=prefs["outputs"]["graphify"],
        export_dir=prefs["outputs"]["export"],
        has_tree=tree_html.is_file(),
    )
    index = out_dir / "index.html"
    index.write_text(html, encoding="utf-8")
    return out_dir


def start_server(directory: Path, port: int) -> int:
    state = load_state()
    if state:
        pid = int(state.get("pid", 0))
        old_directory = Path(str(state.get("directory", "")))
        old_port = int(state.get("port", 0))
        if process_matches(pid, old_directory):
            if old_directory == directory and old_port == port and healthy(port):
                print(f"OK: map already at http://127.0.0.1:{port}/")
                return 0
            print("ERROR: another Graphify map server is running; stop it first", file=sys.stderr)
            return 1
        STATE_FILE.unlink(missing_ok=True)
    if not 1024 <= port <= 65535:
        print("ERROR: port must be between 1024 and 65535", file=sys.stderr)
        return 2
    if not port_available(port):
        print(f"ERROR: loopback port {port} is already in use", file=sys.stderr)
        return 1
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    with LOG_FILE.open("ab") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "http.server",
                str(port),
                "--bind",
                "127.0.0.1",
                "--directory",
                str(directory),
            ],
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    STATE_FILE.write_text(
        json.dumps(
            {"pid": process.pid, "port": port, "directory": str(directory)},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    STATE_FILE.chmod(0o600)
    for _ in range(30):
        if process.poll() is not None:
            break
        if healthy(port):
            print(f"OK: Graphify map at http://127.0.0.1:{port}/")
            print(f"OK: serving {directory}")
            return 0
        time.sleep(0.1)
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
    STATE_FILE.unlink(missing_ok=True)
    print(f"ERROR: map server failed health check; inspect {LOG_FILE}", file=sys.stderr)
    return 1


def status() -> int:
    state = load_state()
    if not state:
        print("STOPPED: Graphify map is not running")
        return 1
    pid = int(state.get("pid", 0))
    port = int(state.get("port", 0))
    directory = Path(str(state.get("directory", "")))
    if process_matches(pid, directory) and healthy(port):
        print(f"OK: Graphify map at http://127.0.0.1:{port}/")
        print(f"OK: serving {directory}")
        return 0
    print("FAILED: map state exists but the server is unavailable", file=sys.stderr)
    return 1


def stop() -> int:
    state = load_state()
    if not state:
        print("OK: Graphify map was not running")
        return 0
    pid = int(state.get("pid", 0))
    directory = Path(str(state.get("directory", "")))
    if process_matches(pid, directory):
        os.killpg(pid, signal.SIGTERM)
        for _ in range(30):
            if not process_matches(pid, directory):
                break
            time.sleep(0.1)
    STATE_FILE.unlink(missing_ok=True)
    print("OK: Graphify map stopped")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default="")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-serve", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)
    if args.stop:
        return stop()
    if args.status:
        return status()
    graph = Path(args.graph) if args.graph else Path("/opt/ai-station/graphify-out/graph.json")
    try:
        directory = generate(graph.resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"OK: wrote {directory / 'index.html'}")
    print(f"OK: wrote {directory / 'graph.html'}")
    if (directory / "GRAPH_TREE.html").is_file():
        print(f"OK: wrote {directory / 'GRAPH_TREE.html'}")
    if args.no_serve:
        return 0
    return start_server(directory, args.port)


if __name__ == "__main__":
    raise SystemExit(main())
