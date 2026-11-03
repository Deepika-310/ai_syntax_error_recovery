"""Grammar-constrained recovery decisions ranked by Isolation Forest anomaly scores."""
import json
import math
import os

from .candidates import generate
from .evaluator import evaluate

STRATEGIES = {
    "panic": {"sync"},
    "insertion": {"insert"},
    "deletion": {"delete"},
    "replacement": {"replace"},
    "phrase": {"insert", "delete", "replace"},
    "automatic": {"insert", "delete", "replace", "sync"},
}
STRATEGY_LABELS = {
    "automatic": "Automatic", "panic": "Panic mode", "insertion": "Token insertion",
    "deletion": "Token deletion", "replacement": "Token replacement", "phrase": "Phrase-level",
}

PARAMS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "params.json")
DEFAULT_PARAMS = {
    "temperature": 0.03, "tau": 0.4, "delta": 0.03, "cost_weight": 0.1,
    "k_gate": 4, "kmax": 12,
}


def load_params(overrides=None):
    params = dict(DEFAULT_PARAMS)
    if os.path.exists(PARAMS_PATH):
        with open(PARAMS_PATH, encoding="utf-8") as f:
            params.update(json.load(f))
    params.update(overrides or {})
    return params


class Recovery:
    def __init__(self, table, model=None, strategy="automatic", params=None):
        if strategy not in STRATEGIES:
            raise ValueError(f"unknown strategy '{strategy}'")
        self.table, self.model = table, model
        self.strategy = strategy
        self.p = load_params(params)

    def decide(self, stack_syms, tokens, pos, info, forced_key=None):
        p = self.p
        rows = []
        for candidate in generate(self.table, stack_syms, tokens, pos, info):
            ev = evaluate(self.table, candidate, stack_syms, tokens, pos, p["k_gate"], p["kmax"])
            anomaly = (self.model.anomaly_score(ev["tokens_after"], ev["edit_index"])
                       if self.model is not None else None)
            # Keep the Isolation Forest as the primary rank signal while preferring
            # shorter repairs when anomaly scores are close.
            rank_score = (anomaly + p["cost_weight"] * candidate.cost if anomaly is not None else
                          candidate.cost - ev["continuation"] / p["kmax"])
            rows.append({"cand": candidate, "ev": ev, "anomaly": anomaly,
                         "rank_score": rank_score, "prob": None})

        kinds = STRATEGIES[self.strategy]
        auto = [row for row in rows if row["cand"].kind in kinds and row["ev"]["valid"]
                and not row["cand"].suggestion_only]
        sync_row = next((row for row in rows if row["cand"].kind == "sync"), None)

        if auto:
            best_score = min(row["rank_score"] for row in auto)
            temperature = max(float(p["temperature"]), 1e-6)
            weights = [math.exp(-min((row["rank_score"] - best_score) / temperature, 700))
                       for row in auto]
            total = sum(weights)
            for row, weight in zip(auto, weights):
                row["prob"] = weight / total

        decision = {"rows": rows, "chosen": None, "ambiguous": False, "fell_back": False,
                    "forced": False, "auto": auto}
        forced_row = next((row for row in rows if row["cand"].key == forced_key), None) if forced_key else None
        if forced_row is not None:
            decision.update(chosen=forced_row, forced=True)
        elif not auto:
            decision.update(chosen=sync_row, fell_back=self.strategy != "panic")
        else:
            ranked = sorted(auto, key=lambda row: (
                row["rank_score"], row["cand"].cost, -row["ev"]["continuation"], row["cand"].key))
            top = ranked[0]
            second = ranked[1] if len(ranked) > 1 else None
            ambiguous = second is not None and (
                top["prob"] < p["tau"] or top["prob"] - second["prob"] < p["delta"])
            if ambiguous and sync_row is not None:
                decision.update(chosen=sync_row, ambiguous=True)
            else:
                decision.update(chosen=top, ambiguous=ambiguous)

        baseline = min(auto, key=lambda row: (
            row["cand"].cost - row["ev"]["continuation"] / p["kmax"], row["cand"].key)) if auto else None
        chosen = decision["chosen"]
        decision["model_changed"] = bool(
            self.model is not None and baseline is not None and chosen is not None
            and not decision["forced"] and not decision["ambiguous"]
            and baseline["cand"].key != chosen["cand"].key
        )
        rows.sort(key=lambda row: (
            not row["ev"]["valid"], row["cand"].suggestion_only, row["rank_score"], row["cand"].key))
        return decision
