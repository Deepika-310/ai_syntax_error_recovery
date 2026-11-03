"""Entry point used by the web app, the tests and the evaluation scripts."""
import time

from .grammar import load_grammar
from .parsing_table import ParsingTable
from .lexer import lex
from .parser import Parser
from .recovery import Recovery, STRATEGIES
from .metrics import run_metrics

_table = None
_model = None
_model_loaded = False

MAX_SOURCE_CHARS = 20000


def get_table():
    global _table
    if _table is None:
        _table = ParsingTable(load_grammar())
    return _table


def get_model():
    """The trained model, or None until the Isolation Forest has been trained."""
    global _model, _model_loaded
    if not _model_loaded:
        _model_loaded = True
        try:
            from .model import load_model
            _model = load_model()
        except FileNotFoundError:
            _model = None
    return _model


def reset_model_cache():
    global _model, _model_loaded
    _model, _model_loaded = None, False


def token_rows(tokens):
    return [{"lexeme": t.text or "$", "token": t.type.upper() if t.type in ("id", "num") else
             ("END" if t.type == "$" else t.type), "line": t.line, "col": t.col, "text": t.short()}
            for t in tokens]


def analyze(source, strategy="automatic", forced=None, params=None, use_model=True, recover=True):
    if len(source) > MAX_SOURCE_CHARS:
        raise ValueError(f"Source is longer than {MAX_SOURCE_CHARS} characters.")
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy '{strategy}'.")
    t0 = time.perf_counter()
    tokens, lex_errors = lex(source)
    table = get_table()
    recovery = None
    if recover:
        recovery = Recovery(table, get_model() if use_model else None, strategy, params)
    result = Parser(table).parse(source, tokens, recovery, forced)
    elapsed = (time.perf_counter() - t0) * 1000
    result["tokens"] = token_rows(tokens)
    result["lexical_errors"] = lex_errors
    result["strategy"] = strategy
    result["metrics"] = run_metrics(result, elapsed)
    result["summary"] = {k: result["metrics"][k] for k in
                         ("detected", "recovered", "panic_recoveries", "unrecoverable")}
    del result["tokens_final"]
    return result
