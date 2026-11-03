"""Recovery evaluator: does a candidate let parsing continue?"""
from .parsing_table import SYNCH
from .candidates import simulate
from .error_detector import TERMINATORS


def dry_run(table, stack_syms, tokens, pos, kmax):
    """Run the parser on copies, stopping at the first error or after kmax matched tokens.

    Returns (consumed, accepted, stop) where stop is (stack top, token type) at the failure.
    """
    stack = list(stack_syms)
    nts = table.g.nonterminals
    consumed = 0
    while consumed < kmax:
        top, tok = stack[-1], tokens[pos]
        if top == "$":
            return consumed, tok.type == "$", (top, tok.type)
        if top in nts:
            entry = table.get(top, tok.type)
            if entry is None or entry == SYNCH:
                return consumed, False, (top, tok.type)
            stack.pop()
            stack.extend(reversed(entry))
        elif top == tok.type:
            stack.pop()
            pos += 1
            consumed += 1
        else:
            return consumed, False, (top, tok.type)
    return consumed, False, None


def evaluate(table, cand, stack_syms, tokens, pos, k_gate, kmax):
    """Fill in validity and continuation length for one candidate."""
    stack, toks, npos, edit_idx = simulate(cand, stack_syms, tokens, pos)
    consumed, accepted, stop = dry_run(table, stack, toks, npos, kmax)
    if cand.kind == "sync":
        valid = True
    else:
        # A candidate also passes if it only stops at a missing terminator or at the end of
        # input: that is a second, independent error, not a sign the edit was wrong.
        near_end = stop is not None and (stop[0] in TERMINATORS or stop[1] == "$")
        valid = accepted or consumed >= k_gate or (consumed >= 2 and near_end)
    return {
        "valid": valid,
        "consumed": consumed,
        "accepted": accepted,
        "continuation": kmax if accepted else consumed,
        "tokens_after": toks,
        "edit_index": edit_idx,
    }
