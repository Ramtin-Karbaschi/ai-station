#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
import sys
from contextlib import suppress


def detect_bridge_host() -> str | None:
    override = os.getenv("AI_STATION_GATEWAY_BRIDGE_HOST", "").strip()
    if override:
        return override

    try:
        result = subprocess.run(
            ["ip", "-4", "addr", "show", "docker0"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None

    if result.returncode != 0:
        return None

    match = re.search(r"\binet\s+(\d+\.\d+\.\d+\.\d+)/", result.stdout)
    if not match:
        return None
    return match.group(1)


async def pipe_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except Exception:
        pass
    finally:
        with suppress(Exception):
            writer.write_eof()


async def proxy_connection(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    target_host: str,
    target_port: int,
) -> None:
    target_writer: asyncio.StreamWriter | None = None
    try:
        target_reader, target_writer = await asyncio.open_connection(target_host, target_port)
    except Exception:
        client_writer.close()
        with suppress(Exception):
            await client_writer.wait_closed()
        return

    upstream = asyncio.create_task(pipe_stream(client_reader, target_writer))
    downstream = asyncio.create_task(pipe_stream(target_reader, client_writer))
    done, pending = await asyncio.wait(
        {upstream, downstream},
        return_when=asyncio.FIRST_COMPLETED,
    )

    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    for task in done:
        with suppress(Exception):
            await task

    target_writer.close()
    client_writer.close()
    with suppress(Exception):
        await target_writer.wait_closed()
    with suppress(Exception):
        await client_writer.wait_closed()


async def wait_for_local_listener(host: str, port: int, attempts: int = 50) -> None:
    for _ in range(attempts):
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()
            return
        except Exception:
            await asyncio.sleep(0.2)
    raise RuntimeError(f"Timed out waiting for local gateway on {host}:{port}")


async def run() -> int:
    host = os.getenv("AI_STATION_GATEWAY_HOST", "127.0.0.1")
    port = int(os.getenv("AI_STATION_GATEWAY_PORT", "8888"))
    bridge_host = detect_bridge_host()
    uvicorn_bin = os.getenv("AI_STATION_GATEWAY_UVICORN", "uvicorn")
    uvicorn_app = os.getenv("AI_STATION_GATEWAY_APP", "apps.gateway.app.main:app")

    stop_event = asyncio.Event()

    def handle_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    env = os.environ.copy()
    proc = await asyncio.create_subprocess_exec(
        uvicorn_bin,
        uvicorn_app,
        "--host",
        host,
        "--port",
        str(port),
        env=env,
    )

    try:
        await wait_for_local_listener(host, port)
    except Exception:
        proc.terminate()
        await proc.wait()
        raise

    server = None
    if bridge_host and bridge_host != host:
        server = await asyncio.start_server(
            lambda r, w: proxy_connection(r, w, host, port),
            bridge_host,
            port,
        )
        print(
            f"AI Station bridge proxy listening on http://{bridge_host}:{port} -> http://{host}:{port}",
            flush=True,
        )
    else:
        print("AI Station bridge proxy disabled", flush=True)

    print(f"AI Station gateway runner supervising http://{host}:{port}", flush=True)

    wait_task = asyncio.create_task(proc.wait())
    stop_task = asyncio.create_task(stop_event.wait())
    done, pending = await asyncio.wait(
        {wait_task, stop_task},
        return_when=asyncio.FIRST_COMPLETED,
    )

    exit_code = 0
    if wait_task in done:
        exit_code = await wait_task
        stop_event.set()
    else:
        proc.terminate()
        exit_code = await wait_task

    for task in pending:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    if server is not None:
        server.close()
        await server.wait_closed()

    if proc.returncode is None:
        proc.terminate()
        await proc.wait()

    return exit_code


def main() -> int:
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
