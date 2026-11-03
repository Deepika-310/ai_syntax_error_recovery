"""Loads grammar/grammar.txt."""
import os

EPS = "eps"
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PATH = os.path.join(HERE, "..", "grammar", "grammar.txt")


class Grammar:
    def __init__(self, productions, start, prefer):
        self.productions = productions      # {A: [tuple(symbols), ...]}, [] means epsilon
        self.start = start
        self.prefer = prefer                # {(A, terminal)}: resolve conflict to non-empty rule
        self.nonterminals = set(productions)
        self.terminals = {s for prods in productions.values() for p in prods
                          for s in p if s not in productions}

    def rules(self):
        for a, prods in self.productions.items():
            for p in prods:
                yield a, p


def parse_grammar_text(text):
    productions, prefer, start = {}, set(), None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("%prefer"):
            _, a, t = line.split()
            prefer.add((a, t))
            continue
        head, body = line.split("->", 1)
        head = head.strip()
        start = start or head
        alts = []
        for alt in body.split("|"):
            syms = tuple(alt.split())
            alts.append(() if syms in ((EPS,), ()) else syms)
        productions.setdefault(head, []).extend(alts)
    return Grammar(productions, start, prefer)


def load_grammar(path=DEFAULT_PATH):
    with open(path, encoding="utf-8") as f:
        return parse_grammar_text(f.read())


def prod_str(a, p):
    return f"{a} → {' '.join(p) if p else 'ε'}"
