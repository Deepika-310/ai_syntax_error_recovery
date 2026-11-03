import os, random, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from compiler.analyze import analyze, get_model
from compiler.grammar import parse_grammar_text
from compiler.first_follow import analyze_grammar
from compiler.parsing_table import ParsingTable, TableConflict
from compiler.lexer import lex
from compiler.evaluation import load_testcases, check_case
from compiler.corpus import generate_programs, load_hand_written, token_types
from compiler.model import abstract

VALID = "int a;\nint b;\na = 10;\nb = a + 5;\nif (b > 10) {\nprint(b);\n}\n"

SMALL = """
E  -> T Ep
Ep -> + T Ep | eps
T  -> F Tp
Tp -> * F Tp | eps
F  -> ( E ) | id
"""


class LexerTests(unittest.TestCase):
    def test_positions(self):
        toks, errs = lex("int a;\n  a = 10;")
        self.assertEqual([(t.text, t.line, t.col) for t in toks[:4]],
                         [("int", 1, 1), ("a", 1, 5), (";", 1, 6), ("a", 2, 3)])
        self.assertEqual(toks[-1].type, "$")
        self.assertFalse(errs)

    def test_illegal_character_is_lexical_error(self):
        toks, errs = lex("a = 5 # 3;")
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0]["char"], "#")

    def test_two_char_operators(self):
        self.assertEqual([t.type for t in lex("a <= b == c != d >= e")[0][:-1]],
                         ["id", "<=", "id", "==", "id", "!=", "id", ">=", "id"])


class GrammarTests(unittest.TestCase):
    def test_first_follow_known_grammar(self):
        g = parse_grammar_text(SMALL)
        first, follow, nullable = analyze_grammar(g)
        self.assertEqual(first["E"], {"(", "id"})
        self.assertEqual(first["Ep"], {"+"})
        self.assertEqual(nullable, {"Ep", "Tp"})
        self.assertEqual(follow["E"], {"$", ")"})
        self.assertEqual(follow["T"], {"+", "$", ")"})
        self.assertEqual(follow["F"], {"*", "+", "$", ")"})

    def test_table_has_synch_entries(self):
        t = ParsingTable(parse_grammar_text(SMALL))
        self.assertEqual(t.get("F", "+"), "synch")
        self.assertEqual(t.get("F", "id"), ("id",))

    def test_conflict_is_reported(self):
        with self.assertRaises(TableConflict):
            ParsingTable(parse_grammar_text("S -> a | a b"))

    def test_real_grammar_dangling_else_resolved(self):
        from compiler.analyze import get_table
        t = get_table()
        self.assertEqual(t.get("ElsePart", "else"), ("else", "Stmt"))
        self.assertTrue(t.resolved)


class ParserTests(unittest.TestCase):
    def test_valid_program_has_no_errors(self):
        r = analyze(VALID)
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["trace"][-1]["kind"], "accept")
        self.assertEqual(r["recovered_source"], VALID)

    def test_hand_written_programs_are_valid(self):
        for p in load_hand_written():
            self.assertEqual(analyze(p)["errors"], [], p)

    def test_generated_programs_are_valid(self):
        for p in generate_programs(200, seed=3):
            self.assertEqual(analyze(p, recover=False)["errors"], [], p)

    def test_plain_parser_stops_at_first_error(self):
        r = analyze("int a\nint b\n", recover=False)
        self.assertEqual(len(r["errors"]), 1)
        self.assertFalse(r["completed"])


class AcceptanceTests(unittest.TestCase):
    def run_case(self, src):
        return analyze(src)

    def test_stored_programs(self):
        for case in load_testcases():
            res = check_case(case)
            self.assertTrue(res["passed"], f"{case['name']}: {res['problems']}")
        self.assertGreaterEqual(len(load_testcases()), 15)

    def test_missing_semicolon_reports_line_1(self):
        e = self.run_case("int x\nx = 10;\n")["errors"][0]
        self.assertEqual((e["line"], e["expected"]), (1, [";"]))

    def test_extra_operator_expected_set(self):
        e = self.run_case("x = 10 + * 20;\n")["errors"][0]
        self.assertEqual((e["unexpected"], e["expected"]), ("*", ["Identifier", "Number", "("]))

    def test_no_invented_operand(self):
        r = self.run_case("x = a + ;\n")
        self.assertEqual(r["recovered_source"], "x = a + ;\n")
        self.assertEqual(r["errors"][0]["action"], "Panic-mode sync")

    def test_panic_mode_skips_listed_tokens(self):
        r = self.run_case("int a;\na = + * 10 abc xyz ;\nint b;\nb = 20;\n")
        e = r["errors"][0]
        self.assertEqual(len(r["errors"]), 1)
        self.assertEqual(e["tokens_deleted"], ["+", "*", "10", "abc", "xyz"])
        self.assertEqual(e["resume"]["line"], 3)

    def test_four_errors_all_recovered(self):
        r = self.run_case("int a\nint b;\na = 10 + ;\nif (a > b {\nprint(a)\n}\n")
        self.assertEqual(r["summary"]["detected"], 4)
        self.assertEqual(r["summary"]["recovered"], 4)
        self.assertEqual(r["summary"]["unrecoverable"], 0)

    def test_ambiguous_operator_lists_alternatives(self):
        e = self.run_case("a = 10 20;\n")["errors"][0]
        self.assertTrue(e["ambiguous"])
        ops = {c["key"]: c["prob"] for c in e["candidates"] if c["key"].startswith("insert:") and c["prob"]}
        self.assertEqual(set(ops), {"insert:+", "insert:-", "insert:*", "insert:/"})
        self.assertTrue(all(c["prob"] is None or 0 <= c["prob"] <= 1 for c in e["candidates"]))
        self.assertAlmostEqual(sum(c["prob"] for c in e["candidates"] if c["prob"] is not None), 1.0, places=2)
        self.assertTrue(all(c["rank_score"] is not None for c in e["candidates"]))

    def test_isolation_forest_does_not_guess_ambiguous_relational_operator(self):
        result = self.run_case("if (a = 10) {\nprint(a);\n}\n")
        error = result["errors"][0]
        self.assertTrue(error["ambiguous"])
        self.assertEqual(error["action"], "Panic-mode sync")
        self.assertEqual(result["recovered_source"], "if (a = 10) {\nprint(a);\n}\n")
        self.assertTrue(all(c["anomaly_score"] is not None for c in error["candidates"]))

    def test_user_can_apply_an_alternative(self):
        r = analyze("total = price qty;\n", forced={1: "insert:+"})
        self.assertEqual(r["recovered_source"], "total = price + qty;\n")

    def test_strategy_fallback_is_logged(self):
        r = analyze("x = a + ;\n", strategy="insertion")
        self.assertTrue(r["errors"][0]["fell_back"])


class RobustnessTests(unittest.TestCase):
    def test_terminates_on_random_token_sequences(self):
        rng = random.Random(5)
        pool = ["int", "float", "if", "else", "while", "print", "a", "b", "10", "(", ")", "{", "}",
                ";", "+", "-", "*", "/", "=", "==", "<", "]", ",", "["]
        for _ in range(500):
            src = " ".join(rng.choice(pool) for _ in range(rng.randint(1, 25)))
            r = analyze(src)
            self.assertIn("errors", r)

    def test_deterministic(self):
        src = "int a\nint b\na = 10 + ;\nif (a > b {\nprint(a)\n}\n"
        a, b = analyze(src), analyze(src)
        a["metrics"].pop("response_ms"); b["metrics"].pop("response_ms")
        self.assertEqual(a, b)

    def test_every_strategy_runs(self):
        for s in ("automatic", "panic", "insertion", "deletion", "replacement", "phrase"):
            self.assertTrue(analyze("int a\nx = 10 + * 20;\n", strategy=s)["completed"])

    def test_oversize_input_rejected(self):
        with self.assertRaises(ValueError):
            analyze("a" * 30000)


class ModelTests(unittest.TestCase):
    def test_isolation_forest_model_has_training_metadata_and_scores(self):
        m = get_model()
        self.assertIsNotNone(m)
        summary = m.summary()
        self.assertEqual(summary["algorithm"], "Isolation Forest")
        self.assertGreater(summary["training_windows"], 0)
        self.assertGreater(summary["features"], 0)
        score = m.anomaly_score(["id", "=", "num", ";", "$"], 2)
        self.assertIsInstance(score, float)

    def test_abstraction(self):
        self.assertEqual([abstract(t) for t in ("id", "num", "if", ";", "$")], ["ID", "NUM", "if", ";", "<EOS>"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        import app as A
        self.c = A.app.test_client()

    def test_analyze_endpoint(self):
        r = self.c.post("/api/analyze", json={"source": "int x\nx = 10;\n"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["recovered_source"], "int x;\nx = 10;\n")

    def test_bad_requests(self):
        self.assertEqual(self.c.post("/api/analyze", json={"source": 5}).status_code, 400)
        self.assertEqual(self.c.post("/api/analyze", json={"source": "x", "strategy": "zzz"}).status_code, 400)
        self.assertEqual(self.c.post("/api/analyze", data="nope").status_code, 400)
        self.assertEqual(self.c.get("/api/nothing").status_code, 404)

    def test_pages_and_data_endpoints(self):
        for u in ("/", "/grammar", "/model", "/evaluation", "/api/grammar", "/api/model",
                  "/api/testcases", "/api/examples", "/api/strategies", "/api/evaluation"):
            self.assertEqual(self.c.get(u).status_code, 200, u)
        self.assertEqual(self.c.get("/api/model").get_json()["algorithm"], "Isolation Forest")


if __name__ == "__main__":
    unittest.main()
