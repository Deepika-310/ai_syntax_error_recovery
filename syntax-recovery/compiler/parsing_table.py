"""LL(1) parsing table with synchronizing entries.

table[(A, t)] is either a production (tuple of symbols, () for epsilon) or the
string "synch". An entry that is not in the dict is an error entry.
"""
from .first_follow import analyze_grammar, first_of_seq

SYNCH = "synch"


class TableConflict(Exception):
    pass


class ParsingTable:
    def __init__(self, g):
        self.g = g
        self.first, self.follow, self.nullable = analyze_grammar(g)
        self.table = {}
        self.resolved = []      # conflicts settled by a %prefer line
        self._build()

    def _put(self, a, t, prod):
        key = (a, t)
        old = self.table.get(key)
        if old is None or old == SYNCH:
            self.table[key] = prod
            return
        if old == prod:
            return
        if (a, t) in self.g.prefer:
            keep = old if old else prod       # the non-empty production wins
            self.table[key] = keep
            self.resolved.append((a, t, [old, prod]))
            return
        raise TableConflict(f"LL(1) conflict at M[{a}, {t}]: {old} vs {prod}")

    def _build(self):
        g = self.g
        for a, prods in g.productions.items():
            for p in prods:
                f, all_null = first_of_seq(p, self.first, self.nullable)
                for t in f:
                    self._put(a, t, p)
                if all_null:
                    for t in self.follow[a]:
                        self._put(a, t, p)
        # Synchronizing entries: tokens in FOLLOW(A) that have no production.
        for a in g.nonterminals:
            for t in self.follow[a]:
                if (a, t) not in self.table:
                    self.table[(a, t)] = SYNCH

    def get(self, a, t):
        return self.table.get((a, t))

    def row_terminals(self, a):
        """Terminals with a real production for A."""
        return sorted(t for (n, t), v in self.table.items() if n == a and v != SYNCH)

    def as_json(self):
        terms = sorted(self.g.terminals | {"$"})
        rows = {}
        for a in self.g.productions:
            row = {}
            for t in terms:
                v = self.table.get((a, t))
                if v is None:
                    continue
                row[t] = "synch" if v == SYNCH else (" ".join(v) if v else "ε")
            rows[a] = row
        return {"terminals": terms, "rows": rows,
                "resolved": [{"nonterminal": a, "token": t,
                              "choices": [" ".join(c) if c else "ε" for c in cs]}
                             for a, t, cs in self.resolved]}
