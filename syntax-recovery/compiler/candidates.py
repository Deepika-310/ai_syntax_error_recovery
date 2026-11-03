"""Recovery candidate generation: insertion, deletion, replacement, synchronization."""
from dataclasses import dataclass

from .lexer import display
from .trace import virtual_token

SYNC_TOKENS = {";", "}", ")", "else"}
OPERAND_TERMS = {"id", "num"}          # never inserted automatically


@dataclass
class Candidate:
    kind: str                 # insert | delete | replace | sync
    term: str = None
    skip: int = 0             # sync: tokens skipped
    pop: int = 0              # sync: stack symbols popped
    cost: float = 1
    suggestion_only: bool = False

    @property
    def key(self):
        if self.kind in ("insert", "replace"):
            return f"{self.kind}:{self.term}"
        if self.kind == "sync":
            return f"sync:{self.skip}:{self.pop}"
        return "delete"

    def label(self, tokens=None, pos=0):
        cur = tokens[pos].text if tokens and tokens[pos].type != "$" else "end of input"
        if self.kind == "insert":
            return f"Insert {display(self.term)}"
        if self.kind == "delete":
            return f"Delete '{cur}'"
        if self.kind == "replace":
            return f"Replace '{cur}' with {display(self.term)}"
        if tokens and self.skip:
            return f"Skip {self.skip} token{'s' if self.skip != 1 else ''} to '{display(tokens[pos + self.skip].type)}'"
        return "Synchronize here"


def generate(table, stack_syms, tokens, pos, info):
    out = []
    cur = tokens[pos]
    allowed = sorted(t for t in info["allowed"] if t != "$")
    for t in allowed:
        out.append(Candidate("insert", t, suggestion_only=t in OPERAND_TERMS))
    if cur.type != "$":
        # Dropping or overwriting an identifier or number throws away the user's value,
        # so it costs one more than touching punctuation or an operator.
        drop = 2.2 if cur.type in OPERAND_TERMS else 1.2
        out.append(Candidate("delete", cost=drop))
        for t in allowed:
            if t != cur.type:
                out.append(Candidate("replace", t, cost=drop, suggestion_only=t in OPERAND_TERMS))
    sync = find_sync(stack_syms, tokens, pos, table.g.nonterminals)
    if sync:
        out.append(sync)
    return out


def find_sync(stack_syms, tokens, pos, nts):
    """Nearest input token that is a synchronization token and also sits on the stack.

    Cost is 1 + tokens skipped + terminals popped from the stack."""
    for k in range(len(tokens) - pos):
        t = tokens[pos + k].type
        if t in SYNC_TOKENS or t == "$":
            for d in range(len(stack_syms)):
                if stack_syms[-1 - d] == t:
                    # popped terminals are tokens we pretend were there, so they cost like insertions
                    missing = sum(1 for s in stack_syms[len(stack_syms) - d:] if s not in nts)
                    return Candidate("sync", t, skip=k, pop=d, cost=1 + k + missing)
    return None


def simulate(cand, stack_syms, tokens, pos):
    """Apply a candidate to copies of the stack and tokens. Returns (stack, tokens, pos, edit_index)."""
    stack = list(stack_syms)
    toks = list(tokens)
    if cand.kind == "insert":
        prev = toks[pos - 1] if pos > 0 else None
        toks.insert(pos, virtual_token(cand.term, toks[pos], prev))
    elif cand.kind == "delete":
        del toks[pos]
    elif cand.kind == "replace":
        old = toks[pos]
        v = virtual_token(cand.term, old, None)
        v.line, v.col, v.offset, v.length = old.line, old.col, old.offset, old.length
        v.inserted, v.replaced_from = False, old.text
        toks[pos] = v
    else:
        if cand.pop:
            del stack[len(stack) - cand.pop:]
        return stack, toks, pos + cand.skip, pos + cand.skip
    return stack, toks, pos, pos
