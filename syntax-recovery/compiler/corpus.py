"""Valid-program generator, hand-written program loader and error injector.

Everything is seeded so training and evaluation are reproducible.
"""
import glob
import os
import random

from .grammar import load_grammar
from .lexer import lex

HERE = os.path.dirname(os.path.abspath(__file__))
VALID_DIR = os.path.join(HERE, "..", "data", "valid")

NAMES = ["a", "b", "c", "i", "j", "n", "x", "y", "z", "sum", "total", "count", "result",
         "index", "value", "price", "qty", "temp", "limit", "step", "score", "max", "min", "avg"]
RELOPS = ["==", "!=", "<", ">", "<=", ">="]

# Weights make the generated programs look like programs: mostly assignments, short expressions.
STMT_WEIGHTS = {"Decl": 2.0, "AssignStmt": 4.0, "IfStmt": 1.5, "WhileStmt": 1.0, "PrintStmt": 2.0, "Block": 0.4}
CONTINUE = {"StmtList": 0.86, "ExprRest": 0.42, "TermRest": 0.28, "ElsePart": 0.35}
# '+' is more common than '-', and '*' more common than '/', as in ordinary code.
OP_WEIGHTS = {"ExprRest": [0.62, 0.38], "TermRest": [0.62, 0.38]}


class Generator:
    def __init__(self, rng, grammar=None, max_depth=4):
        self.g = grammar or load_grammar()
        self.rng, self.max_depth = rng, max_depth

    def derive(self, sym, depth, out):
        g, rng = self.g, self.rng
        if sym not in g.nonterminals:
            out.append(sym)
            return
        prods = g.productions[sym]
        deep = depth > self.max_depth
        if sym == "Stmt":
            names = [p[0] for p in prods]
            w = [STMT_WEIGHTS[n] * (0.15 if deep and n in ("IfStmt", "WhileStmt", "Block") else 1) for n in names]
            prod = rng.choices(prods, w)[0]
        elif sym == "Factor":
            w = [0.05 if deep and p[0] == "(" else {"id": .55, "num": .35, "(": .10}[p[0]] for p in prods]
            prod = rng.choices(prods, w)[0]
        elif sym in CONTINUE:
            p_more = CONTINUE[sym] * (0.3 if deep else 1)
            more = [p for p in prods if p]
            if rng.random() < p_more:
                prod = rng.choices(more, OP_WEIGHTS.get(sym, [1] * len(more)))[0]
            else:
                prod = ()
        elif sym == "RelOp":
            prod = rng.choice(prods)
        else:
            prod = rng.choice(prods)
        for s in prod:
            self.derive(s, depth + 1, out)

    def program(self):
        out = []
        self.derive("Program", 0, out)
        return concretize(out, self.rng)


def concretize(terms, rng):
    """Turn grammar terminals into real tokens (random names and numbers)."""
    out = []
    for t in terms:
        if t == "id":
            out.append(rng.choice(NAMES))
        elif t == "num":
            out.append(str(rng.choice([0, 1, 2, 3, 5, 10, 20, 100, rng.randint(1, 99)])) if rng.random() < .9
                       else f"{rng.randint(0, 9)}.{rng.randint(1, 9)}")
        else:
            out.append(t)
    return out


def pretty(words):
    """Format a token list as readable source."""
    lines, cur, indent, paren = [], "", 0, 0

    def flush():
        nonlocal cur
        if cur.strip():
            lines.append("    " * indent + cur.strip())
        cur = ""

    prev = ""
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else ""
        if w == "}":
            flush()
            indent = max(0, indent - 1)
            cur = "}" + (" " if nxt == "else" else "")
            if nxt != "else":
                flush()
        elif w in (";", ")", ","):
            cur = cur.rstrip() + w
            paren += -1 if w == ")" else 0
            if w == ";" and paren <= 0:
                flush()
        elif w == "(":
            paren += 1
            if prev == "print" or cur.endswith("("):
                cur += "("
            else:
                cur += (" " if cur and not cur.endswith(" ") else "") + "("
        else:
            if cur and not cur.endswith(("(", " ")):
                cur += " "
            cur += w
            if w == "{":
                flush()
                indent += 1
        prev = w
    flush()
    return "\n".join(lines) + "\n"


def generate_programs(n, seed=7):
    rng = random.Random(seed)
    gen = Generator(rng)
    seen, out = set(), []
    while len(out) < n:
        words = gen.program()
        if not 10 <= len(words) <= 110 or tuple(words) in seen:
            continue
        seen.add(tuple(words))
        out.append(pretty(words))
    return out


def load_hand_written():
    progs = []
    for path in sorted(glob.glob(os.path.join(VALID_DIR, "*.txt"))):
        with open(path, encoding="utf-8") as f:
            progs.append(f.read())
    return progs


def split_corpus(generated, hand, seed=11):
    """70 / 10 / 20 split into train, dev and test. Hand-written programs are spread across all three."""
    rng = random.Random(seed)
    allp = [("gen", p) for p in generated] + [("hand", p) for p in hand]
    rng.shuffle(allp)
    n = len(allp)
    a, b = int(n * 0.7), int(n * 0.8)
    return [p for _, p in allp[:a]], [p for _, p in allp[a:b]], [p for _, p in allp[b:]]


def token_types(source):
    toks, _ = lex(source)
    return [t.type for t in toks[:-1]]


# ---------------- error injection ----------------
INSERT_POOL = [";", ")", "(", "}", "{", "+", "-", "*", "/", "=", "id", "num", ",", "]", "==", "<", ">"]
MUTATIONS = ["delete", "insert", "replace", "duplicate", "swap"]


def mutate(source, rng, kind=None):
    """Apply one token-level mutation. Returns (mutated_source, description) or None."""
    toks, _ = lex(source)
    toks = toks[:-1]
    if len(toks) < 3:
        return None
    kind = kind or rng.choice(MUTATIONS)
    i = rng.randrange(len(toks))
    t = toks[i]
    operand = t.type in ("id", "num")
    if kind in ("delete", "replace") and operand:
        return None                             # cannot be restored without inventing a value
    def text_of(term):
        return {"id": rng.choice(NAMES), "num": str(rng.randint(1, 99))}.get(term, term)
    if kind == "delete":
        start, end = t.offset, t.end_offset
        while end < len(source) and source[end] in " \t":
            end += 1
        new = source[:start] + source[end:]
    elif kind == "insert":
        term = rng.choice(INSERT_POOL)
        new = source[:t.offset] + text_of(term) + " " + source[t.offset:]
    elif kind == "replace":
        term = rng.choice([x for x in INSERT_POOL if x != t.type])
        new = source[:t.offset] + text_of(term) + source[t.end_offset:]
    elif kind == "duplicate":
        new = source[:t.end_offset] + " " + t.text + source[t.end_offset:]
    else:
        if i + 1 >= len(toks):
            return None
        u = toks[i + 1]
        new = source[:t.offset] + u.text + source[t.end_offset:u.offset] + t.text + source[u.end_offset:]
    return new, kind


def same_tokens(a, b):
    """Do two sources have the same token sequence (ids and numbers compared by text)?"""
    ta, _ = lex(a)
    tb, _ = lex(b)
    return [(t.type, t.text) for t in ta] == [(t.type, t.text) for t in tb]
