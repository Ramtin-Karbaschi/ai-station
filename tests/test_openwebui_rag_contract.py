#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "compose.yml"
CLI = ROOT / "scripts/ai"
VERIFY = ROOT / "scripts/verify.sh"
PROVIDERS = ROOT / "config/providers.yaml"
CATALOG = ROOT / "config/model-catalog.json"
DOCS = ROOT / "docs/clients/OPENWEBUI.md"
MANAGER = ROOT / "AI Station/AI Station Manager.ps1"
WIN_README = ROOT / "AI Station/README.md"
ADR = ROOT / "docs/adr/ADR-005-retrieval-engine.md"


class OpenWebuiRagContractTests(unittest.TestCase):
    def test_hybrid_search_uses_local_cpu_reranker(self) -> None:
        env = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"][
            "open-webui"
        ]["environment"]
        self.assertEqual(env["ENABLE_RAG_HYBRID_SEARCH"], "True")
        self.assertEqual(env["RAG_RERANKING_ENGINE"], "external")
        self.assertEqual(env["RAG_RERANKING_MODEL"], "ai-station-reranker")
        self.assertEqual(
            env["RAG_EXTERNAL_RERANKER_URL"], "http://reranker:8091/v1/rerank"
        )
        self.assertEqual(env["RAG_TOP_K"], "20")
        self.assertEqual(env["RAG_TOP_K_RERANKER"], "3")
        self.assertEqual(env["RAG_FULL_CONTEXT"], "False")
        self.assertEqual(env["VECTOR_DB"], "pgvector")
        self.assertIn("function_calling", env["DEFAULT_MODEL_PARAMS"])
        self.assertIn("default", env["DEFAULT_MODEL_PARAMS"])
        self.assertNotIn("BAAI/", env["RAG_RERANKING_MODEL"])
        self.assertNotIn("huggingface", env["RAG_EXTERNAL_RERANKER_URL"])

    def test_start_and_verify_require_the_cpu_reranker(self) -> None:
        start = CLI.read_text(encoding="utf-8")
        verify = VERIFY.read_text(encoding="utf-8")
        self.assertIn(
            "ai_retry_compose --profile reranker up -d reranker", start
        )
        self.assertIn("ai_wait_compose_service reranker healthy 180", start)
        self.assertIn("http://127.0.0.1:8091/v1/models|Reranker", start)
        self.assertIn("http://127.0.0.1:8091/v1/models", verify)

    def test_reranker_stays_cpu_and_production(self) -> None:
        providers = yaml.safe_load(PROVIDERS.read_text(encoding="utf-8"))
        reranker = providers["providers"]["llama-cpp-reranker"]
        self.assertEqual(reranker["classification"], "production_default")
        self.assertFalse(reranker["heavy"])
        self.assertEqual(reranker["resource_group"], "cpu")
        self.assertEqual(reranker["port"], 8091)
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in catalog["models"]}
        self.assertIn("ai start", by_id["reranker-qwen3-0_6b"]["note"])

    def test_operator_docs_separate_notebooks_from_api_projects(self) -> None:
        docs = DOCS.read_text(encoding="utf-8")
        self.assertIn("Workspace → Knowledge", docs)
        self.assertIn("ai projects", docs)
        self.assertIn("does not store PDFs", docs)
        self.assertIn("function_calling=default", docs)
        manager = MANAGER.read_text(encoding="utf-8")
        self.assertIn("Workspace -> Knowledge", manager)
        win_readme = WIN_README.read_text(encoding="utf-8")
        self.assertIn("Workspace > Knowledge", win_readme)
        adr = ADR.read_text(encoding="utf-8")
        self.assertIn("hybrid BM25", adr)
        self.assertIn("llama-cpp-reranker", adr)

    def test_gitignore_keeps_retrieval_smoke_only(self) -> None:
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("benchmarks/results/**/retrieval/*", gitignore)
        self.assertIn("!benchmarks/results/**/retrieval/*-smoke.json", gitignore)


if __name__ == "__main__":
    unittest.main(verbosity=2)
