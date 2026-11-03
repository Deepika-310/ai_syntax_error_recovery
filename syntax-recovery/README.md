# Syntax Error Recovery

A web tool that parses a small C-like language, reports syntax errors, and shows how recovery proceeds. A custom LL(1) parser generates possible repairs; a trained Isolation Forest ranks repairs that pass the parser's grammar-validity gate.

## Run it

```text
pip install -r requirements.txt
python -m compiler.train
python app.py
```

Open `http://127.0.0.1:5000`. Run the tests with `python -m unittest discover -s tests`. Evaluate against unseen synthetic errors with `python -m compiler.evaluation`.

The training command must be run once after installing dependencies. It writes the model to `data/isolation_forest.joblib`. The scikit-learn version is pinned to match the checked-in model artifact. If the model file is absent, the site reports that the model is untrained and recovery uses the edit-cost baseline.

## Language and parser

The controlled language supports `int` and `float` declarations, assignment, `if` / `else`, `while`, `print(expr);`, blocks, identifiers, numbers, arithmetic and relational operators, parentheses, and `//` comments. Its grammar is in `grammar/grammar.txt`. FIRST and FOLLOW sets, the LL(1) parsing table, parser trace, token stream, recovered source, and parse tree are exposed in the website.

## Recovery workflow

1. The lexer produces tokens and the LL(1) parser detects an error.
2. The recovery engine generates insertion, deletion, replacement, and synchronization candidates.
3. Each candidate is simulated and checked by the grammar-based continuation gate. Invalid candidates and repairs that would invent an identifier or number are not applied automatically.
4. The Isolation Forest scores the five-token window around each candidate's resulting token position. It is trained only on local token windows from valid programs; its anomaly score is combined with a small edit-cost adjustment to rank candidates.
5. The top grammar-valid candidate is applied unless its relative score is ambiguous. Ambiguous cases use panic-mode synchronization and are shown for user review.

The UI reports the anomaly score, relative candidate confidence, grammar validation, final action, and parser continuation. Relative confidence is normalized across the candidates for one error; it is not a calibrated probability. A small edit-cost adjustment favors shorter fixes when anomaly scores are close, while the grammar-validity gate remains authoritative.

## Training and evaluation workflow

`python -m compiler.train` deterministically generates valid programs, combines them with the hand-written examples under `data/valid/`, creates train/validation/test splits, and fits the Isolation Forest using only the training split. The model learns five-position one-hot token windows, with identifiers and numbers abstracted to token classes.

`python -m compiler.evaluation` injects token errors into held-out test programs and compares the Isolation Forest against an edit-cost/continuation baseline. It reports automatic restoration, top-ranked accuracy, ambiguity, incorrect automatic recovery, cascading errors, and per-error-kind results. The website's Model and Evaluation pages display the training metadata and latest evaluation.

The model assists recovery but does not generate source code. If the intended repair is uncertain, it reports ambiguity or synchronizes rather than inventing a value.
