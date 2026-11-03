"""Flask app: pages and JSON API."""
import json
import os

from flask import Flask, jsonify, render_template, request

from compiler.analyze import analyze, get_table, get_model
from compiler.evaluation import (load_testcases, run_testcases, evaluate_saved, RESULTS_DIR)
from compiler.recovery import STRATEGIES, STRATEGY_LABELS, load_params
from compiler.grammar import prod_str

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


@app.errorhandler(ApiError)
def handle_api_error(e):
    return jsonify({"error": e.message}), e.status


@app.errorhandler(413)
def too_large(_):
    return jsonify({"error": "The request is too large."}), 413


@app.errorhandler(404)
def not_found(_):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found."}), 404
    return render_template("page.html", page="404", title="Not found"), 404


@app.errorhandler(500)
def server_error(_):
    return jsonify({"error": "Something went wrong while analysing the program."}), 500


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError("Send a JSON object.")
    return data


def read_source(data):
    src = data.get("source")
    if not isinstance(src, str):
        raise ApiError("'source' must be a string.")
    return src


def read_strategy(data):
    s = data.get("strategy", "automatic")
    if s not in STRATEGIES:
        raise ApiError(f"Unknown strategy '{s}'.")
    return s


# ---------------- pages ----------------
@app.route("/")
def page_analyze():
    return render_template("page.html", page="analyze", title="Analyze")


@app.route("/grammar")
def page_grammar():
    return render_template("page.html", page="grammar", title="Grammar")


@app.route("/model")
def page_model():
    return render_template("page.html", page="model", title="Model")


@app.route("/evaluation")
def page_evaluation():
    return render_template("page.html", page="evaluation", title="Evaluation")


@app.route("/favicon.ico")
def favicon():
    return "", 204


# ---------------- API ----------------
@app.post("/api/analyze")
def api_analyze():
    data = body()
    forced = {}
    for k, v in (data.get("apply") or {}).items():
        try:
            forced[int(k)] = str(v)
        except ValueError:
            raise ApiError("'apply' keys must be error numbers.")
    try:
        result = analyze(read_source(data), read_strategy(data), forced=forced)
    except ValueError as e:
        raise ApiError(str(e))
    return jsonify(result)


@app.post("/api/compare")
def api_compare():
    data = body()
    source = read_source(data)
    rows = []
    for key in STRATEGIES:
        try:
            r = analyze(source, key)
        except ValueError as e:
            raise ApiError(str(e))
        m = r["metrics"]
        rows.append({"strategy": key, "label": STRATEGY_LABELS[key], "errors": m["detected"],
                     "recovered": m["recovered"], "edits": m["edit_count"],
                     "skipped": m["resume_distance"], "completed": m["parse_completed"],
                     "recovered_source": r["recovered_source"],
                     "first_action": r["errors"][0]["detail"] if r["errors"] else ""})
    best = min((r["errors"] for r in rows), default=0)
    for r in rows:
        r["extra_errors"] = r["errors"] - best
    return jsonify({"rows": rows})


@app.get("/api/strategies")
def api_strategies():
    order = ["automatic", "panic", "insertion", "deletion", "replacement", "phrase"]
    return jsonify([{"key": k, "label": STRATEGY_LABELS[k]} for k in order])


@app.get("/api/examples")
def api_examples():
    with open(os.path.join(BASE, "data", "examples.json"), encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.get("/api/grammar")
def api_grammar():
    t = get_table()
    order = [t.g.start] + [a for a in t.g.productions if a != t.g.start]
    return jsonify({
        "start": t.g.start,
        "productions": [prod_str(a, p) for a in order for p in t.g.productions[a]],
        "first": {a: sorted(t.first[a]) for a in order},
        "follow": {a: sorted(t.follow[a]) for a in order},
        "nullable": sorted(t.nullable),
        "table": t.as_json(),
        "nonterminals": order,
    })


@app.get("/api/model")
def api_model():
    m = get_model()
    if m is None:
        return jsonify({"trained": False, "algorithm": "Isolation Forest"})
    return jsonify({"trained": True, "algorithm": "Isolation Forest",
                    "summary": m.summary(), "params": load_params()})


@app.get("/api/testcases")
def api_testcases():
    cases = load_testcases()
    run = run_testcases()
    by_name = {c["name"]: c for c in run["cases"]}
    for c in cases:
        c["result"] = by_name.get(c["name"])
    return jsonify({"cases": cases, "summary": {k: v for k, v in run.items() if k != "cases"}})


@app.get("/api/evaluation")
def api_evaluation():
    path = os.path.join(RESULTS_DIR, "evaluation.json")
    if not os.path.exists(path):
        return jsonify({"available": False})
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    data["available"] = True
    return jsonify(data)


@app.post("/api/evaluate")
def api_evaluate():
    return jsonify(evaluate_saved())


if __name__ == "__main__":
    app.run(debug=False, port=int(os.environ.get("PORT", 5000)))
