"""Quality metrics for one analysis run."""


def run_metrics(result, elapsed_ms, expected_errors=None):
    errors = result["errors"]
    detected = len(errors)
    recovered = sum(1 for e in errors if e["status"].startswith("recovered"))
    panic = sum(1 for e in errors if e["status"] == "recovered by panic mode")
    edit_count = sum(len(e["tokens_inserted"]) + len(e["tokens_replaced"])
                     + (len(e["tokens_deleted"]) if e["action"] == "Delete" else 0) for e in errors)
    skipped = sum(len(e["tokens_deleted"]) for e in errors if e["action"] == "Panic-mode sync")
    m = {
        "detected": detected,
        "recovered": recovered,
        "panic_recoveries": panic,
        "unrecoverable": detected - recovered,
        "ambiguous": sum(1 for e in errors if e.get("ambiguous")),
        "recovery_rate": round(100.0 * recovered / detected, 1) if detected else None,
        "edit_count": edit_count,
        "resume_distance": skipped,
        "parse_completed": bool(result["completed"]),
        "response_ms": round(elapsed_ms, 2),
        "false_errors": None,
    }
    if expected_errors is not None:
        m["false_errors"] = max(0, detected - expected_errors)
    return m
