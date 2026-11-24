from __future__ import annotations

import unittest
from unittest.mock import patch
from types import SimpleNamespace

from apps.gateway.app.admission import (
    admit,
    effective_max_heavy,
    estimate_required_vram_mib,
    get_provider,
    list_gpus,
    npu_present,
    uses_gpu_exclusivity,
    vram_probe_looks_stale,
    probe_free_vram_mib,
)


class AdmissionTests(unittest.TestCase):
    def test_wsl_gpu_probe_survives_service_path_without_nvidia_smi(self) -> None:
        with patch("apps.gateway.app.admission.shutil.which", return_value=None), \
             patch("apps.gateway.app.admission.Path.is_file", return_value=True), \
             patch("apps.gateway.app.admission.subprocess.run", return_value=SimpleNamespace(stdout="22000\n")) as run:
            self.assertEqual(probe_free_vram_mib(), 22000)
            self.assertEqual(run.call_args.args[0][0], "/usr/lib/wsl/lib/nvidia-smi")

    def test_shared_runtime_marker_resolves_to_lifecycle_owner(self) -> None:
        shared = {"profile": "comfyui-experimental", "service": "comfyui-experimental",
                  "lifecycle_command": "ai provider start comfyui-media-experimental"}
        registry = {"providers": {
            "hunyuan3d-2_1": {**shared, "id": "hunyuan3d-2_1"},
            "comfyui-media-experimental": {**shared, "id": "comfyui-media-experimental"},
        }}
        self.assertEqual(get_provider(registry, "comfyui-experimental")["id"],
                         "comfyui-media-experimental")
        self.assertEqual(get_provider(registry, "hunyuan3d-2_1")["id"], "hunyuan3d-2_1")

    def setUp(self) -> None:
        self.registry = {
            "admission": {
                "enforce": True,
                "safety_margin_vram_mib": 1024,
                "safety_margin_ram_mib": 4096,
                "max_active_heavy": 1,
                "allow_auto_stop_production": True,
                "default_fallback_provider": "llama-cpp-general",
            },
            "providers": {
                "llama-cpp-general": {
                    "id": "llama-cpp-general",
                    "heavy": True,
                    "minimum_vram_mib": 21000,
                    "minimum_ram_mib": 8192,
                    "minimum_storage_mib": 22000,
                    "kv_cache_mib_per_1k_context": 180,
                    "default_context": 8192,
                    "max_context": 32768,
                    "fallback_provider": None,
                },
                "llama-cpp-coder": {
                    "id": "llama-cpp-coder",
                    "heavy": True,
                    "minimum_vram_mib": 17500,
                    "minimum_ram_mib": 8192,
                    "minimum_storage_mib": 18000,
                    "kv_cache_mib_per_1k_context": 160,
                    "default_context": 8192,
                    "max_context": 32768,
                    "fallback_provider": "llama-cpp-general",
                },
                "comfyui-media-experimental": {
                    "id": "comfyui-media-experimental",
                    "heavy": True,
                    "minimum_vram_mib": 20000,
                    "minimum_ram_mib": 16384,
                    "minimum_storage_mib": 80000,
                    "kv_cache_mib_per_1k_context": 0,
                    "default_context": 1,
                    "max_context": 1,
                    "fallback_provider": None,
                },
                "n8n": {
                    "id": "n8n",
                    "heavy": False,
                    "resource_group": "cpu",
                    "minimum_vram_mib": 0,
                    "minimum_ram_mib": 1024,
                    "minimum_storage_mib": 512,
                    "kv_cache_mib_per_1k_context": 0,
                    "default_context": 1,
                    "max_context": 1,
                    "fallback_provider": None,
                },
                "cpu-mislabeled-heavy": {
                    "id": "cpu-mislabeled-heavy",
                    "heavy": True,
                    "resource_group": "cpu",
                    "minimum_vram_mib": 0,
                    "minimum_ram_mib": 1024,
                    "minimum_storage_mib": 512,
                    "kv_cache_mib_per_1k_context": 0,
                    "default_context": 1,
                    "max_context": 1,
                    "fallback_provider": None,
                },
            },
        }
        self.hardware = {
            "gpu": {"vram_total_mib": 24463},
            "memory": {"wsl_visible_total_gib": 47},
        }

    def test_start_when_budget_fits(self) -> None:
        decision = admit(
            "llama-cpp-general",
            registry=self.registry,
            hardware=self.hardware,
            free_vram_mib=24000,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=[],
        )
        self.assertEqual(decision.decision, "START")

    def test_stop_conflicting_and_start(self) -> None:
        decision = admit(
            "llama-cpp-coder",
            registry=self.registry,
            hardware=self.hardware,
            free_vram_mib=400,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=["llama-cpp-general"],
        )
        self.assertEqual(decision.decision, "STOP_CONFLICTING_PROVIDER_AND_START")
        self.assertEqual(decision.stop_providers, ["llama-cpp-general"])

    def test_ornith_coder_reserves_host_ram_for_offloaded_kv_before_switching(self) -> None:
        resources = {
            "hardware": self.hardware,
            "free_vram_mib": 982,
            "free_storage_mib": 500000,
            "active_heavy": ["llama-cpp-reasoning"],
        }
        decision = admit("llama-cpp-coder", free_ram_mib=34518, **resources)
        self.assertEqual(decision.decision, "STOP_CONFLICTING_PROVIDER_AND_START")
        self.assertEqual(decision.stop_providers, ["llama-cpp-reasoning"])
        self.assertEqual(decision.effective_context, decision.requested_context)
        self.assertEqual(decision.required_vram_mib, 21000)

        max_context = admit(
            "llama-cpp-coder", context=262144, free_ram_mib=34518, **resources
        )
        self.assertEqual(max_context.decision, decision.decision)
        self.assertEqual(max_context.effective_context, 262144)
        self.assertEqual(max_context.required_vram_mib, decision.required_vram_mib)

        low_ram = admit("llama-cpp-coder", free_ram_mib=24000, **resources)
        self.assertEqual(low_ram.decision, "REJECT")
        self.assertIn("insufficient system RAM including safety margin", low_ram.reasons)

    def test_reduced_context(self) -> None:
        decision = admit(
            "llama-cpp-general",
            context=32768,
            registry=self.registry,
            hardware=self.hardware,
            free_vram_mib=23000,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=[],
        )
        self.assertEqual(decision.decision, "START_WITH_REDUCED_CONTEXT")
        self.assertLess(decision.effective_context, 32768)

    def test_reject_insufficient_vram(self) -> None:
        decision = admit(
            "llama-cpp-general",
            registry=self.registry,
            hardware=self.hardware,
            free_vram_mib=1000,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=[],
        )
        self.assertEqual(decision.decision, "REJECT")

    def test_reject_insufficient_storage(self) -> None:
        decision = admit(
            "llama-cpp-general",
            registry=self.registry,
            hardware=self.hardware,
            free_vram_mib=24000,
            free_ram_mib=40000,
            free_storage_mib=100,
            active_heavy=[],
        )
        self.assertEqual(decision.decision, "REJECT")

    def test_fallback_when_configured(self) -> None:
        decision = admit(
            "llama-cpp-coder",
            registry=self.registry,
            hardware={"gpu": {"vram_total_mib": 8000}, "memory": {}},
            free_vram_mib=500,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=[],
        )
        self.assertEqual(decision.decision, "FALLBACK")
        self.assertEqual(decision.fallback_provider, "llama-cpp-general")

    def test_queue_when_auto_stop_disabled(self) -> None:
        registry = dict(self.registry)
        registry["admission"] = dict(self.registry["admission"])
        registry["admission"]["allow_auto_stop_production"] = False
        decision = admit(
            "llama-cpp-coder",
            registry=registry,
            hardware=self.hardware,
            free_vram_mib=400,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=["llama-cpp-general"],
        )
        self.assertEqual(decision.decision, "QUEUE")

    def test_comfyui_stops_conflicting_llama_cpp(self) -> None:
        decision = admit(
            "comfyui-media-experimental",
            registry=self.registry,
            hardware=self.hardware,
            free_vram_mib=400,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=["llama-cpp-general"],
        )
        self.assertEqual(decision.decision, "STOP_CONFLICTING_PROVIDER_AND_START")
        self.assertEqual(decision.stop_providers, ["llama-cpp-general"])

    def test_non_heavy_starts_when_vram_is_below_gpu_margin(self) -> None:
        decision = admit(
            "n8n",
            registry=self.registry,
            hardware=self.hardware,
            free_vram_mib=400,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=["llama-cpp-general"],
        )
        self.assertEqual(decision.decision, "START")
        self.assertEqual(decision.stop_providers, [])
        self.assertEqual(decision.required_vram_mib, 0)
        self.assertTrue(
            any("VRAM exclusivity does not apply" in r for r in decision.reasons)
        )

    def test_cpu_resource_group_does_not_stop_gpu_even_if_heavy(self) -> None:
        decision = admit(
            "cpu-mislabeled-heavy",
            registry=self.registry,
            hardware=self.hardware,
            free_vram_mib=400,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=["llama-cpp-general"],
        )
        self.assertEqual(decision.decision, "START")
        self.assertEqual(decision.stop_providers, [])
        self.assertFalse(
            uses_gpu_exclusivity(
                get_provider(self.registry, "cpu-mislabeled-heavy")
            )
        )

    def test_cpu_provider_still_rejects_on_insufficient_ram(self) -> None:
        decision = admit(
            "n8n",
            registry=self.registry,
            hardware=self.hardware,
            free_vram_mib=400,
            free_ram_mib=100,
            free_storage_mib=500000,
            active_heavy=["llama-cpp-general"],
        )
        self.assertEqual(decision.decision, "REJECT")
        self.assertIn("insufficient system RAM", decision.reasons[0])

    def test_gpu_heavy_uses_exclusivity(self) -> None:
        self.assertTrue(
            uses_gpu_exclusivity(
                get_provider(self.registry, "llama-cpp-general")
            )
        )
        self.assertFalse(
            uses_gpu_exclusivity(get_provider(self.registry, "n8n"))
        )

    def test_estimate_kv_budget(self) -> None:
        provider = get_provider(self.registry, "llama-cpp-general")
        self.assertEqual(
            estimate_required_vram_mib(provider, 8000),
            21000 + int(8 * 180),
        )

    def test_vram_probe_looks_stale_when_active_heavy_but_vram_nearly_full(
        self,
    ) -> None:
        warning = vram_probe_looks_stale(
            22935,
            ["llama-cpp-ornith"],
            self.hardware,
        )
        self.assertIsNotNone(warning)
        assert warning is not None
        self.assertIn("stale", warning.lower())
        self.assertIn("llama-cpp-ornith", warning)

    def test_vram_probe_not_stale_when_vram_matches_loaded_model(self) -> None:
        warning = vram_probe_looks_stale(
            2441,
            ["llama-cpp-ornith"],
            self.hardware,
        )
        self.assertIsNone(warning)

    def test_vram_probe_not_stale_when_no_heavy_active(self) -> None:
        warning = vram_probe_looks_stale(22935, [], self.hardware)
        self.assertIsNone(warning)

    def test_vram_probe_not_stale_when_gpu_total_unknown(self) -> None:
        warning = vram_probe_looks_stale(
            22935,
            ["llama-cpp-ornith"],
            {"gpu": {}, "memory": {}},
        )
        self.assertIsNone(warning)

    def test_one_gpu_host_keeps_exclusivity(self) -> None:
        self.assertEqual(effective_max_heavy(self.registry["admission"], self.hardware), 1)
        self.assertEqual(len(list_gpus(self.hardware)), 1)
        decision = admit(
            "llama-cpp-coder",
            registry=self.registry,
            hardware=self.hardware,
            free_vram_mib=400,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=["llama-cpp-general"],
        )
        self.assertEqual(decision.decision, "STOP_CONFLICTING_PROVIDER_AND_START")
        self.assertEqual(decision.gpu_index, 0)

    def test_two_gpu_fixture_places_second_heavy_on_gpu_index_1(self) -> None:
        hardware = {
            "gpus": [
                {"index": 0, "name": "GPU-0", "vram_total_mib": 24463},
                {"index": 1, "name": "GPU-1", "vram_total_mib": 24463},
            ],
            "gpu": {"vram_total_mib": 24463},
            "memory": {"wsl_visible_total_gib": 47},
            "npu": {"present": False, "status": "absent"},
        }
        registry = dict(self.registry)
        registry["admission"] = dict(self.registry["admission"])
        registry["admission"]["max_heavy_providers"] = 2
        registry["providers"] = dict(self.registry["providers"])
        registry["providers"]["llama-cpp-coder"] = dict(
            self.registry["providers"]["llama-cpp-coder"]
        )
        registry["providers"]["llama-cpp-coder"]["gpu_index"] = 1
        self.assertEqual(effective_max_heavy(registry["admission"], hardware), 2)
        decision = admit(
            "llama-cpp-coder",
            registry=registry,
            hardware=hardware,
            free_vram_mib=24000,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=["llama-cpp-general"],
        )
        self.assertEqual(decision.decision, "START")
        self.assertEqual(decision.gpu_index, 1)
        self.assertIn("gpu_index=1", " ".join(decision.reasons))
        self.assertEqual(decision.stop_providers, [])
        self.assertFalse(npu_present(hardware))

    def test_tensor_parallel_stays_opt_in(self) -> None:
        hardware = {
            "gpus": [
                {"index": 0, "vram_total_mib": 24463},
                {"index": 1, "vram_total_mib": 24463},
            ],
            "memory": {},
        }
        registry = dict(self.registry)
        registry["admission"] = dict(self.registry["admission"])
        registry["admission"]["max_heavy_providers"] = 2
        registry["providers"] = dict(self.registry["providers"])
        registry["providers"]["llama-cpp-coder"] = dict(
            self.registry["providers"]["llama-cpp-coder"]
        )
        registry["providers"]["llama-cpp-coder"]["tensor_parallel"] = True
        decision = admit(
            "llama-cpp-coder",
            registry=registry,
            hardware=hardware,
            free_vram_mib=400,
            free_ram_mib=40000,
            free_storage_mib=500000,
            active_heavy=["llama-cpp-general"],
        )
        self.assertEqual(decision.decision, "REJECT")
        self.assertIn("tensor-parallel", " ".join(decision.reasons))


if __name__ == "__main__":
    unittest.main()
