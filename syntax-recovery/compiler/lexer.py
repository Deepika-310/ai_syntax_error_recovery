"""Lexical analyzer. Produces tokens with line, column and source offsets."""
from dataclasses import dataclass, field

KEYWORDS = {"int", "float", "if", "else", "while", "print"}
TWO_CHAR = {"==", "!=", "<=", ">="}
ONE_CHAR = set("+-*/=<>(){};[],")

# Names shown to the user for each terminal.
DISPLAY = {
    "id": "Identifier", "num": "Number", "$": "end of input",
    "int": "int", "float": "float", "if": "if", "else": "else",
    "while": "while", "print": "print",
}


def display(term):
    return DISPLAY.get(term, term)


@dataclass
class Token:
    type: str            # terminal name used by the grammar
    text: str
    line: int
    col: int             # 1-based
    offset: int          # index into the source string
    length: int
    inserted: bool = False       # created by recovery
    replaced_from: str = None    # original text if created by replacement

    @property
    def end_offset(self):
        return self.offset + self.length

    def short(self):
        if self.type == "id":
            return f"<id,{self.text}>"
        if self.type == "num":
            return f"<num,{self.text}>"
        if self.type == "$":
            return "$"
        return f"<{self.text}>"


def lex(source):
    """Return (tokens, lexical_errors). tokens always ends with a '$' token."""
    tokens, errors = [], []
    i, line, col, n = 0, 1, 1, len(source)
    while i < n:
        c = source[i]
        if c == "\n":
            i += 1; line += 1; col = 1
            continue
        if c in " \t\r":
            i += 1; col += 1
            continue
        if source.startswith("//", i):
            while i < n and source[i] != "\n":
                i += 1; col += 1
            continue
        start, scol = i, col
        if c.isalpha() or c == "_":
            while i < n and (source[i].isalnum() or source[i] == "_"):
                i += 1; col += 1
            text = source[start:i]
            tokens.append(Token(text if text in KEYWORDS else "id", text, line, scol, start, i - start))
        elif c.isdigit():
            while i < n and source[i].isdigit():
                i += 1; col += 1
            if i + 1 < n and source[i] == "." and source[i + 1].isdigit():
                i += 1; col += 1
                while i < n and source[i].isdigit():
                    i += 1; col += 1
            tokens.append(Token("num", source[start:i], line, scol, start, i - start))
        elif source[i:i + 2] in TWO_CHAR:
            i += 2; col += 2
            tokens.append(Token(source[start:i], source[start:i], line, scol, start, 2))
        elif c in ONE_CHAR:
            i += 1; col += 1
            tokens.append(Token(c, c, line, scol, start, 1))
        else:
            errors.append({"line": line, "col": col, "char": c,
                           "message": f"Illegal character '{c}'"})
            i += 1; col += 1
    tokens.append(Token("$", "", line, col, n, 0))
    return tokens, errors
