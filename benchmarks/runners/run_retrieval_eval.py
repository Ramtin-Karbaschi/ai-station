#!/usr/bin/env python3
"""Offline retrieval metric harness for the public-safe corpus.

Computes lexical Recall@K / MRR / nDCG as a Phase 4 baseline that does not
require installing Qdrant. Optional embedding endpoint scoring can be added
later; this runner is intentionally dependency-light.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


def tokenize(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text)}


def score(query: str, doc_text: str) -> float:
    q = tokenize(query)
    d = tokenize(doc_text)
    if not q or not d:
        return 0.0
    overlap = len(q & d)
    return overlap / math.sqrt(len(q) * len(d))


def dcg(relevances: list[float]) -> float:
    total = 0.0
    for idx, rel in enumerate(relevances, start=1):
        total += (2**rel - 1) / math.log2(idx + 1)
    return total


def evaluate(corpus: dict[str, Any], k: int = 3) -> dict[str, Any]:
    docs = corpus["documents"]
    queries = corpus["queries"]
    started = time.perf_counter()
    per_query: list[dict[str, Any]] = []
    recalls: list[float] = []
    mrrs: list[float] = []
    ndcgs: list[float] = []

    for query in queries:
        ranked = sorted(
            docs,
            key=lambda doc: score(query["text"], f'{doc["title"]} {doc["text"]}'),
            reverse=True,
        )
        top = ranked[:k]
        relevant = set(query["relevant_doc_ids"])
        hit_ranks = [
            idx
            for idx, doc in enumerate(top, start=1)
            if doc["id"] in relevant
        ]
        recall = len({doc["id"] for doc in top} & relevant) / max(len(relevant), 1)
        mrr = 1.0 / hit_ranks[0] if hit_ranks else 0.0
        gains = [1.0 if doc["id"] in relevant else 0.0 for doc in top]
        ideal = sorted(gains, reverse=True)
        ndcg = (dcg(gains) / dcg(ideal)) if any(ideal) else 0.0
        recalls.append(recall)
        mrrs.append(mrr)
        ndcgs.append(ndcg)
        per_query.append(
            {
                "id": query["id"],
                "top_ids": [doc["id"] for doc in top],
                "recall_at_k": recall,
                "mrr": mrr,
                "ndcg": ndcg,
            }
        )

    elapsed_ms = (time.perf_counter() - started) * 1000
    return {
        "engine": "lexical-baseline",
        "corpus_id": corpus.get("corpus_id"),
        "k": k,
        "document_count": len(docs),
        "query_count": len(queries),
        "metrics": {
            "recall_at_k": sum(recalls) / len(recalls),
            "mrr": sum(mrrs) / len(mrrs),
            "ndcg": sum(ndcgs) / len(ndcgs),
            "eval_wall_ms": elapsed_ms,
        },
        "queries": per_query,
        "decision_note": (
            "Lexical baseline only. pgvector remains production default "
            "per ADR-005 until an embedding-backed gap justifies Qdrant."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus",
        default="benchmarks/datasets/retrieval/public_safe_v1.json",
    )
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument(
        "--out",
        default="",
        help="Optional result JSON path",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    corpus_path = (root / args.corpus).resolve()
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    result = evaluate(corpus, k=args.k)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    result["corpus_path"] = str(corpus_path.relative_to(root))

    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
