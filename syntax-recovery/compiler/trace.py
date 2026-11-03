"""Records the parser trace and the per-error recovery log."""
from .lexer import Token


class Trace:
    def __init__(self):
        self.rows = []

    def add(self, stack_syms, tokens, pos, action, kind="step"):
        remaining = " ".join(t.text if t.type not in ("$",) else "$" for t in tokens[pos:])
        self.rows.append({
            "step": len(self.rows) + 1,
            "stack": " ".join(stack_syms),
            "input": remaining,
            "action": action,
            "kind": kind,                       # step | error | recovery | accept
            "line": tokens[pos].line, "col": tokens[pos].col,
        })


def virtual_token(term, near, prev):
    """A token created by recovery. Placed at the end of the previous token if there is one."""
    if prev is not None:
        line, col, off = prev.line, prev.col + prev.length, prev.end_offset
    else:
        line, col, off = near.line, near.col, near.offset
    return Token(term, term if term not in ("id", "num") else term, line, col, off, 0, inserted=True)
