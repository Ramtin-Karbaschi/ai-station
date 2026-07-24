from __future__ import annotations

import unittest

from apps.gateway.app.admission import admit, estimate_required_vram_mib, get_provider


class AdmissionTests(unittest.TestCase):
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

    def test_estimate_kv_budget(self) -> None:
        provider = get_provider(self.registry, "llama-cpp-general")
        self.assertEqual(
            estimate_required_vram_mib(provider, 8000),
            21000 + int(8 * 180),
        )


if __name__ == "__main__":
    unittest.main()
