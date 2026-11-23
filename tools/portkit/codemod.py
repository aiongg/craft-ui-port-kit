"""Codemod recipes over rustc's JSON diagnostics, for tools/codemod.

Each recipe turns one diagnostic into edits at rustc's spans, or declines it with a reason. Edits are character
ranges in a file of the tree; a diagnostic's edits are taken all together or not at all. Structure (the enclosing
fn, its parameter list, statement starts) comes from a masked copy of each file: comments, strings and character
literals blanked, offsets kept, so bracket matching never sees their contents.
"""
from __future__ import annotations

import difflib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

RECIPES = ("E0061", "E0609", "E0615", "E0502")


class Decline(Exception):
    """A recipe saw the diagnostic but cannot fix this site; the message says why."""


# ---------------------------------------------------------------- diagnostics


@dataclass
class Span:
    file: str
    start: int  # byte offsets into the file, as rustc gives them
    end: int
    line: int
    col: int
    primary: bool
    label: str
    replacement: str | None
    macro: bool


def _span(s: dict) -> Span:
    return Span(s["file_name"], s["byte_start"], s["byte_end"], s["line_start"], s["column_start"], s["is_primary"],
                s.get("label") or "", s.get("suggested_replacement"), s.get("expansion") is not None)


@dataclass
class Diag:
    code: str
    message: str
    spans: list[Span]
    children: list[tuple[str, list[Span]]]  # (message, spans) of notes and help

    @property
    def primary(self) -> Span:
        return next((s for s in self.spans if s.primary), self.spans[0])

    def where(self) -> str:
        p = self.primary
        return f"{p.file}:{p.line}:{p.col}"

    def error_line(self) -> str:
        """The line compile-gate's `--message-format short` logs hold for this error."""
        code = "" if self.code == "no code" else f"[{self.code}]"
        return f"{self.where()}: error{code}: {self.message}"

    def help(self, prefix: str) -> Span | None:
        """The first suggestion span of a child message starting with prefix."""
        for msg, spans in self.children:
            if msg.startswith(prefix):
                for s in spans:
                    if s.replacement is not None:
                        return s
        return None


def parse(lines) -> list[Diag]:
    """Errors with a position from cargo's JSON stream (or plain rustc JSON), in order, each once."""
    out, seen = [], set()
    for line in lines:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        m = d.get("message") if d.get("reason") == "compiler-message" else d
        if not isinstance(m, dict) or m.get("level") != "error" or not m.get("spans"):
            continue
        diag = Diag((m.get("code") or {}).get("code") or "no code", m.get("message", ""),
                    [_span(s) for s in m["spans"]],
                    [(c.get("message", ""), [_span(s) for s in c.get("spans", [])]) for c in m.get("children", [])])
        p = diag.primary
        key = (diag.code, diag.message, p.file, p.start, p.end)
        if key not in seen:
            seen.add(key)
            out.append(diag)
    return out


# ---------------------------------------------------------------- source files

RAW_STR = re.compile(r'b?r(#*)"')
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def mask(t: str) -> str:
    """t with comments, string and char literals turned into spaces (newlines kept); lifetimes stay."""
    out = list(t)
    n = len(t)

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    i = 0
    while i < n:
        c = t[i]
        if t.startswith("//", i):
            j = t.find("\n", i)
            j = n if j < 0 else j
        elif t.startswith("/*", i):
            depth, j = 1, i + 2
            while j < n and depth:
                if t.startswith("/*", j):
                    depth, j = depth + 1, j + 2
                elif t.startswith("*/", j):
                    depth, j = depth - 1, j + 2
                else:
                    j += 1
        elif c in "rb" and (m := RAW_STR.match(t, i)) and not (i and (t[i - 1].isalnum() or t[i - 1] == "_")):
            end = t.find('"' + m.group(1), m.end())
            j = n if end < 0 else end + 1 + len(m.group(1))
        elif c == '"':
            j = i + 1
            while j < n and t[j] != '"':
                j += 2 if t[j] == "\\" else 1
            j += 1
        elif c == "'" and i + 1 < n and t[i + 1] == "\\":
            end = t.find("'", i + 3)
            j = n if end < 0 else end + 1
        elif c == "'" and i + 2 < n and t[i + 2] == "'":
            j = i + 3
        else:
            i += 1
            continue
        blank(i, j)
        i = j
    return "".join(out)


class Source:
    def __init__(self, path: Path):
        raw = path.read_bytes()
        self.text = raw.decode("utf-8")
        self.masked = mask(self.text)
        self._map = None
        if len(raw) != len(self.text):
            self._map = [i for i, ch in enumerate(self.text) for _ in ch.encode()] + [len(self.text)]

    def c(self, byte: int) -> int:
        """The character offset of a byte offset."""
        return byte if self._map is None else self._map[byte]


OPEN, CLOSE = "([{", ")]}"


def match_close(m: str, i: int) -> int:
    depth = 0
    for j in range(i, len(m)):
        if m[j] in OPEN:
            depth += 1
        elif m[j] in CLOSE:
            depth -= 1
            if depth == 0:
                return j
    return -1


def match_open(m: str, i: int) -> int:
    depth = 0
    for j in range(i, -1, -1):
        if m[j] in CLOSE:
            depth += 1
        elif m[j] in OPEN:
            depth -= 1
            if depth == 0:
                return j
    return -1


def top_level_segments(m: str, a: int, b: int, angles: bool) -> list[tuple[int, int]]:
    """(start, end) of the comma-separated parts of m[a:b] at bracket depth 0 (and angle depth 0 with angles)."""
    parts, depth, start, j = [], 0, a, a
    while j < b:
        ch = m[j]
        if ch in OPEN or (angles and ch == "<"):
            depth += 1
        elif ch in CLOSE or (angles and ch == ">" and m[j - 1] != "-"):
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append((start, j))
            start = j + 1
        j += 1
    parts.append((start, b))
    return parts


@dataclass
class Fn:
    name: str
    kw: int        # offset of `fn`
    p_open: int    # its parameter list's parentheses
    p_close: int
    b_open: int    # its body's braces
    b_close: int


def enclosing_fn(src: Source, pos: int) -> Fn | None:
    """The innermost fn whose body holds pos."""
    m = src.masked
    for f in reversed(list(re.finditer(r"\bfn\s+([A-Za-z_]\w*)", m[:pos]))):
        j = f.end()
        while j < len(m) and m[j].isspace():
            j += 1
        if j < len(m) and m[j] == "<":
            depth = 0
            while j < len(m):
                if m[j] == "<":
                    depth += 1
                elif m[j] == ">" and m[j - 1] != "-":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
        p_open = m.find("(", j)
        p_close = match_close(m, p_open) if p_open >= 0 else -1
        if p_close < 0:
            continue
        body = re.compile(r"[{;]").search(m, p_close)
        if not body or body.group() == ";":
            continue
        b_close = match_close(m, body.start())
        if body.start() < pos < b_close:
            return Fn(f.group(1), f.start(), p_open, p_close, body.start(), b_close)
    return None


def trait_bound(src: Source, fn: Fn) -> str | None:
    """'trait' or 'impl' when fn sits in a trait or a trait impl, whose signature the trait fixes."""
    m = src.masked
    for k in reversed(list(re.finditer(r"\b(impl|trait)\b", m[:fn.kw]))):
        o = m.find("{", k.end())
        if 0 <= o < fn.kw and match_close(m, o) > fn.kw:
            if k.group(1) == "trait":
                return "trait"
            return "impl" if re.search(r"\bfor\b(?!\s*<)", m[k.end():o]) else None
    return None


def is_test(src: Source, fn: Fn) -> bool:
    head = src.masked[:fn.kw]
    cut = max(head.rfind(";"), head.rfind("}"), head.rfind("{"))
    return re.search(r"#\[\s*(\w+::)*test\b", head[cut + 1:]) is not None


def norm_type(t: str) -> str:
    """A type as rustc prints it, without paths and lifetimes: `&mut craft::Ctx<'_>` -> `&mut Ctx`."""
    t = re.sub(r"\b\w+::", "", t)
    t = re.sub(r"'\w+\s*,?\s*", "", t)
    t = re.sub(r"<\s*>", "", t)
    return re.sub(r"\s+", " ", t).replace("& ", "&").strip()


def type_name(t: str) -> str:
    """The bare type name of a receiver type: `&mut craft::View<T>` -> `View`."""
    t = re.sub(r"<.*>", "", t)
    t = re.sub(r"^(&\s*('\w+\s+)?(mut\s+)?|dyn\s+)+", "", t.strip())
    return t.split("::")[-1].strip()


# ---------------------------------------------------------------- plan


@dataclass(frozen=True)
class Edit:
    file: str
    start: int  # character offsets
    end: int
    text: str


@dataclass
class Mapping:
    """The map file: [[argument]] rows (E0061), [fields] (E0609), [methods] (E0615 write sites)."""
    arguments: list[dict] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)
    methods: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def load(cls, data: dict) -> "Mapping":
        args = data.get("argument", [])
        for a in args:
            if not {"type", "expr"} <= a.keys():
                raise ValueError(f"[[argument]] needs type and expr: {a}")
            if a.get("position", "last") not in ("first", "last"):
                raise ValueError(f"[[argument]] position is first or last: {a}")
            if "param" in a and not re.match(r"\s*(mut\s+)?[A-Za-z_]\w*\s*:", a["param"]):
                raise ValueError(f"[[argument]] param is `name: Type`: {a}")
        return cls(args, dict(data.get("fields", {})), dict(data.get("methods", {})))

    def argument(self, placeholder: str) -> dict | None:
        want = norm_type(placeholder)
        return next((a for a in self.arguments if norm_type(a["type"]) == want), None)

    def lookup(self, table: dict, typ: str, name: str):
        return table.get(f"{type_name(typ)}.{name}", table.get(f"*.{name}"))


def param_name(arg: dict) -> str:
    return re.match(r"\s*(?:mut\s+)?([A-Za-z_]\w*)", arg["param"]).group(1)


class Planner:
    def __init__(self, tree: Path, mapping: Mapping):
        self.tree = tree.resolve()
        self.mapping = mapping
        self._src: dict[str, Source] = {}

    def source(self, file: str) -> Source:
        if file not in self._src:
            p = (self.tree / file).resolve()
            if not p.is_relative_to(self.tree) or not p.is_file():
                raise Decline("file outside the tree")
            self._src[file] = Source(p)
        return self._src[file]

    def at(self, span: Span) -> tuple[Source, int, int]:
        if span.macro:
            raise Decline("inside a macro expansion")
        src = self.source(span.file)
        return src, src.c(span.start), src.c(span.end)

    # ---- E0061 and its cascade

    def e0061(self, d: Diag) -> list[Edit]:
        s = d.help("provide the argument")
        if s is None:
            raise Decline("no argument to add (rustc suggests another change)")
        src, a, b = self.at(s)
        used = []

        def fill(m: re.Match) -> str:
            arg = self.mapping.argument(m.group(1))
            if arg is None:
                raise Decline(f"no [[argument]] row for `{m.group(1)}`")
            used.append(arg)
            return arg["expr"]

        edits = [Edit(s.file, a, b, re.sub(r"/\*\s*(.*?)\s*\*/", fill, s.replacement))]
        for arg in used:
            if "param" in arg and not self.bound(src, a, param_name(arg)):
                edits.append(self.add_param(src, s.file, a, arg))
        return edits

    def e0425(self, d: Diag) -> list[Edit]:
        """The cascade's backstop: rustc found a configured argument name unbound where a call passes it."""
        m = re.fullmatch(r"cannot find value `(\w+)` in this scope", d.message)
        arg = m and next((x for x in self.mapping.arguments if "param" in x and param_name(x) == m.group(1)), None)
        if not arg:
            raise LookupError
        src, a, _ = self.at(d.primary)
        return [self.add_param(src, d.primary.file, a, arg)]

    def bound(self, src: Source, pos: int, name: str) -> bool:
        """Whether name could be bound at pos: it occurs as a plain identifier in the enclosing fn before pos.

        A binding always precedes its uses in the text, so no occurrence means unbound. An occurrence that is not a
        binding (another scope) leaves the call to rustc's E0425 in the next round."""
        fn = enclosing_fn(src, pos)
        if fn is None:
            return False
        return re.search(rf"(?<![.\w])(?<!::){re.escape(name)}\b", src.masked[fn.p_open:pos]) is not None

    def add_param(self, src: Source, file: str, pos: int, arg: dict) -> Edit:
        fn = enclosing_fn(src, pos)
        if fn is None:
            raise Decline("the call is outside a fn")
        name = param_name(arg)
        why = ("the trait fixes its signature" if trait_bound(src, fn) else "it is `main`" if fn.name == "main"
               else "it is a test" if is_test(src, fn) else None)
        if why:
            raise Decline(f"`{fn.name}` needs parameter `{name}`, but {why}")
        m, param = src.masked, arg["param"].strip()
        a, b = fn.p_open + 1, fn.p_close
        inner = m[a:b]
        if not inner.strip():
            return Edit(file, a, a, param)
        parts = top_level_segments(m, a, b, angles=True)
        first = m[parts[0][0]:parts[0][1]]
        if arg.get("position", "last") == "first":
            if re.fullmatch(r"\s*(&\s*('\w+\s+)?)?(mut\s+)?self\b.*", first, re.S):
                if len(parts) == 1:
                    end = a + len(inner.rstrip())
                    return Edit(file, end, end, f", {param}")
                return Edit(file, parts[0][1] + 1, parts[0][1] + 1, f" {param},")
            return Edit(file, a, a, f"{param}, ")
        end = a + len(inner.rstrip())
        return Edit(file, end, end, f" {param}," if m[end - 1] == "," else f", {param}")

    # ---- E0609

    def e0609(self, d: Diag) -> list[Edit]:
        m = re.fullmatch(r"no field `(\w+)` on type `(.+)`", d.message)
        if not m:
            raise Decline("unexpected message")
        path = self.mapping.lookup(self.mapping.fields, m.group(2), m.group(1))
        if path is None:
            raise Decline(f"no [fields] row for `{type_name(m.group(2))}.{m.group(1)}`")
        _, a, b = self.at(d.primary)
        return [Edit(d.primary.file, a, b, path)]

    # ---- E0615

    def e0615(self, d: Diag) -> list[Edit]:
        m = re.fullmatch(r"attempted to take value of method `(\w+)` on type `(.+)`", d.message)
        if not m:
            raise Decline("unexpected message")
        name, typ = m.groups()
        src, a, b = self.at(d.primary)
        t, f = src.masked, d.primary.file
        op = re.match(r"\s*(<<=|>>=|[-+*/%^&|]=|=(?!=))", t[b:])
        start = receiver_start(t, a)
        borrow = re.search(r"&\s*mut\s+$", t[:start])
        if op or borrow:
            row = self.mapping.lookup(self.mapping.methods, typ, name) or {}
            if op and op.group(1) == "=" and "set" in row:
                vs = b + op.end()
                ve = expr_end(t, vs)
                if ve < 0:
                    raise Decline("cannot find the end of the assigned value")
                value = src.text[vs:ve].strip()
                return [Edit(f, a, ve, f"{row['set']}({value})")]
            if "mut" in row and (borrow or op.group(1) != "="):
                if borrow:
                    return [Edit(f, borrow.start(), start, ""), Edit(f, a, b, f"{row['mut']}()")]
                return [Edit(f, start, start, "*"), Edit(f, a, b, f"{row['mut']}()")]
            kind = "an assignment to" if op else "a mutable borrow of"
            raise Decline(f"{kind} `{type_name(typ)}.{name}`: no [methods] row with "
                          f"{'set' if op and op.group(1) == '=' else 'mut'}")
        s = d.help("use parentheses to call the method")
        if s is None or s.replacement != "()":
            raise Decline("the method takes arguments" if s else "rustc offers no call")
        _, sa, sb = self.at(s)
        return [Edit(s.file, sa, sb, "()")]

    # ---- E0502

    def e0502(self, d: Diag) -> list[Edit]:
        later = next((s for s in d.spans if s.label.endswith("later used by call")), None)
        if later is None:
            raise Decline("the conflicting borrow is not a call argument")
        src, _, le = self.at(later)
        m, f = src.masked, later.file
        o = le
        while o < len(m) and m[o].isspace():
            o += 1
        if o >= len(m) or m[o] != "(":
            raise Decline("no argument list after the call")
        close = match_close(m, o)
        inside = None
        for s in d.spans:
            if s.label.endswith("borrow occurs here"):
                _, bs, be = self.at(s)
                if o < bs and be <= close:
                    inside = bs
        if inside is None:
            raise Decline("no borrow inside the call's arguments")
        seg = next(p for p in top_level_segments(m, o + 1, close, angles=False) if p[0] <= inside <= p[1])
        raw = src.text[seg[0]:seg[1]]
        sa = seg[0] + len(raw) - len(raw.lstrip())
        sb = seg[0] + len(raw.rstrip())
        stmt = statement_start(m, src.c(later.start))
        prefix = m[stmt:o]
        if stmt < 0 or re.match(r"(else|while|for|loop)\b", prefix) or "=>" in prefix or "|" in prefix:
            raise Decline("the call is not a plain statement (loop, arm, closure or else branch)")
        line = m.rfind("\n", 0, stmt) + 1
        indent = src.text[line:stmt]
        if indent.strip():
            raise Decline("the statement does not start its line")
        fn = enclosing_fn(src, stmt)
        name = hoist_name(src.text[sa:sb], src.masked[fn.b_open:fn.b_close] if fn else "")
        return [Edit(f, stmt, stmt, f"let {name} = {src.text[sa:sb]};\n{indent}"), Edit(f, sa, sb, name)]

    # ---- the plan

    def plan(self, diags: list[Diag], only: set[str] | None = None) -> "Plan":
        """Edits of one diagnostic are taken together, and never when one overlaps an edit already taken."""
        recipes = {"E0061": self.e0061, "E0609": self.e0609, "E0615": self.e0615, "E0502": self.e0502,
                   "E0425": self.e0425}
        p = Plan()
        for d in diags:
            code = "E0061" if d.code == "E0425" else d.code
            recipe = recipes.get(d.code)
            if recipe is None or (only and code not in only):
                p.unhandled.append((d, None))
                continue
            try:
                edits = recipe(d)
            except LookupError:
                p.unhandled.append((d, None))
                continue
            except Decline as e:
                p.unhandled.append((d, str(e)))
                continue
            new = [e for e in dict.fromkeys(edits) if e not in p.edits]
            if any(overlaps(e, t) for e in new for t in p.edits) or any(
                    overlaps(x, y) for i, x in enumerate(new) for y in new[i + 1:]):
                p.unhandled.append((d, "overlaps another edit; rerun after applying"))
                continue
            p.edits += new
            p.handled.append((d, code))
        return p


@dataclass
class Plan:
    edits: list[Edit] = field(default_factory=list)
    handled: list[tuple[Diag, str]] = field(default_factory=list)   # (diagnostic, recipe code)
    unhandled: list[tuple[Diag, str | None]] = field(default_factory=list)  # (diagnostic, decline reason)

    def counts(self) -> Counter:
        return Counter(code for _, code in self.handled)


def overlaps(x: Edit, y: Edit) -> bool:
    if x.file != y.file or x == y:
        return False
    if x.start == x.end == y.start == y.end:
        return True
    return x.start < y.end and y.start < x.end


def receiver_start(m: str, a: int) -> int:
    """Start of the place expression whose field name starts at a (`self.view.zoom` -> offset of `self`)."""
    j = a
    while True:
        k = j
        while k > 0 and m[k - 1].isspace():
            k -= 1
        if k > 0 and m[k - 1] == "." and j == a:
            j = k - 1
            continue
        c = m[k - 1] if k > 0 else ""
        if c in ")]":
            j = match_open(m, k - 1)
            continue
        if c.isalnum() or c == "_":
            while k > 0 and (m[k - 1].isalnum() or m[k - 1] == "_"):
                k -= 1
            j = k
            while k > 0 and m[k - 1].isspace():
                k -= 1
            if k > 0 and m[k - 1] == ".":
                j = k - 1
                continue
            if k > 1 and m[k - 2:k] == "::":
                j = k - 2
                continue
        return j


def expr_end(m: str, i: int) -> int:
    """End of the expression starting at i: the `;` or `,` at depth 0, or a bracket that closes past it."""
    depth = 0
    for j in range(i, len(m)):
        if m[j] in OPEN:
            depth += 1
        elif m[j] in CLOSE:
            if depth == 0:
                return j
            depth -= 1
        elif m[j] in ";," and depth == 0:
            return j
    return -1


def statement_start(m: str, pos: int) -> int:
    """First character of the statement holding pos: after the `;`, `{` or `}` before it at depth 0."""
    j = pos - 1
    while j >= 0:
        if m[j] in ")]":
            j = match_open(m, j) - 1
            continue
        if m[j] in ";{}":
            break
        j -= 1
    j += 1
    while j < pos and m[j].isspace():
        j += 1
    return j


SKIP_NAMES = {"self", "mut", "as", "clone", "cloned", "copied", "to_owned", "to_string", "into", "unwrap", "expect",
              "as_ref", "as_mut", "iter", "get", "borrow"}


def hoist_name(expr: str, body: str) -> str:
    names = [n for n in IDENT.findall(mask(expr)) if n not in SKIP_NAMES and not n[0].isupper()]
    base = names[-1] if names else "value"
    name, n = base, 2
    while re.search(rf"(?<![.\w]){name}\b", body):
        name, n = f"{base}_{n}", n + 1
    return name


# ---------------------------------------------------------------- output


def apply(tree: Path, edits: list[Edit]) -> dict[str, tuple[str, str]]:
    """{file: (old text, new text)} for the edits, without writing."""
    out = {}
    for file in sorted({e.file for e in edits}):
        old = (tree / file).read_bytes().decode("utf-8")
        new = old
        for e in sorted((e for e in edits if e.file == file), key=lambda e: (e.start, e.end), reverse=True):
            new = new[:e.start] + e.text + new[e.end:]
        out[file] = (old, new)
    return out


def diff(changes: dict[str, tuple[str, str]]) -> str:
    return "".join("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{f}", f"b/{f}"))
                   for f, (old, new) in changes.items())


def unhandled_report(unhandled, pending=()) -> str:
    """Markdown: the errors no recipe handled, by code with counts, each with the recipe's reason when one declined;
    then the errors with an edit not applied (round limit)."""
    by = {}
    for d, why in unhandled:
        by.setdefault(d.code, []).append((d, why))
    lines = [f"# Errors codemod did not handle: {len(unhandled)}", ""]
    for code, items in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lines += [f"## {code}: {len(items)}", ""]
        lines += [f"- {d.where()}: {d.message}" + (f" (declined: {why})" if why else "") for d, why in items]
        lines.append("")
    if pending:
        lines += [f"## Edits not applied (round limit): {len(pending)}", ""]
        lines += [f"- {d.where()}: {d.code} {d.message}" for d in pending]
        lines.append("")
    return "\n".join(lines)
