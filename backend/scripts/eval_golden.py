#!/usr/bin/env python3
"""
Evaluation script for NL→SQL pipeline on golden questions.

Usage:
    cd backend
    uv run python scripts/eval_golden.py [--verbose] [--json]

Outputs a table with: question | path | confidence | keywords | pass/fail
Prints final accuracy: overall, template-path, LLM-path.
"""
import asyncio
import argparse
import json
import sys
import time
from pathlib import Path

# Allow running from scripts/ dir or from backend/
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml


async def run_eval(verbose: bool = False, as_json: bool = False):
    # Load golden questions
    golden_path = Path(__file__).parent.parent / "tests" / "golden_questions.yaml"
    with open(golden_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    questions = data["golden_questions"]

    # Bootstrap app context
    from askdata.db.meta import init_db
    from askdata.semantic.loader import load_semantic_layer
    from askdata.rag.store import seed_if_empty, _get_model

    await init_db()
    load_semantic_layer()
    # Pre-load RAG model (blocking but only once)
    await asyncio.to_thread(seed_if_empty)
    await asyncio.to_thread(_get_model)

    from askdata.query.pipeline import run_pipeline

    results = []
    for item in questions:
        question = item["question"]
        expected_keywords = [kw.lower() for kw in item.get("expected_keywords", [])]
        expected_tables = item.get("expected_tables", [])

        t0 = time.time()
        try:
            resp = await run_pipeline(question, force_llm=False)
        except Exception as e:
            results.append({
                "question": question,
                "status": "error",
                "error": str(e),
                "path": "error",
                "confidence": 0.0,
                "sql": "",
                "keywords_hit": [],
                "keywords_miss": expected_keywords,
                "pass": False,
                "elapsed_ms": int((time.time() - t0) * 1000),
            })
            continue

        elapsed_ms = int((time.time() - t0) * 1000)
        status = resp.get("status", "error")

        if status != "ok":
            results.append({
                "question": question,
                "status": status,
                "path": resp.get("sql_source", "unknown"),
                "confidence": resp.get("confidence", {}).get("score", 0.0),
                "sql": "",
                "keywords_hit": [],
                "keywords_miss": expected_keywords,
                "pass": False,
                "elapsed_ms": elapsed_ms,
            })
            continue

        sql = resp.get("sql", "").lower()
        confidence = resp.get("confidence", {}).get("score", 0.0)
        sql_source = resp.get("sql_source", "llm")

        # Keyword check (case-insensitive substring match)
        hit = [kw for kw in expected_keywords if kw.lower() in sql]
        miss = [kw for kw in expected_keywords if kw.lower() not in sql]

        # Forbidden keywords check — catches old-schema hallucinations
        forbidden_keywords = [kw.lower() for kw in item.get("forbidden_keywords", [])]
        forbidden_hit = [kw for kw in forbidden_keywords if kw in sql]

        # Pass if all keywords found AND no forbidden keywords present
        passed = len(miss) == 0 and len(forbidden_hit) == 0

        results.append({
            "question": question,
            "status": "ok",
            "path": sql_source,
            "confidence": round(confidence, 2),
            "sql": sql[:200],
            "keywords_hit": hit,
            "keywords_miss": miss,
            "forbidden_hit": forbidden_hit,
            "pass": passed,
            "elapsed_ms": elapsed_ms,
        })

    if as_json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    # Pretty-print table
    total = len(results)
    passed = sum(1 for r in results if r["pass"])
    template_results = [r for r in results if r["path"] == "template"]
    llm_results = [r for r in results if r["path"] in ("llm", "llm_corrected")]
    template_pass = sum(1 for r in template_results if r["pass"])
    llm_pass = sum(1 for r in llm_results if r["pass"])

    print("\n" + "=" * 90)
    print(f"{'ВОПРОС':<45} {'ПУТЬ':<12} {'CONF':>5}  {'РЕЗУЛЬТАТ'}")
    print("=" * 90)

    for r in results:
        question_short = r["question"][:43] + ".." if len(r["question"]) > 45 else r["question"]
        miss_info = r.get("keywords_miss", [])[:2]
        forb_info = r.get("forbidden_hit", [])[:1]
        if r["pass"]:
            status_str = "✓ PASS"
        elif forb_info:
            status_str = f"✗ FAIL [forbidden: {forb_info[0]}]"
        else:
            status_str = f"✗ FAIL [{', '.join(miss_info)}]"
        print(f"{question_short:<45} {r['path']:<12} {r['confidence']:>5.2f}  {status_str}")
        if verbose and r.get("sql"):
            print(f"  SQL: {r['sql'][:100]}")

    print("=" * 90)
    print(f"\nИтого: {passed}/{total} ({100*passed//total}%)")
    if template_results:
        print(f"  template: {template_pass}/{len(template_results)} ({100*template_pass//len(template_results) if template_results else 0}%)")
    if llm_results:
        print(f"  llm:      {llm_pass}/{len(llm_results)} ({100*llm_pass//len(llm_results) if llm_results else 0}%)")

    avg_ms = int(sum(r["elapsed_ms"] for r in results) / len(results)) if results else 0
    print(f"  avg latency: {avg_ms} мс/запрос\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate NL→SQL pipeline on golden questions")
    parser.add_argument("--verbose", action="store_true", help="Print generated SQL for each question")
    parser.add_argument("--json", action="store_true", help="Output raw JSON results")
    args = parser.parse_args()
    asyncio.run(run_eval(verbose=args.verbose, as_json=args.json))
