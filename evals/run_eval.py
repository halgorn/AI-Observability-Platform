#!/usr/bin/env python3
"""Regression eval: score dataset with judge, compare to baseline.

Exit codes:
  0  all dimensions within 5% of baseline (or no baseline yet)
  1  one or more dimensions regressed > 5%
  2  eval itself errored

Usage:
  python evals/run_eval.py                    # compare to baseline.json
  python evals/run_eval.py --save-baseline    # run + write new baseline.json
  python evals/run_eval.py --report out.json  # write full report to file
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).parent
REPO_ROOT = EVALS_DIR.parent
JUDGE_DIR = REPO_ROOT / "services" / "judge"

sys.path.insert(0, str(JUDGE_DIR))

from app.service import JudgeService, StubJudgeClient  # noqa: E402

DATASET_PATH = EVALS_DIR / "regression_dataset.jsonl"
BASELINE_PATH = EVALS_DIR / "baseline.json"
REGRESSION_THRESHOLD = 0.05


def load_dataset() -> list[dict]:
    cases = []
    with DATASET_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


async def run_eval(cases: list[dict], use_real_judge: bool = False) -> dict[str, list[float]]:
    if use_real_judge:
        import os
        from app.service import OpenAIJudgeClient
        client = OpenAIJudgeClient(api_key=os.environ.get("JUDGE_API_KEY"))
        n_judges = 1
    else:
        client = StubJudgeClient()
        n_judges = 1

    svc = JudgeService(client=client, n_judges=n_judges)
    results: dict[str, list[float]] = {}

    for case in cases:
        try:
            r = await svc.judge(
                input=case["input"],
                output=case["output"],
                dimension=case["dimension"],
            )
            results.setdefault(case["dimension"], []).append(r.score)
            print(f"  [{case['id']}] {case['dimension']} score={r.score:.3f}")
        except Exception as e:
            print(f"  [{case['id']}] ERROR: {e}", file=sys.stderr)

    return results


def build_summary(scores: dict[str, list[float]]) -> dict[str, dict]:
    return {
        dim: {
            "mean": round(sum(s) / len(s), 4) if s else 0.0,
            "min": round(min(s), 4) if s else 0.0,
            "max": round(max(s), 4) if s else 0.0,
            "n": len(s),
        }
        for dim, s in scores.items()
    }


def check_regression(current: dict[str, dict], baseline: dict[str, dict]) -> list[str]:
    failures = []
    for dim, stats in current.items():
        if dim not in baseline:
            continue
        delta = stats["mean"] - baseline[dim]["mean"]
        if delta < -REGRESSION_THRESHOLD:
            failures.append(
                f"{dim}: mean dropped {abs(delta):.3f} "
                f"(was {baseline[dim]['mean']:.3f}, now {stats['mean']:.3f})"
            )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--save-baseline", action="store_true")
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--real-judge", action="store_true", help="use real LLM (needs JUDGE_API_KEY)")
    args = parser.parse_args()

    try:
        cases = load_dataset()
        print(f"Loaded {len(cases)} eval cases from {DATASET_PATH.name}")
    except FileNotFoundError:
        print(f"ERROR: dataset not found at {DATASET_PATH}", file=sys.stderr)
        return 2

    try:
        scores = asyncio.run(run_eval(cases, use_real_judge=args.real_judge))
    except Exception as e:
        print(f"ERROR: eval run failed: {e}", file=sys.stderr)
        return 2

    summary = build_summary(scores)

    report = {"summary": summary, "cases": len(cases)}
    print(f"\n=== Eval Summary ===")
    for dim, stats in summary.items():
        print(f"  {dim:15s}  mean={stats['mean']:.3f}  min={stats['min']:.3f}  n={stats['n']}")

    if args.report:
        args.report.write_text(json.dumps(report, indent=2))
        print(f"\nReport written to {args.report}")

    if args.save_baseline:
        baseline_data = {dim: {"mean": s["mean"], "min": s["min"]} for dim, s in summary.items()}
        BASELINE_PATH.write_text(json.dumps(baseline_data, indent=2))
        print(f"Baseline saved to {BASELINE_PATH}")
        return 0

    if not BASELINE_PATH.exists():
        print("\nNo baseline.json found — run with --save-baseline to create one.")
        return 0

    baseline = json.loads(BASELINE_PATH.read_text())
    failures = check_regression(summary, baseline)

    if failures:
        print(f"\n❌ REGRESSION DETECTED (threshold={REGRESSION_THRESHOLD:.0%}):")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(f"\n✅ No regression (threshold={REGRESSION_THRESHOLD:.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
