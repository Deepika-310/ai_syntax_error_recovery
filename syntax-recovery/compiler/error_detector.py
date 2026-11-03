"""Error detection: what was found, what was expected, and where to report it."""
from .parsing_table import SYNCH
from .lexer import display

# Terminals that end a construct. If one of these is missing and the next token is
# on a later line, the error is reported at the end of the previous token.
TERMINATORS = {";", ")", "}", "]"}


def valid_next(table, stack_syms):
    """Terminals that can legally come next, and the 'primary' expected set.

    Walk down the stack, adding FIRST of each symbol until one cannot be empty.
    primary is the FIRST set of the first symbol that cannot be empty (a single
    terminal if it is one), which is what the parser actually requires next.
    """
    allowed, primary, seen_required = set(), set(), False
    for sym in reversed(stack_syms):
        if sym == "$":
            allowed.add("$")
            if not seen_required:
                primary, seen_required = {"$"}, True
            break
        if sym in table.g.nonterminals:
            f = set(table.first[sym])
            allowed |= f
            if sym in table.nullable:
                continue
            if not seen_required:
                primary, seen_required = f, True
            break
        allowed.add(sym)
        if not seen_required:
            primary, seen_required = {sym}, True
        break
    return allowed, primary


def find_error(table, stack_syms, tok):
    """Return None if the next step is legal, else a dict describing the error."""
    top = stack_syms[-1]
    if top in table.g.nonterminals:
        entry = table.get(top, tok.type)
        if entry is not None and entry != SYNCH:
            return None
        kind = "synch" if entry == SYNCH else "empty"
    else:
        if top == tok.type:
            return None
        kind = "mismatch"
    allowed, primary = valid_next(table, stack_syms)
    return {"kind": kind, "top": top, "allowed": allowed, "primary": primary}


def error_location(info, tokens, pos):
    """Line and column to report."""
    tok = tokens[pos]
    prev = tokens[pos - 1] if pos > 0 else None
    if prev is not None and (tok.line > prev.line or tok.type == "$") \
            and info["primary"] and info["primary"] <= TERMINATORS:
        return prev.line, prev.col + prev.length
    return tok.line, tok.col


def expected_text(terms):
    order = {"id": 0, "num": 1, "(": 2}
    return [display(t) for t in sorted(terms, key=lambda t: (order.get(t, 9), t))]
