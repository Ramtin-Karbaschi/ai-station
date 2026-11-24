from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.gateway.app import main as gateway_main  # noqa: E402
from apps.gateway.app.lifecycle_lock import LifecycleLock  # noqa: E402


@unittest.skipUnless(os.name == "posix", "Linux flock lifecycle regressions")
class LifecycleLockRegressionTests(unittest.IsolatedAsyncioTestCase):
    def lock_env(self, directory: Path) -> dict[str, str]:
        return {
            "AI_STATE_DIR": str(directory),
            "AI_ACTIVE_PROFILE_FILE": str(directory / "active-heavy-profile"),
            "AI_LIFECYCLE_LOCK_FILE": str(directory / "lifecycle.lock"),
        }

    async def wait_for_holder(self, directory: Path) -> None:
        marker = directory / "lifecycle.lock"
        for _ in range(20):
            if marker.exists() and "cli-holder" in marker.read_text():
                return
            await asyncio.sleep(0.05)
        self.fail("CLI lock holder did not publish its diagnostic")

    async def test_cli_subprocess_contention_times_out_then_acquires(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            holder = subprocess.Popen(
                ["bash", "-c", "source \"$1\"; ai_lifecycle_lock cli-holder; sleep 1",
                 "bash", str(ROOT / "scripts/lib/ai-common.sh")],
                env={**os.environ, **self.lock_env(directory)},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            try:
                await self.wait_for_holder(directory)
                with patch.dict(os.environ, self.lock_env(directory), clear=False):
                    with self.assertRaises(TimeoutError):
                        async with LifecycleLock("gateway-contender", timeout=0.05):
                            pass
                holder.wait(timeout=3)
                holder.stdout.close()
                holder.stderr.close()
                with patch.dict(os.environ, self.lock_env(directory), clear=False):
                    async with LifecycleLock("gateway-after-cli"):
                        self.assertIn("gateway-after-cli", (directory / "lifecycle.lock").read_text())
            finally:
                if holder.poll() is None:
                    holder.kill()
                    holder.wait(timeout=3)

    async def test_crashed_holder_releases_kernel_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            script = textwrap.dedent("""
                import fcntl, os, sys
                stream = open(sys.argv[1], "a+")
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                os._exit(0)
            """)
            subprocess.run([sys.executable, "-c", script, str(directory / "lifecycle.lock")], check=True)
            with patch.dict(os.environ, self.lock_env(directory), clear=False):
                async with LifecycleLock("after-crash", timeout=0.2):
                    self.assertTrue((directory / "lifecycle.lock").exists())

    async def test_admission_runs_inside_shared_lock_before_compose(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            holder_script = textwrap.dedent("""
                import fcntl, sys, time
                stream = open(sys.argv[1], "a+")
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                stream.write("python-holder\\n"); stream.flush()
                time.sleep(2)
            """)
            holder = subprocess.Popen(
                [sys.executable, "-c", holder_script, str(directory / "lifecycle.lock")],
                env={**os.environ, **self.lock_env(directory)},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            compose = AsyncMock()
            evaluate = Mock(return_value={"decision": "START"})
            try:
                for _ in range(20):
                    marker = directory / "lifecycle.lock"
                    if marker.exists() and "python-holder" in marker.read_text():
                        break
                    await asyncio.sleep(0.05)
                else:
                    self.fail("Python lock holder did not publish its diagnostic")
                model = {"id": "test-model", "service": "llm-test", "heavy": False}
                with patch.dict(os.environ, self.lock_env(directory), clear=False), \
                     patch.object(gateway_main, "LifecycleLock", side_effect=lambda action: LifecycleLock(action, timeout=0.05)), \
                     patch.object(gateway_main, "evaluate_admission", evaluate), \
                     patch.object(gateway_main, "compose", compose):
                    with self.assertRaisesRegex(gateway_main.HTTPException, "lifecycle_lock"):
                        await gateway_main.start_runtime(model)
                compose.assert_not_awaited()
                evaluate.assert_not_called()
            finally:
                holder.wait(timeout=3)
                holder.stdout.close()
                holder.stderr.close()

    async def test_cancelled_compose_does_not_release_lock_while_operation_drains(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            started = threading.Event()
            drain = threading.Event()

            def blocking_run_compose(*_args, **_kwargs):
                started.set()
                drain.wait(5)
                return subprocess.CompletedProcess([], 0, "", "")

            model = {"id": "test-model", "service": "llm-test", "heavy": False}
            with patch.dict(os.environ, self.lock_env(directory), clear=False), \
                 patch.object(gateway_main, "evaluate_admission", return_value={"decision": "START"}), \
                 patch.object(gateway_main, "run_compose", side_effect=blocking_run_compose):
                task = asyncio.create_task(gateway_main.start_runtime(model))
                for _ in range(20):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.05)
                else:
                    self.fail("blocking Compose stub did not start")
                task.cancel()
                await asyncio.sleep(0)
                try:
                    self.assertFalse(task.done(), "cancellation must wait for Compose drain")
                    with self.assertRaises(TimeoutError):
                        async with LifecycleLock("contender", timeout=0.05):
                            pass
                finally:
                    drain.set()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                async with LifecycleLock("after-drain", timeout=0.2):
                    pass

    def test_restart_does_not_start_after_busy_stop(self) -> None:
        """A failed/busy stop must not allow restart to create a no-gap start."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            scripts.mkdir()
            events = root / "events"
            (scripts / "lib").mkdir()
            (scripts / "lib" / "ai-common.sh").write_text(
                (ROOT / "scripts/lib/ai-common.sh").read_text()
            )
            for source_lib in (ROOT / "scripts/lib").glob("*.sh"):
                (scripts / "lib" / source_lib.name).write_text(source_lib.read_text())
            source_file = scripts / "ai-source"
            source_file.write_text((ROOT / "scripts/ai").read_text().rsplit('main "$@"', 1)[0])
            command = f'''
                source "$1"
                ROOT="$2"
                export EVENTS="$3"
                cmd_stop() {{ [[ -z "${{AI_LIFECYCLE_LOCK_FD:-}}" ]] && ai_lifecycle_lock stub-stop; echo stop >> "$EVENTS"; return "${{STOP_STATUS:-7}}"; }}
                cmd_start() {{ [[ -z "${{AI_LIFECYCLE_LOCK_FD:-}}" ]] && ai_lifecycle_lock stub-start; echo start >> "$EVENTS"; return 0; }}
                cmd_restart --profile general
            '''
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(source_file), str(root), str(events)],
                capture_output=True, text=True,
                env={**os.environ, **self.lock_env(root)},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(events.exists(), result.stderr + result.stdout)
            self.assertEqual(events.read_text().splitlines(), ["stop"])

            successful_events = root / "successful-events"
            success = subprocess.run(
                ["bash", "-c", command, "bash", str(source_file), str(root), str(successful_events)],
                capture_output=True, text=True,
                env={**os.environ, **self.lock_env(root), "STOP_STATUS": "0"},
            )
            self.assertEqual(success.returncode, 0, success.stderr)
            self.assertEqual(successful_events.read_text().splitlines(), ["stop", "start"])


if __name__ == "__main__":
    unittest.main()
