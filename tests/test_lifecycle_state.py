from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == "posix", "Bash lifecycle helpers require POSIX")
class LifecycleStateTests(unittest.TestCase):
    def test_ready_cpu_chat_skips_low_ram_admission_but_runs_visible_canary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            events = directory / "events"
            python = directory / "python3"
            python.write_text(
                "#!/bin/bash\n"
                "printf '%s\\n' \"$*\" >> \"$PYLOG\"\n"
                "printf '%s\\n' '{\"decision\":\"REJECT\",\"reasons\":[\"low RAM\"]}'\n",
                encoding="utf-8",
            )
            python.chmod(0o755)
            script = r'''source "$1"; source "$2"
ai_cpu_fallback_runtime_ready(){ return 0; }
ai_chat_generation_canary(){ printf 'visible-canary\n' >> "$EVENTS"; }
ai_retry_compose(){ printf 'unexpected-compose\n' >> "$EVENTS"; return 99; }
ai_start_cpu_fallback
'''
            result = subprocess.run(
                ["bash", "-c", script, "bash", str(ROOT / "scripts/lib/ai-common.sh"),
                 str(ROOT / "scripts/lib/ai-models.sh")],
                env={**os.environ, "ROOT": str(ROOT), "EVENTS": str(events),
                     "PYLOG": str(directory / "python.log"),
                     "PATH": f"{directory}:{os.environ['PATH']}"},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("already ready", result.stdout)
            self.assertEqual(events.read_text().splitlines(), ["visible-canary"])
            self.assertFalse((directory / "python.log").exists())

    def test_cold_cpu_chat_runs_admission_compose_and_visible_canary(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            events = directory / "events"
            python = directory / "python3"
            python.write_text(
                "#!/bin/bash\n"
                "printf '%s\\n' \"$*\" >> \"$PYLOG\"\n"
                "if [[ \"$1\" == -m && \"$2\" == apps.gateway.app.admission ]]; then\n"
                "  printf '%s\\n' '{\"decision\":\"START\",\"stop_providers\":[]}'\n"
                "  exit 0\n"
                "fi\n"
                f"exec {sys.executable} \"$@\"\n",
                encoding="utf-8",
            )
            python.chmod(0o755)
            script = r'''source "$1"; source "$2"
ai_cpu_fallback_runtime_ready(){ return 1; }
ai_retry_compose(){ printf 'compose %s\n' "$*" >> "$EVENTS"; }
ai_wait_url(){ printf 'wait %s\n' "$*" >> "$EVENTS"; }
ai_chat_generation_canary(){ printf 'visible-canary\n' >> "$EVENTS"; }
ai_start_cpu_fallback
'''
            result = subprocess.run(
                ["bash", "-c", script, "bash", str(ROOT / "scripts/lib/ai-common.sh"),
                 str(ROOT / "scripts/lib/ai-models.sh")],
                env={**os.environ, "ROOT": str(ROOT), "EVENTS": str(events),
                     "PYLOG": str(directory / "python.log"),
                     "PATH": f"{directory}:{os.environ['PATH']}"},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            event_lines = events.read_text().splitlines()
            self.assertEqual(event_lines[0], "compose --profile cpu-chat up -d llm-general-cpu")
            self.assertTrue(event_lines[1].startswith("wait http://127.0.0.1:8089/v1/models"))
            self.assertEqual(event_lines[2], "visible-canary")
            python_calls = (directory / "python.log").read_text().splitlines()
            self.assertIn("-m apps.gateway.app.admission llama-cpp-general-cpu --context 2048 --json", python_calls)

    def test_cpu_dependency_preserves_healthy_reranker(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802 - stdlib handler API
                payload = {"data": [{"id": "ai-station-reranker"}]}
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            events = Path(tempfile.mkdtemp()) / "events"
            script = r'''source "$1"; source "$2"
ai_retry_compose(){ printf 'recreated\n' >> "$EVENTS"; return 99; }
ai_wait_compose_service(){ printf 'waited\n' >> "$EVENTS"; }
ai_start_cpu_dependency reranker "$URL" Reranker ai-station-reranker reranker
'''
            result = subprocess.run(
                ["bash", "-c", script, "bash", str(ROOT / "scripts/lib/ai-common.sh"),
                 str(ROOT / "scripts/lib/ai-models.sh")],
                env={**os.environ, "URL": f"http://127.0.0.1:{server.server_port}/v1/models",
                     "EVENTS": str(events), "ROOT": str(ROOT)},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("preserving existing container", result.stdout)
            self.assertFalse(events.exists())
        finally:
            server.shutdown()
            server.server_close()

    def test_cpu_dependency_cold_start_retries_without_recreating_healthy_path(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            requests = 0

            def do_GET(self):  # noqa: N802 - stdlib handler API
                type(self).requests += 1
                if type(self).requests == 1:
                    self.send_error(503)
                    return
                payload = {"data": [{"id": "ai-station-reranker"}]}
                body = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            events = Path(tempfile.mkdtemp()) / "events"
            script = r'''source "$1"; source "$2"
ai_retry_compose(){ printf '%s\n' "$*" >> "$EVENTS"; }
ai_wait_compose_service(){ printf 'waited %s\n' "$*" >> "$EVENTS"; }
ai_start_cpu_dependency reranker "$URL" Reranker ai-station-reranker reranker
'''
            result = subprocess.run(
                ["bash", "-c", script, "bash", str(ROOT / "scripts/lib/ai-common.sh"),
                 str(ROOT / "scripts/lib/ai-models.sh")],
                env={**os.environ, "URL": f"http://127.0.0.1:{server.server_port}/v1/models",
                     "EVENTS": str(events), "ROOT": str(ROOT)},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--profile reranker up -d reranker", events.read_text())
            self.assertIn("ai-station-reranker", result.stdout)
        finally:
            server.shutdown()
            server.server_close()

    def test_provider_dry_run_uses_observed_heavy_when_marker_is_missing(self) -> None:
        import json
        import sys

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "active-heavy-profile"
            docker = directory / "docker"
            docker.write_text(
                "#!/bin/bash\n"
                "if [[ \"$1\" == ps ]]; then echo ai-station-llm-general; fi\n"
            )
            docker.chmod(0o755)
            python = directory / "python3"
            python.write_text(
                "#!/bin/bash\n"
                "case \"$*\" in\n"
                "  *'-m apps.gateway.app.admission'*'--active-heavy llama-cpp-general'*)\n"
                "    printf '%s\\n' '{\"decision\":\"STOP_CONFLICTING_PROVIDER_AND_START\",\"active_heavy\":[\"llama-cpp-general\"]}' ;;\n"
                "  *'-m apps.gateway.app.admission'*)\n"
                "    printf '%s\\n' '{\"decision\":\"FALLBACK\",\"active_heavy\":[]}' ;;\n"
                f"  *) exec {sys.executable} \"$@\" ;;\n"
                "esac\n"
            )
            python.chmod(0o755)
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/ai"), "provider", "start",
                 "comfyui-media-experimental", "--dry-run"],
                capture_output=True,
                text=True,
                env={
                    **os.environ,
                    "PATH": str(directory) + ":" + os.environ["PATH"],
                    "AI_STATE_DIR": str(directory),
                    "AI_ACTIVE_PROFILE_FILE": str(marker),
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("STOP_CONFLICTING_PROVIDER_AND_START", result.stdout)
            self.assertFalse(marker.exists())

    def test_provider_start_preserves_admission_denials_and_never_runs_docker(self) -> None:
        import json
        import shlex
        import sys

        for decision, exit_code in (("REJECT", 2), ("QUEUE", 0), ("FALLBACK", 0),
                                    ("START_WITH_REDUCED_CONTEXT", 0)):
            with self.subTest(decision=decision), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                python = directory / "python3"
                payload = json.dumps({"decision": decision, "reasons": ["fixture resource constraint"]})
                python.write_text('#!/bin/bash\ncase "$*" in\n'
                                  '  *"-m apps.gateway.app.admission"*)\n'
                                  f'    printf "%s\\n" {shlex.quote(payload)}; exit {exit_code} ;;\n'
                                  f'  *) exec {shlex.quote(sys.executable)} "$@" ;;\nesac\n')
                python.chmod(0o755)
                docker = directory / "docker"
                docker.write_text(
                    '#!/bin/bash\n'
                    'if [[ "$1" != ps ]]; then touch "'
                    + str(directory / "docker-called")
                    + '"; fi\n'
                )
                docker.chmod(0o755)
                result = subprocess.run(["bash", str(ROOT / "scripts/ai"), "provider", "start",
                                         "comfyui-media-experimental"], capture_output=True, text=True,
                                        env={**os.environ, "PATH": str(directory) + ":" + os.environ["PATH"],
                                             "AI_STATE_DIR": str(directory),
                                             "AI_LIFECYCLE_LOCK_FILE": str(directory / "lifecycle.lock")})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(decision, result.stdout)
                self.assertIn("fixture resource constraint", result.stdout)
                self.assertFalse((directory / "docker-called").exists())

    def test_busy_lock_preserves_holder_and_blocks_second_start(self) -> None:
        import fcntl

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            lock = directory / "lifecycle.lock"
            with lock.open("w+") as holder:
                holder.write("existing start pid=123\n")
                holder.flush()
                fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run(
                    ["bash", "-c", 'source "$1"; ai_lifecycle_lock start',
                     "bash", str(ROOT / "scripts/lib/ai-common.sh")],
                    env={**os.environ, "AI_STATE_DIR": str(directory),
                         "AI_LIFECYCLE_LOCK_FILE": str(lock)},
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 4)
                self.assertIn("existing start pid=123", result.stderr)
                self.assertEqual(lock.read_text(), "existing start pid=123\n")

    def test_busy_lock_blocks_direct_model_switch_before_compose(self) -> None:
        import fcntl

        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            lock = directory / "lifecycle.lock"
            with lock.open("w+") as holder:
                holder.write("existing media transition pid=123\n")
                holder.flush()
                fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = subprocess.run(
                    ["bash", "-c", 'source "$1"; source "$2"; '
                     'ai_active_heavy_profile(){ printf general; }; '
                     'ai_profile_service(){ printf llm-general; }; '
                     'ai_profile_port(){ printf 8082; }; '
                     'cmd_models_use general',
                     "bash", str(ROOT / "scripts/lib/ai-common.sh"),
                     str(ROOT / "scripts/lib/ai-models.sh")],
                    env={**os.environ, "AI_STATE_DIR": str(directory),
                         "AI_LIFECYCLE_LOCK_FILE": str(lock)},
                    capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 4)
                self.assertIn("existing media transition pid=123", result.stderr)
                self.assertNotIn("Switching heavy model", result.stdout)

    def run_helper(self, directory: Path, profile: str) -> None:
        subprocess.run(
            ["bash", "-c", 'source "$1"; ai_set_active_heavy_profile "$2"',
             "bash", str(ROOT / "scripts/lib/ai-common.sh"), profile],
            env={**os.environ, "AI_STATE_DIR": str(directory),
                 "AI_ACTIVE_PROFILE_FILE": str(directory / "active-heavy-profile")},
            check=True, capture_output=True, text=True,
        )

    def test_replaces_read_only_marker_and_can_clear_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "active-heavy-profile"
            marker.write_text("coder\n")
            marker.chmod(0o444)
            self.run_helper(directory, "general")
            self.assertEqual(marker.read_text(), "general\n")
            self.assertEqual(marker.stat().st_mode & 0o777, 0o660)
            self.assertEqual(marker.stat().st_gid, directory.stat().st_gid)
            self.assertEqual(list(directory.iterdir()), [marker])
            self.run_helper(directory, "")
            self.assertEqual(list(directory.iterdir()), [])

    def test_replaces_symlink_without_overwriting_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            target = directory / "other-state"
            target.write_text("unchanged\n")
            marker = directory / "active-heavy-profile"
            marker.symlink_to(target)
            self.run_helper(directory, "general")
            self.assertFalse(marker.is_symlink())
            self.assertEqual(marker.read_text(), "general\n")
            self.assertEqual(target.read_text(), "unchanged\n")

    def test_active_profile_prefers_live_gateway_selected_model(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "active-heavy-profile"
            marker.write_text("coder\n")
            docker = directory / "docker"
            docker.write_text('#!/bin/bash\nif [[ "$1" == ps ]]; then echo ai-station-llm-general; fi\n')
            docker.chmod(0o755)
            result = subprocess.run(
                ["bash", "-c", 'source "$1"; ai_active_heavy_profile',
                 "bash", str(ROOT / "scripts/lib/ai-common.sh")],
                env={**os.environ, "PATH": str(directory) + ":" + os.environ["PATH"],
                     "AI_STATE_DIR": str(directory), "AI_ACTIVE_PROFILE_FILE": str(marker)},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "general")

    def test_model_switch_publishes_marker_after_readiness_and_warmup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "active-heavy-profile"
            script = r'''source "$1"; source "$2"
AI_LIFECYCLE_LOCK_FD=1
ai_is_heavy_profile(){ return 0; }
ai_active_heavy_profile(){ :; }
ai_profile_service(){ printf 'llm-%s' "$1"; }
ai_profile_port(){ printf '8082'; }
public_name_for_profile(){ printf 'model-%s' "$1"; }
ai_stop_experimental_gpu_overlays(){ :; }
ai_compose(){ :; }
ai_wait_url(){ test ! -e "$AI_ACTIVE_PROFILE_FILE"; }
ai_litellm_warmup_chat(){ test ! -e "$AI_ACTIVE_PROFILE_FILE"; }
cmd_models_use general
'''
            result = subprocess.run(
                ["bash", "-c", script, "bash", str(ROOT / "scripts/lib/ai-common.sh"),
                 str(ROOT / "scripts/lib/ai-models.sh")],
                env={**os.environ, "AI_STATE_DIR": str(directory),
                     "AI_ACTIVE_PROFILE_FILE": str(marker)},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(), "general\n")

    def test_failed_model_readiness_does_not_publish_target_marker(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            marker = directory / "active-heavy-profile"
            script = r'''source "$1"; source "$2"
AI_LIFECYCLE_LOCK_FD=1
ai_is_heavy_profile(){ return 0; }
ai_active_heavy_profile(){ :; }
ai_profile_service(){ printf 'llm-%s' "$1"; }
ai_profile_port(){ printf '8082'; }
public_name_for_profile(){ printf 'model-%s' "$1"; }
ai_stop_experimental_gpu_overlays(){ :; }
ai_compose(){ :; }
ai_wait_url(){ return 8; }
ai_litellm_warmup_chat(){ return 0; }
cmd_models_use general
'''
            result = subprocess.run(
                ["bash", "-c", script, "bash", str(ROOT / "scripts/lib/ai-common.sh"),
                 str(ROOT / "scripts/lib/ai-models.sh")],
                env={**os.environ, "AI_STATE_DIR": str(directory),
                     "AI_ACTIVE_PROFILE_FILE": str(marker)},
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertFalse(marker.exists())

    def test_start_publishes_marker_only_after_auxiliary_readiness_and_warmup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            scripts = root / "scripts"
            (scripts / "lib").mkdir(parents=True)
            source_file = scripts / "ai-source"
            source_file.write_text(
                (ROOT / "scripts" / "ai").read_text(encoding="utf-8").rsplit(
                    'main "$@"', 1
                )[0],
                encoding="utf-8",
            )
            for source_lib in (ROOT / "scripts" / "lib").glob("*.sh"):
                (scripts / "lib" / source_lib.name).write_text(
                    source_lib.read_text(encoding="utf-8"), encoding="utf-8"
                )
            idle_timeout = scripts / "ensure-wsl-idle-timeout.sh"
            idle_timeout.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
            idle_timeout.chmod(0o755)
            for helper in ("sync-litellm-db-url.sh", "ensure-litellm-db.sh"):
                path = scripts / helper
                path.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
                path.chmod(0o755)
            marker = root / "state" / "active-heavy-profile"
            command = r'''source "$1"
AI_LIFECYCLE_LOCK_FD=1
ai_lifecycle_lock(){ :; }
ai_ensure_docker(){ :; }
ai_stop_experimental_gpu_overlays(){ :; }
ai_ensure_network(){ :; }
ai_retry_compose(){ :; }
ai_runtime_gpu_status(){ printf available; }
ai_cpu_fallback_enabled(){ printf true; }
ai_start_cpu_dependency(){ :; }
ai_start_cpu_fallback(){ touch "$AI_STATE_DIR/cpu-fallback-called"; return 99; }
ai_wait_compose_service(){ :; }
ai_ensure_host_gateway(){ :; }
ai_tools_start(){ :; }
ai_wait_url(){
  if [[ "${FAIL_LABEL:-}" == "$2" ]]; then return 1; fi
  return 0
}
ai_litellm_warmup_chat(){ [[ "${FAIL_WARMUP:-0}" != 1 ]]; }
ai_print_service_directory(){ :; }
cmd_start --profile general
'''
            base_env = {
                **os.environ,
                "AI_STATE_DIR": str(marker.parent),
                "AI_ACTIVE_PROFILE_FILE": str(marker),
            }
            for failure_env in (
                {"FAIL_LABEL": "Open WebUI"},
                {"FAIL_WARMUP": "1"},
            ):
                with self.subTest(failure_env=failure_env):
                    marker.unlink(missing_ok=True)
                    result = subprocess.run(
                        ["bash", "-c", command, "bash", str(source_file)],
                        capture_output=True,
                        text=True,
                        env={**base_env, **failure_env},
                    )
                    self.assertNotEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(marker.exists(), result.stdout)

            marker.unlink(missing_ok=True)
            result = subprocess.run(
                ["bash", "-c", command, "bash", str(source_file)],
                capture_output=True,
                text=True,
                env=base_env,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(marker.read_text(encoding="utf-8"), "general\n")
            self.assertFalse((marker.parent / "cpu-fallback-called").exists())

    def test_models_stop_checks_media_busy_before_stopping_llama(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            script = r'''source "$1"; source "$2"
AI_LIFECYCLE_LOCK_FD=1
ai_stop_experimental_gpu_overlays(){ echo checked-media; return 9; }
ai_compose(){ echo stopped-llama; }
ai_profile_service(){ printf 'llm-%s' "$1"; }
cmd_models_stop
'''
            result = subprocess.run(
                ["bash", "-c", script, "bash", str(ROOT / "scripts/lib/ai-common.sh"),
                 str(ROOT / "scripts/lib/ai-models.sh")],
                env={**os.environ, "AI_STATE_DIR": str(directory)},
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("checked-media", result.stdout)
            self.assertNotIn("stopped-llama", result.stdout)
