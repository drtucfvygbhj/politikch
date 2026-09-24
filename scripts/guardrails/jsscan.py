"""Minimal JavaScript scanner for the guardrail checks (stdlib only).

Finds every template literal and the `${...}` expressions inside it, skipping
strings, comments and regex literals, so check.py can tell which values are
interpolated into HTML-building templates (GUARDRAILS.md SEC-01).
"""
import re

_REGEX_PREV = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_KEYWORDS = ("return", "typeof", "case", "do", "else", "in", "of", "void", "yield", "await")


def _regex_allowed(src, i):
    j = i - 1
    while j >= 0 and src[j] in " \t\r\n":
        j -= 1
    if j < 0:
        return True
    if src[j] in _REGEX_PREV:
        return True
    m = re.search(r"([A-Za-z_$][\w$]*)$", src[:j + 1])
    return bool(m and m.group(1) in _REGEX_KEYWORDS)


def templates(src):
    """Yield (line, static_text, [expr, ...]) for every template literal."""
    out = []
    i, n = 0, len(src)

    def skip_string(i, q):
        i += 1
        while i < n and src[i] != q:
            i += 2 if src[i] == "\\" else 1
        return i + 1

    def skip_regex(i):
        i += 1
        in_class = False
        while i < n:
            c = src[i]
            if c == "\\":
                i += 2
                continue
            if c == "[":
                in_class = True
            elif c == "]":
                in_class = False
            elif c == "/" and not in_class:
                i += 1
                while i < n and (src[i].isalnum() or src[i] in "_$"):
                    i += 1
                return i
            elif c == "\n":
                return i
            i += 1
        return i

    def read_template(i):
        """i at the opening backtick. Returns index after the closing one."""
        start_line = src.count("\n", 0, i) + 1
        i += 1
        static, exprs = [], []
        while i < n:
            c = src[i]
            if c == "\\":
                static.append(src[i:i + 2])
                i += 2
            elif c == "`":
                out.append((start_line, "".join(static), exprs))
                return i + 1
            elif c == "$" and i + 1 < n and src[i + 1] == "{":
                j = scan_code(i + 2, stop_on_brace=True)
                exprs.append(src[i + 2:j])
                static.append("\x00")
                i = j + 1
            else:
                static.append(c)
                i += 1
        return i

    def scan_code(i, stop_on_brace=False):
        depth = 0
        while i < n:
            c = src[i]
            if c in "'\"":
                i = skip_string(i, c)
            elif c == "`":
                i = read_template(i)
            elif src.startswith("//", i):
                i = src.find("\n", i)
                i = n if i < 0 else i
            elif src.startswith("/*", i):
                i = src.find("*/", i + 2)
                i = n if i < 0 else i + 2
            elif c == "/" and _regex_allowed(src, i):
                i = skip_regex(i)
            elif c == "{":
                depth += 1
                i += 1
            elif c == "}":
                if stop_on_brace and depth == 0:
                    return i
                depth -= 1
                i += 1
            else:
                i += 1
        return i

    scan_code(0)
    return out


def whole_call(expr, names):
    """True if `expr` is exactly one call to one of `names`, e.g. escapeAttr(x)."""
    expr = expr.strip()
    m = re.match(r"(%s)\(" % "|".join(map(re.escape, names)), expr)
    if not m:
        return False
    depth, i, q = 0, m.end() - 1, None
    while i < len(expr):
        c = expr[i]
        if q:
            if c == "\\":
                i += 2
                continue
            if c == q:
                q = None
        elif c in "'\"`":
            q = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i == len(expr) - 1
        i += 1
    return False
