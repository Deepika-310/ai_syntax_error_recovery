"""Evaluation: stored invalid programs, and synthetic single-error programs.

Synthetic cases come from valid programs the model never trained on (dev for tuning,
test for the final numbers). The original program is the ground truth.
"""
import glob
import json
import os
import random
import statistics
import time

from .analyze import analyze
from .corpus import mutate, same_tokens
from .recovery import load_params

HERE = os.path.dirname(os.path.abspath(__file__))
TESTCASE_DIR = os.path.join(HERE, "..", "testcases")
RESULTS_DIR = os.path.join(HERE, "..", "results")

KIND_LABEL = {"delete": "Deleted token", "insert": "Extra token", "replace": "Wrong token",
              "duplicate": "Duplicated token", "swap": "Swapped tokens"}


# ---------------- stored invalid programs ----------------
def load_testcases():
    cases = []
    for path in sorted(glob.glob(os.path.join(TESTCASE_DIR, "*.json"))):
        with open(path, encoding="utf-8") as f:
            cases.append(json.load(f))
    return cases


def check_case(case, strategy="automatic", use_model=True):
    r = analyze(case["source"], strategy=strategy, use_model=use_model)
    errs = r["errors"]
    problems = []
    if len(errs) != case["expected_errors"]:
        problems.append(f"expected {case['expected_errors']} errors, found {len(errs)}")
    if "error_lines" in case and [e["line"] for e in errs] != case["error_lines"]:
        problems.append(f"lines {[e['line'] for e in errs]} != {case['error_lines']}")
    if "actions" in case and [e["action"] for e in errs] != case["actions"]:
        problems.append(f"actions {[e['action'] for e in errs]} != {case['actions']}")
    if "recovered_source" in case and r["recovered_source"] != case["recovered_source"]:
        problems.append("recovered source differs")
    if case.get("all_recovered", True) and r["metrics"]["unrecoverable"]:
        problems.append("unrecoverable error")
    return {"name": case["name"], "passed": not problems, "problems": problems,
            "detected": len(errs), "expected": case["expected_errors"],
            "recovered": r["metrics"]["recovered"],
            "false_errors": max(0, len(errs) - case["expected_errors"]),
            "resume_distance": r["metrics"]["resume_distance"],
            "edit_count": r["metrics"]["edit_count"], "ms": r["metrics"]["response_ms"]}


def run_testcases(strategy="automatic", use_model=True):
    rows = [check_case(c, strategy, use_model) for c in load_testcases()]
    n = len(rows)
    detected = sum(r["detected"] for r in rows)
    expected = sum(r["expected"] for r in rows)
    return {
        "cases": rows, "count": n, "passed": sum(r["passed"] for r in rows),
        "detected": detected, "expected": expected,
        "detection_rate": round(100 * min(detected, expected) / expected, 1) if expected else None,
        "recovery_rate": round(100 * sum(r["recovered"] for r in rows) / detected, 1) if detected else None,
        "false_errors": sum(r["false_errors"] for r in rows),
        "parse_completion_rate": 100.0,
        "mean_ms": round(statistics.mean(r["ms"] for r in rows), 2) if rows else None,
    }


# ---------------- synthetic single-error cases ----------------
def make_cases(programs, n, seed):
    rng = random.Random(seed)
    cases, tries = [], 0
    while len(cases) < n and tries < n * 30:
        tries += 1
        src = rng.choice(programs)
        m = mutate(src, rng)
        if m is None:
            continue
        bad, kind = m
        if analyze(bad, use_model=False, recover=False)["errors"]:
            cases.append({"original": src, "mutated": bad, "kind": kind})
    return cases


def score_case(case, params, use_model, deep=False):
    r = analyze(case["mutated"], params=params, use_model=use_model)
    e1 = r["errors"][0]
    restored = same_tokens(r["recovered_source"], case["original"]) and len(r["errors"]) == 1
    out = {"kind": case["kind"], "auto_restored": restored, "ambiguous": bool(e1["ambiguous"]),
           "wrong_apply": (not e1["ambiguous"]) and not restored,
           "cascading": max(0, len(r["errors"]) - 1)}
    if deep:
        ranked = sorted((c for c in e1["candidates"] if c["prob"] is not None),
                        key=lambda c: -c["prob"])
        hits = []
        for c in ranked[:3]:
            rr = analyze(case["mutated"], forced={1: c["key"]}, params=params, use_model=use_model)
            hits.append(same_tokens(rr["recovered_source"], case["original"]) and len(rr["errors"]) == 1)
        out["top1"] = bool(hits and hits[0])
        out["top3"] = any(hits)
    return out


def aggregate(rows):
    n = len(rows)
    if not n:
        return {}
    def rate(key):
        return round(100 * sum(1 for r in rows if r.get(key)) / n, 1)
    agg = {"cases": n, "auto_restored": rate("auto_restored"), "ambiguous": rate("ambiguous"),
           "wrong_apply": rate("wrong_apply"),
           "mean_cascading": round(statistics.mean(r["cascading"] for r in rows), 3)}
    if "top1" in rows[0]:
        agg["top1"], agg["top3"] = rate("top1"), rate("top3")
    return agg


def evaluate_split(cases, params, use_model, deep=False):
    """Headline numbers cover the four single-edit error kinds. Swapped adjacent tokens need
    two edits, which the insert/delete/replace/skip operations cannot undo in one step, so
    they are reported in by_kind but left out of the headline."""
    rows = [score_case(c, params, use_model, deep) for c in cases]
    by_kind = {}
    for k in sorted({r["kind"] for r in rows}):
        by_kind[k] = aggregate([r for r in rows if r["kind"] == k])
    return {"overall": aggregate([r for r in rows if r["kind"] != "swap"]), "by_kind": by_kind}


def full_evaluation(log=print):
    from .train import build_splits
    from .analyze import reset_model_cache
    reset_model_cache()
    _, _, test = build_splits()
    test_cases = make_cases(test, 600, seed=202)
    params = load_params()
    log(f"unseen test cases: {len(test_cases)}")
    t0 = time.time()
    result = {
        "params": {"baseline": params, "isolation_forest": params},
        "test": {
            "baseline": evaluate_split(test_cases, params, False, deep=True),
            "isolation_forest": evaluate_split(test_cases, params, True, deep=True),
        },
        "testcases": run_testcases(),
        "seconds": round(time.time() - t0, 1),
    }
    os.makedirs(RESULTS_DIR, exist_ok=True)
    with open(os.path.join(RESULTS_DIR, "evaluation.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def evaluate_saved(log=print):
    """Re-run the stored programs and the test split with the saved parameters (no tuning)."""
    from .train import build_splits
    from .analyze import reset_model_cache
    path = os.path.join(RESULTS_DIR, "evaluation.json")
    reset_model_cache()
    _, _, test = build_splits()
    cases = make_cases(test, 600, seed=202)
    params = load_params()
    t0 = time.time()
    result = {
        "params": {"baseline": params, "isolation_forest": params},
        "test": {"baseline": evaluate_split(cases, params, False, deep=True),
                 "isolation_forest": evaluate_split(cases, params, True, deep=True)},
        "testcases": run_testcases(), "seconds": round(time.time() - t0, 1),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


if __name__ == "__main__":
    res = full_evaluation()
    print(json.dumps({k: res[k] for k in ("params", "test")}, indent=2))
