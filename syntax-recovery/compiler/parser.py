"""LL(1) predictive parser with an explicit stack and pluggable error recovery."""
from .candidates import simulate
from .error_detector import find_error, error_location, expected_text
from .lexer import display
from .parsing_table import SYNCH
from .trace import Trace

MAX_STEPS = 20000
MISSING_LABEL = {"Expr": "expression", "Term": "expression", "Factor": "expression",
                 "ExprRest": "expression", "TermRest": "expression", "Stmt": "statement",
                 "Cond": "condition", "RelOp": "operator"}
OPS = {"+", "-", "*", "/"}


def _node(sym):
    return {"sym": sym, "children": []}


def insertion_text(source, offset, term):
    if term in ";)],":
        return term
    if term == "}":
        return "}" if offset == 0 or source[offset - 1] == "\n" else "\n}"
    lead = " " if offset > 0 and not source[offset - 1].isspace() else ""
    nxt = source[offset] if offset < len(source) else ""
    trail = " " if nxt and not nxt.isspace() else ""
    return f"{lead}{term}{trail}"


def deletion_span(source, tok):
    ls = source.rfind("\n", 0, tok.offset) + 1
    le = source.find("\n", tok.end_offset)
    le = len(source) if le < 0 else le
    if not source[ls:tok.offset].strip() and not source[tok.end_offset:le].strip():
        return ls, min(le + 1, len(source)) - ls          # token is alone on its line
    end = tok.end_offset
    while end < len(source) and source[end] in " \t":
        end += 1
    start = tok.offset
    if end == tok.end_offset:                             # nothing after it: take spaces before it
        while start > 0 and source[start - 1] in " \t":
            start -= 1
    return start, end - start


def apply_edits(source, edits):
    ops = [(e["offset"], e.get("length", 0), e.get("text", ""), i)
           for i, e in enumerate(edits) if e["kind"] in ("insert", "delete", "replace")]
    ops.sort(key=lambda o: (o[0], o[3]))
    out, cur = [], 0
    for off, ln, text, _ in ops:
        if off < cur:
            continue
        out.append(source[cur:off])
        out.append(text)
        cur = off + ln
    out.append(source[cur:])
    return "".join(out)


class Parser:
    def __init__(self, table):
        self.table = table

    def parse(self, source, tokens, recovery=None, forced=None):
        table, nts = self.table, self.table.g.nonterminals
        forced = forced or {}
        tokens = list(tokens)
        pos = 0
        root = _node(table.g.start)
        stack = [("$", None), (table.g.start, root)]
        trace, errors, edits = Trace(), [], []
        stuck, last_progress = 0, None
        aborted = False

        def syms():
            return [s for s, _ in stack]

        for _ in range(MAX_STEPS):
            top, node = stack[-1]
            tok = tokens[pos]
            info = find_error(table, syms(), tok)

            if info is None:
                if top == "$":
                    trace.add(syms(), tokens, pos, "Accept", "accept")
                    break
                if top in nts:
                    prod = table.get(top, tok.type)
                    trace.add(syms(), tokens, pos,
                              f"Expand {top} → {' '.join(prod) if prod else 'ε'}")
                    stack.pop()
                    kids = [_node(s) for s in prod]
                    node["children"] = kids
                    node["prod"] = " ".join(prod) if prod else "ε"
                    for s, k in reversed(list(zip(prod, kids))):
                        stack.append((s, k))
                else:
                    trace.add(syms(), tokens, pos, f"Match {display(top)}" + (f" ({tok.text})" if top in ("id", "num") else ""))
                    node.update(text=tok.text, inserted=tok.inserted, replaced_from=tok.replaced_from)
                    stack.pop()
                    pos += 1
                continue

            # ---- error ----
            err_no = len(errors) + 1
            line, col = error_location(info, tokens, pos)
            unexpected = display(tok.type) if tok.type in ("id", "num", "$") else tok.text
            exp = expected_text(info["primary"])
            also = expected_text(info["allowed"] - info["primary"])
            trace.add(syms(), tokens, pos,
                      f"Error: unexpected {unexpected}, expected {' / '.join(exp)}", "error")
            rec = {"id": err_no, "line": line, "col": col, "unexpected": unexpected,
                   "expected": exp, "also_valid": also, "parser_state": info["top"],
                   "stack": syms()[::-1], "current_token": tok.text or "$", "kind": info["kind"],
                   "synch_entry": info["kind"] == "synch"}
            prev = tokens[pos - 1] if pos > 0 else None

            if recovery is None:                       # plain parser: stop at the first error
                rec.update(action="None", status="unrecoverable", cost=0,
                           problem=f"Unexpected {unexpected}", detail="Recovery is off.",
                           tokens_inserted=[], tokens_deleted=[], tokens_replaced=[],
                           sync_token=None, resume=None, candidates=[],
                           ambiguous=False, fell_back=False)
                errors.append(rec)
                aborted = True
                break

            dec = recovery.decide(syms(), tokens, pos, info, forced.get(err_no))
            row = dec["chosen"]
            cand = row["cand"]
            rec.update(candidates=_candidate_rows(dec, tokens, pos), ambiguous=dec["ambiguous"],
                       fell_back=dec["fell_back"], forced=dec["forced"], model_changed=dec["model_changed"], strategy=recovery.strategy,
                       cost=cand.cost,
                       tokens_inserted=[], tokens_deleted=[], tokens_replaced=[], sync_token=None)

            skipped = []
            if cand.kind == "insert":
                _, tokens, _, _ = simulate(cand, syms(), tokens, pos)
                off = tokens[pos].offset
                edits.append({"kind": "insert", "offset": off,
                              "text": insertion_text(source, off, cand.term), "token": cand.term})
                rec["tokens_inserted"].append(cand.term)
                action, detail = "Insert", f"Inserted {display(cand.term)}"
            elif cand.kind == "delete":
                start, ln = deletion_span(source, tok)
                edits.append({"kind": "delete", "offset": start, "length": ln, "token": tok.text})
                rec["tokens_deleted"].append(tok.text)
                _, tokens, _, _ = simulate(cand, syms(), tokens, pos)
                action, detail = "Delete", f"Deleted '{tok.text}'"
            elif cand.kind == "replace":
                edits.append({"kind": "replace", "offset": tok.offset, "length": tok.length,
                              "text": cand.term, "token": tok.text, "with": cand.term})
                rec["tokens_replaced"].append({"from": tok.text, "to": cand.term})
                _, tokens, _, _ = simulate(cand, syms(), tokens, pos)
                action, detail = "Replace", f"Replaced '{tok.text}' with {display(cand.term)}"
            else:
                skipped = tokens[pos:pos + cand.skip]
                for s in skipped:
                    edits.append({"kind": "skip", "offset": s.offset, "length": s.length, "token": s.text})
                popped = stack[len(stack) - cand.pop:] if cand.pop else []
                for sym, nd in popped:
                    nd["error"] = True
                    nd["label"] = (f"<missing-{MISSING_LABEL.get(sym, 'token')}>" if sym in nts
                                   else f"<missing {display(sym)}>")
                if skipped:
                    ((popped[-1][1] if popped else node) or root).setdefault("skipped", []).extend(s.text for s in skipped)
                if cand.pop:
                    del stack[len(stack) - cand.pop:]
                pos += cand.skip
                rec["tokens_deleted"] = [s.text for s in skipped]
                rec["sync_token"] = display(cand.term)
                action = "Panic-mode sync"
                detail = (f"Skipped {len(skipped)} token(s): {' '.join(s.text for s in skipped)}; " if skipped else "") \
                    + f"synchronized at {display(cand.term)}"
                if popped:
                    detail += f" (popped {', '.join(s for s, _ in popped)})"

            if dec["ambiguous"]:
                detail = "Ambiguous: " + detail + ". Alternatives are listed."
            if dec["fell_back"]:
                detail += f" (no valid {recovery.strategy} fix, fell back to panic mode)"
            tgt = tokens[pos]
            if cand.kind == "sync" and cand.term == ";" and tgt.type == ";" and pos + 1 < len(tokens):
                tgt = tokens[pos + 1]          # the ';' is consumed, parsing resumes after it
            hopeless = cand.kind == "sync" and cand.term == "$" and cand.skip > 0
            rec.update(action=action, detail=detail,
                       status="unrecoverable" if hopeless else ("recovered by panic mode" if cand.kind == "sync" else "recovered"),
                       resume={"line": tgt.line, "col": tgt.col, "token": tgt.text or "end of input"},
                       problem=_problem(info, cand, tok, prev, exp))
            errors.append(rec)
            trace.add(syms(), tokens, pos, f"Recovery: {detail}", "recovery")

            sig = (pos, len(stack), len(tokens))
            stuck = stuck + 1 if sig == last_progress else 0
            last_progress = sig
            if stuck > 3:                                   # progress guard
                if tokens[pos].type == "$":
                    aborted = True
                    break
                edits.append({"kind": "skip", "offset": tokens[pos].offset, "length": tokens[pos].length,
                              "token": tokens[pos].text})
                pos += 1
        else:
            aborted = True

        return {"errors": errors, "trace": trace.rows, "tree": root, "edits": edits,
                "tokens_final": tokens, "completed": not aborted,
                "recovered_source": apply_edits(source, edits)}


def _candidate_rows(dec, tokens, pos):
    out = []
    for r in dec["rows"]:
        c, ev = r["cand"], r["ev"]
        out.append({"key": c.key, "label": c.label(tokens, pos), "kind": c.kind, "cost": c.cost,
                    "valid": ev["valid"], "continuation": ev["continuation"],
                    "anomaly_score": None if r["anomaly"] is None else round(r["anomaly"], 5),
                    "rank_score": round(r["rank_score"], 5),
                    "prob": None if r["prob"] is None else round(r["prob"], 4),
                    "suggestion_only": c.suggestion_only,
                    "chosen": r is dec["chosen"]})
    return out


def _problem(info, cand, tok, prev, exp):
    prim = info["primary"]
    if cand.kind == "delete":
        return f"Unexpected '{tok.text}'"
    if cand.kind == "replace":
        return f"Wrong token '{tok.text}', expected {display(cand.term)}"
    if tok.type in ("id", "num") and prev is not None and prev.type in ("id", "num") \
            and (info["allowed"] & OPS):
        return f"Missing operator between '{prev.text}' and '{tok.text}'"
    if prim and prim <= {"id", "num", "("}:
        if cand.kind == "sync" and cand.skip:
            return "Malformed expression"
        base = "Missing operand"
        if prev is not None and prev.type in OPS | {"="}:
            base += f" after '{prev.text}'"
        return base
    if cand.kind == "insert":
        return f"Missing {display(cand.term)}"
    return f"Unexpected {display(tok.type) if tok.type in ('id', 'num', '$') else repr(tok.text)}"
