"""FIRST, FOLLOW and nullable sets, computed from the grammar."""
from .grammar import EPS


def compute_nullable(g):
    nullable, changed = set(), True
    while changed:
        changed = False
        for a, p in g.rules():
            if a not in nullable and all(s in nullable for s in p):
                nullable.add(a)
                changed = True
    return nullable


def first_of_seq(seq, first, nullable):
    """FIRST of a symbol sequence. Terminals are their own FIRST."""
    out = set()
    for s in seq:
        out |= first[s] if s in first else {s}
        if s not in nullable:
            return out, False
    return out, True


def compute_first(g, nullable):
    first = {a: set() for a in g.nonterminals}
    changed = True
    while changed:
        changed = False
        for a, p in g.rules():
            f, _ = first_of_seq(p, first, nullable)
            if not f <= first[a]:
                first[a] |= f
                changed = True
    return first


def compute_follow(g, first, nullable):
    follow = {a: set() for a in g.nonterminals}
    follow[g.start].add("$")
    changed = True
    while changed:
        changed = False
        for a, p in g.rules():
            for i, s in enumerate(p):
                if s not in g.nonterminals:
                    continue
                f, all_null = first_of_seq(p[i + 1:], first, nullable)
                new = set(f)
                if all_null:
                    new |= follow[a]
                if not new <= follow[s]:
                    follow[s] |= new
                    changed = True
    return follow


def analyze_grammar(g):
    nullable = compute_nullable(g)
    first = compute_first(g, nullable)
    follow = compute_follow(g, first, nullable)
    return first, follow, nullable
