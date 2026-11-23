"""`port-set audit`: token-free plan checks over every sheet, the contract parts, the decisions and both code trees at
their writing bases. No model call, no worktree.

Four checks gate writing (process/05-plancheck-decide.md, step 8); each must report 0 before phase 5 starts:

  stubs           every contract item a set writes or another set calls (a pinned cross-set signature) is in the
                  stubs, with the parameter count the contract gives; every type a decision names that another set
                  also names exists in a tree
  stories         every component or variant the port adds to the framework names its gallery story and a story owner
  decision-files  every file a decisions.md adds or writes is in its set's Files table
  readers         every file that uses an item a sheet replaces is named by the sheet or owned by a set that names it

Six more report what a reader of the plan would want to know, without gating: line-refs, tests, markers, waves,
sizes, names. Reports go to <work.dir>/audit/<check>.md, each opening with how it decides, plus README.md (the
summary) and markers.tsv. tools/port-set.md describes each report.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from .bundle import build_bundle
from .context import OTHER, REPOS, ctx
from .plan import (SET_ID, TOK, Owners, Trees, all_sheets, calls_of, contract_table, def_regex, row_files,
                   set_dir_text, sig_items, writers)
from .scip import con as scip_con
from .sheet import RUST_KW, Sheet, base_files, idents_of, spans_of
from .write import Outcome

GATING = ("stubs", "stories", "decision-files", "readers")
ADVISORY = ("line-refs", "tests", "markers", "waves", "sizes", "names")

GENERIC_CAP = 60       # an identifier with more hit files than this is too common to say anything
SIMPLE_CAP = 12        # the same, for one-word names (`frame`, `Grab`)
WIDE_CAP = 40          # more unnamed hit files than this: one "wide" line, not a list
RARE = 8               # up to this many hit files, a `Type::name` mechanism does not need `Type` in the file
BUNDLE_TOKENS = 150_000
WRITE_LINES = 1500
SKIP_ROW = re.compile(r"\b(unchanged|gains?|kept|keeps?|adds?|added)\b", re.I)

# Gallery registration as the framework writes it (craft-libs docs/porting.md, "Adding a component or story to the
# gallery"): a type registers by `#[derive(Component)]` or as a pattern; a story is `#[story(Type ...)]`.
REGISTER = re.compile(r"#\[derive\([^)]*\b(?:Component|Pattern)\b|#\[pattern\b")
STORY = re.compile(r"#\[story\(\s*([A-Z]\w*)")
VARIANT_ROW = re.compile(r"\bvariant of\b|\bnamed (?:option|variant)\b|\bapp variant\b", re.I)
STORIES_KEY = "Stories"


# ---------------------------------------------------------------- stubs

def trace_index(T: Trees) -> tuple[set[str], dict[str, list[str]]]:
    """Contract ids the framework tree carries as `todo!("<id>")` and as `P3(` marker lines naming them."""
    todo_ids, p3 = set(), {}
    for p in T.files["fw"]:
        t = T.text("fw", p)
        if not t or ("todo!(" not in t and "P3(" not in t):
            continue
        for n, line in enumerate(T.lines("fw", p), 1):
            todo_ids |= set(re.findall(r'todo!\("([^"]+)"\)', line))
            if "P3(" in line:
                for i in re.findall(r"[a-z]{2}\.[A-Z]+\d+[a-z]?", line):
                    p3.setdefault(i, []).append(f"{p}:{n}")
    return todo_ids, p3


def _skip_angle(code: str, i: int) -> int:
    """Index after the `<...>` group starting at code[i] (`->` inside it is not a closing bracket)."""
    depth = 0
    while i < len(code):
        c = code[i]
        if c == "<":
            depth += 1
        elif c == ">" and code[i - 1] != "-":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def fn_params(code: str, name: str) -> list[int]:
    """Parameter counts (self forms excluded) of every `fn <name>` in a text."""
    out = []
    for m in re.finditer(rf"\bfn\s+{re.escape(name)}\b", code):
        i = m.end()
        while i < len(code) and code[i].isspace():
            i += 1
        if i < len(code) and code[i] == "<":
            i = _skip_angle(code, i)
        while i < len(code) and code[i].isspace():
            i += 1
        if i >= len(code) or code[i] != "(":
            continue
        depth, start, parts, j = 0, i + 1, [], i
        while j < len(code):
            c = code[j]
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
                if depth == 0:
                    parts.append(code[start:j])
                    break
            elif c == "<":
                depth += 1
            elif c == ">" and code[j - 1] != "-":
                depth -= 1
            elif c == "," and depth == 1:
                parts.append(code[start:j])
                start = j + 1
            j += 1
        params = [x.strip() for x in parts if x.strip()]
        params = [x for x in params if not re.fullmatch(r"&?\s*(?:'\w+\s+)?(?:mut\s+)?self(?:\s*:.*)?", x, re.S)]
        out.append(len(params))
    return out


def audit_stubs(sheets: list[Sheet], every: list[Sheet], T: Trees) -> tuple[list, list, int]:
    """(missing, decision names, checked). missing: (writer set, id, kind, files, why, callers)."""
    rows, W = contract_table(), writers()
    todo_ids, p3 = trace_index(T)
    callers: dict[str, set[str]] = {}
    for s in every:
        for cid in calls_of(s):
            callers.setdefault(cid, set()).add(s.id)
    chosen = {s.id for s in sheets}
    ids = sorted({cid for cid, ws in W.items() if ws & chosen} |
                 {cid for cid, cs in callers.items() if cs & chosen})
    missing, checked = [], 0
    for cid in ids:
        row = rows.get(cid)
        if not row or row["repo"] != "fw" or not re.match(r"(new|changed)", row["kind"]):
            continue
        items = sig_items(row["sig"])
        if not items:
            continue
        checked += 1
        ws = sorted(W.get(cid, ())) or ["-"]
        cs = sorted(callers.get(cid, set()) - set(ws))
        files = row_files(row, T)
        texts = {f: T.text("fw", f) for f in files}
        texts = {f: t for f, t in texts.items() if t}
        defined = [(k, n) for k, n in items if any(def_regex(k, n).search(t) for t in texts.values())]
        if not defined:
            if cid in todo_ids or cid in p3:
                continue
            why = "no item of the signature in the row's file" if texts else "the row's file is not in the tree"
            missing.append((ws[0], cid, row["kind"], ", ".join(row["file"]), why + ": " +
                            ", ".join(f"{k} {n}" for k, n in items[:4]), cs))
            continue
        # The parameter count of each fn the contract gives must match a definition of that fn.
        for k, n in defined:
            if k != "fn":
                continue
            want = fn_params(" ".join(re.findall(r"`([^`]+)`", row["sig"])) or row["sig"], n)
            have = [c for t in texts.values() for c in fn_params(t, n)]
            if want and have and not set(want) & set(have):
                missing.append((ws[0], cid, row["kind"], ", ".join(row["file"]),
                                f"`fn {n}` takes {'/'.join(map(str, sorted(set(have))))} parameters in the stubs, "
                                f"{'/'.join(map(str, sorted(set(want))))} in the contract", cs))
    return missing, decision_names(sheets, every, T), checked


NAME = re.compile(r"\b([A-Z]\w{2,})(?:::([a-z_]\w{2,}|[A-Z]\w{2,}))?")
STD = {"Self", "Option", "Some", "None", "Result", "String", "Vec", "Arc", "Box", "Default", "Debug", "Clone", "Copy",
       "PartialEq", "Serialize", "Deserialize", "Send", "Sync", "Path", "PathBuf", "HashMap", "BTreeMap", "TODO", "PLAN",
       "Rc", "Cow", "Ord", "Eq", "Hash", "FnMut", "Fn", "FnOnce", "Into", "From", "Iterator"}


def written(set_id: str) -> bool:
    return (ctx.sets / set_id / "check.md").exists()


def decision_names(sheets: list[Sheet], every: list[Sheet], T: Trees) -> list[tuple[str, str, list[str], str]]:
    """Backticked names in a decisions.md bullet that neither tree has and that another set's sheet or decisions also
    names, where one of those sets writes framework code: a cross-set item with nothing to compile against."""
    dec = {s.id: set_dir_text(s.id, "decisions.md") for s in every}
    repo = {s.id: s.repo for s in every}
    mention: dict[str, set[str]] = {}
    for s in every:
        for n in set(re.findall(r"\b\w{3,}\b", s.text + dec[s.id])):
            mention.setdefault(n, set()).add(s.id)
    words = T.words("fw") | T.words("app")
    out = []
    for s in sheets:
        if written(s.id) or not dec[s.id]:
            continue
        seen = {}
        for line in dec[s.id].splitlines():
            if not line.lstrip().startswith("- "):
                continue
            for span in re.findall(r"`([^`\n]+)`", line):
                for m in NAME.finditer(span):
                    if m.group(1) in STD and not m.group(2):
                        continue
                    seen.setdefault(m.group(2) or m.group(1), line.strip()[:220])
        for n, line in seen.items():
            if n in words:
                continue
            others = sorted(mention.get(n, set()) - {s.id})
            if not others or not any(repo[x] == "fw" for x in [s.id, *others]):
                continue
            out.append((s.id, n, others, line))
    return out


def fmt_stubs(missing, names, checked) -> str:
    out = ["# stubs: pinned signatures the stubs lack", "",
           "How it decides. Every contract id a set writes or another set calls (head keys `Contract items it writes` "
           "and `Contract items and ...`, ranges expanded; plus the row's Writer cell) whose framework row has kind "
           "new or changed and whose signature names a Rust item (`fn`, `struct`, `enum`, `trait`, `type`, `const`, "
           "`mod` or a `pub name:` field) is looked up in the framework tree at its writing base. It is present when "
           "one of the items is defined in the file the row's heading names, or the tree holds `todo!(\"<id>\")` or a "
           "`P3(` marker line naming the id. For each `fn` of the signature that is defined, the parameter count (self "
           "forms left out) must match one definition. Items defined only inside macros or re-exported from another "
           "file show as false positives.", "",
           "The second table lists backticked names in `decisions.md` bullets that neither tree has, that another set's "
           "sheet or decisions also names, where one of those sets writes framework code. Sets already written "
           "(their check.md exists) are not checked.", "",
           f"{checked} ids checked: {len(missing)} findings. {len(names)} decision names without a stub.", ""]
    if missing:
        out += ["## Contract items", "", "| Writer | Id | Kind | Row file | Finding | Called by |", "|---|---|---|---|---|---|"]
        out += [f"| {w} | {cid} | {k} | `{f}` | {why} | {', '.join(cs) or '-'} |" for w, cid, k, f, why, cs in missing]
        out.append("")
    if names:
        out += ["## Names in decisions", "", "| Set | Name | Also named by | Decision line |", "|---|---|---|---|"]
        for sid, n, others, line in names:
            more = f"{', '.join(others[:6])}{' ...' if len(others) > 6 else ''}"
            out.append(f"| {sid} | `{n}` | {more} | {line.replace('|', '/')} |")
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- stories

def registered_types(T: Trees) -> dict[str, list[str]]:
    """Gallery-registered type name -> `path:line` in the framework tree (a pattern's `probe(Type)` names its type)."""
    out: dict[str, list[str]] = {}
    for p in T.files["fw"]:
        t = T.text("fw", p)
        if not t or not REGISTER.search(t):
            continue
        lines = T.lines("fw", p)
        for n, line in enumerate(lines, 1):
            if not REGISTER.search(line):
                continue
            window = "\n".join(lines[n - 1:n + 6])
            probe = re.search(r"#\[pattern\(.*?probe\(\s*([A-Z]\w*)", window, re.S)
            decl = re.search(r"\b(?:struct|enum)\s+([A-Z]\w*)", window)
            name = probe.group(1) if probe else decl.group(1) if decl else None
            if name:
                out.setdefault(name, []).append(f"{p}:{n}")
    return out


def stories_line(s: Sheet) -> tuple[set[str], set[str]]:
    """(type names, story files) of a sheet's `Stories` head key."""
    v = s.head.get(STORIES_KEY, "")
    spans = re.findall(r"`([^`]+)`", v)
    files = {x for x in spans if x.endswith(".rs")}
    names = {m for x in spans if not x.endswith(".rs") for m in re.findall(r"\b[A-Z]\w+\b", x)}
    names |= set(re.findall(r"\b[A-Z][a-z]\w*[A-Z]\w*\b", re.sub(r"`[^`]*`", " ", v)))   # bare CamelCase names
    return names, files


def adds_component(s: Sheet) -> list[tuple[str, str, str]]:
    """(id, type, why) for every component or variant a sheet's written contract rows add."""
    rows, out = contract_table(), []
    for cid in sorted(i for i, ws in writers().items() if s.id in ws):
        row = rows.get(cid)
        if not row or row["repo"] != "fw":
            continue
        sig = row["sig"]
        if row["kind"].startswith("new") and REGISTER.search(sig):
            for k, n in sig_items(sig):
                if k in ("struct", "enum"):
                    out.append((cid, n, "new component"))
                    break
        elif VARIANT_ROW.search(row["kind"] + " " + row["beh"]):
            ty = next((n for k, n in sig_items(sig) if k in ("struct", "enum")), None) or \
                next(iter(re.findall(r"\b[A-Z][a-z]\w*\b", row["beh"])), None)
            if ty:
                out.append((cid, ty, "variant"))
    return out


def audit_stories(sheets: list[Sheet], every: list[Sheet], T: Trees) -> tuple[list, list, int]:
    """(sheet findings, tree findings, components checked)."""
    story_types = set()
    for p in T.files["fw"]:
        t = T.text("fw", p)
        if t and "#[story(" in t:
            story_types |= set(STORY.findall(t))
    declared = {s.id: stories_line(s) for s in every}
    sheet_find = []
    n = 0
    for s in sheets:
        names, files = declared[s.id]
        owned = {p for p, _ in s.files}
        for cid, ty, why in adds_component(s):
            n += 1
            if ty not in names:
                sheet_find.append((s.id, cid, ty, why, f"no `{STORIES_KEY}` head line naming `{ty}`"))
        for f in sorted(files):
            if f not in owned and f not in base_files(s.repo_of(f)):
                sheet_find.append((s.id, "-", ", ".join(sorted(names)) or "-", "stories file",
                                   f"`{f}` is in neither the Files table nor the tree"))
    tree_find = []
    reported = {ty for _, _, ty, _, _ in sheet_find}
    for ty, locs in sorted(registered_types(T).items()):
        if ty in story_types or ty in reported:
            continue
        n += 1
        d = locs[0].split(":")[0].rsplit("/", 1)[0]
        owners = sorted(sid for sid, (names, _) in declared.items() if ty in names)
        if not owners:   # a set that writes a stories file beside the type and names the type
            owners = sorted(s.id for s in every
                            if any(re.search(r"stor\w*\.rs$", p) and p.startswith(d + "/") for p, _ in s.files)
                            and re.search(rf"\b{re.escape(ty)}\b", s.text))
        if not owners:
            tree_find.append((ty, locs[0], "-"))
    return sheet_find, tree_find, n


def fmt_stories(sheet_find, tree_find, n) -> str:
    out = ["# stories: components without a gallery story or story owner", "",
           "How it decides. A sheet adds a component when a contract row it writes has kind new and a signature that "
           "registers a type with the gallery (`#[derive(Component)]`, `#[derive(Pattern)]` or `#[pattern(...)]`), and "
           "a variant when the row's kind or behaviour says `variant of`, `named option`, `named variant` or `app "
           f"variant`. Such a sheet needs a `- {STORIES_KEY}:` head line naming the type in backticks; a stories file "
           "the line names must be in the sheet's Files table or the tree. The framework tree is also checked: every "
           "registered type needs a `#[story(Type ...)]` there, or a story owner: a set whose Stories line names it, "
           "or that writes a stories file in the type's directory and names the type.", "",
           f"{n} components checked: {len(sheet_find)} sheet findings, {len(tree_find)} types with no story and no owner.", ""]
    if sheet_find:
        out += ["## Sheets", "", "| Set | Id | Type | What | Finding |", "|---|---|---|---|---|"]
        out += [f"| {sid} | {cid} | `{ty}` | {why} | {f} |" for sid, cid, ty, why, f in sheet_find]
        out.append("")
    if tree_find:
        out += ["## Registered types with no story and no owner", "", "| Type | Registered at |", "|---|---|"]
        out += [f"| `{ty}` | `{loc}` |" for ty, loc, _ in tree_find]
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- decision files

DEC_PATH = re.compile(r"\b((?:crates|apps|tools|src|tests|examples|benches|docs)/[\w./{},-]+\.(?:rs|toml|md|json|svg))\b")
DEC_VERB = re.compile(r"\b(add|adds|edit|edits|write|writes|new file|moves? to|goes? (?:in|to)|owns?|Files table|"
                      r"File add)\b", re.I)


def audit_decision_files(sheets: list[Sheet], owners: Owners) -> list[tuple[str, str, str]]:
    out = []
    for s in sheets:
        if written(s.id):
            continue
        dec = set_dir_text(s.id, "decisions.md")
        mine = {p for p, _ in s.files}
        for line in dec.splitlines():
            if not DEC_VERB.search(line):
                continue
            for p in dict.fromkeys(DEC_PATH.findall(line)):
                if "{" in p or p in mine or any(d.endswith("/") and p.startswith(d) for d in mine):
                    continue
                o = owners.of(s.repo_of(p), p)
                if o and s.id not in o and not re.search(r"Files table", line):
                    continue   # another set owns it: this set reads it
                out.append((s.id, p, ", ".join(o) or "none"))
    return out


def fmt_decision_files(res) -> str:
    out = ["# decision-files: files a decision writes outside its set's Files table", "",
           "How it decides. Every line of a set's `decisions.md` that says add, edit, write, new file, moves to, goes "
           "in, owns or Files table is read for repo paths (crates/, apps/, tools/, src/, tests/, examples/, benches/, "
           "docs/). A path is listed when it is not in the set's Files table (exact or under a directory entry) and "
           "either no other set owns it or the line adds it to the Files table. `port-set apply` refuses edits to "
           "files outside the Files table, so the writer would skip them. Sets already written are not checked.", "",
           f"{len(res)} paths.", ""]
    if res:
        out += ["| Set | Path | Owner by Files tables |", "|---|---|---|"]
        out += [f"| {sid} | `{p}` | {o} |" for sid, p, o in res]
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- readers

def scip_refs(own_repo: str, name: str, qual: str | None):
    """{(repo, path): lines} of references to the items named `name` (`qual::name` when the indexes know that pairing)
    that the sheet's own repo defines, read from both repos' indexes; None without both indexes. An item defined only
    in the other repo counts too (an app set may replace a framework item)."""
    cons = {r: scip_con(r) for r in REPOS}
    if any(c is None for c in cons.values()):
        return None

    def defs(repo, with_qual):
        q = "select distinct crate from occ where name=? and def=1" + (" and qual=?" if with_qual else "")
        return {c for (c,) in cons[repo].execute(q, (name, qual) if with_qual else (name,))}

    with_qual = bool(qual) and any(defs(r, True) for r in cons)
    crates = defs(own_repo, with_qual) or defs(OTHER[own_repo], with_qual)
    if not crates:
        return {}
    out = {}
    marks = ",".join("?" * len(crates))
    for repo, c in cons.items():
        q = f"select path, line from occ where name=? and def=0 and crate in ({marks})" + (" and qual=?" if with_qual else "")
        for path, line in c.execute(q, (name, *crates, qual) if with_qual else (name, *crates)):
            if not path.startswith("/"):
                out.setdefault((repo, path), []).append(line)
    return out


def audit_readers(sheets: list[Sheet], every: list[Sheet], T: Trees, owners: Owners):
    """Replaced-mechanism identifiers with hits in files the sheet neither names nor owns. With both SCIP indexes the
    hits are exact references; without them, text hits."""
    plan, wanted = {}, set()
    for s in sheets:
        prev, items = None, []
        for r in s.replaced:
            if len(r) < 2:
                continue
            mech = r[0]
            if mech.lower().startswith("same"):
                mech = prev
            else:
                prev = mech
            if not mech or SKIP_ROW.search(mech):
                continue
            if set(SET_ID.findall(mech)) - {s.id}:
                continue   # another set makes this change; its own sheet carries the readers
            for sp in spans_of(mech):
                for name, qual in idents_of(sp):
                    items.append((name, qual, mech))
                    wanted.add(name)
        plan[s.id] = items
    T.scan(wanted)
    sheet_texts = {s.id: s.text for s in every}
    results, found, skipped_all, exact_used = {}, 0, {}, False
    for s in sheets:
        named_tokens = {p for p, _ in s.files}
        for r in s.replaced + s.table("Requests to other sets"):
            if len(r) > 1:
                named_tokens |= set(re.findall(r"[\w./-]+\.rs", r[1]))

        def named(p):
            return any(p == t or p.endswith("/" + t) or t.endswith("/" + p) for t in named_tokens)

        per_file, skipped, seen, wide = {}, [], set(), {}
        for name, qual, mech in plan[s.id]:
            if (name, qual) in seen:
                continue
            seen.add((name, qual))
            w = T.where(name)
            exact = scip_refs(s.repo, name, qual)
            if exact is None:
                exact = {}
            else:
                exact_used = True
                w = dict(exact)
            nfiles = len(w)
            cap = SIMPLE_CAP if (name.islower() and "_" not in name) or re.fullmatch(r"[A-Z][a-z]+", name) else GENERIC_CAP
            if nfiles > cap:
                skipped.append(f"`{name}` ({nfiles} files)")
                continue
            rare = nfiles <= RARE
            mine = {}
            for (repo, p), lines in sorted(w.items()):
                if named(p) or s.id in owners.of(repo, p):
                    continue
                if (repo, p) in exact:
                    mine[(repo, p)] = sorted(set(lines))[:3]
                    continue
                text = T.text(repo, p) or ""
                if qual and not rare and qual not in set(TOK.findall(text)):
                    continue
                if re.search(rf"\b(?:fn|struct|enum|trait|type|const|static)\s+{re.escape(name)}\b", text):
                    continue   # the file defines an item of that name itself: not a reader of the removed one
                src = T.lines(repo, p)
                code = [n for n in lines if not src[n - 1].lstrip().startswith("//")]
                if qual and name[0].isupper():   # a variant or associated item: the line must name its owner
                    code = [n for n in code if re.search(rf"\b{re.escape(qual)}\b", src[n - 1])]
                if code:
                    mine[(repo, p)] = code[:3]
            if len(mine) > WIDE_CAP:
                wide[name] = (len(mine), nfiles)
                continue
            for k, code in mine.items():
                own = owners.of(*k)
                if own and all(o != s.id and re.search(rf"\b{re.escape(name)}\b", sheet_texts.get(o, "")) for o in own):
                    continue   # the file's own set names this item: it handles the read
                e = per_file.setdefault(k, {"idents": {}, "owner": own})
                e["idents"].setdefault(name, code)
        skipped = list(dict.fromkeys(skipped))
        if skipped:
            skipped_all[s.id] = skipped
        if per_file or wide:
            results[s.id] = (per_file, wide)
            found += len(per_file) + len(wide)
    return results, found, skipped_all, exact_used


def fmt_readers(results, skipped, sheets, exact_used) -> str:
    src = ("exact references from both SCIP indexes" if exact_used else
           "whole-word text hits in both trees (no SCIP index: build `<work.scip>/fw.sqlite` and `app.sqlite` for exact "
           "references)")
    out = ["# readers: files that use a replaced mechanism and are not in the plan", "",
           "How it decides. For each row of a sheet's `Replaced mechanisms` table (a row starting `same` repeats the "
           "row above; rows saying unchanged, gains, kept or adds are skipped; rows naming another set are that set's), "
           "the first path expression of every backticked span gives an identifier (last `::` segment, qualifier kept). "
           "Names under 4 characters and common words are dropped. Hits come from " + src + "; comment lines do not "
           f"count. A name with more than {WIDE_CAP} unnamed hit files is reported as one 'wide' line; one with more "
           f"than {GENERIC_CAP} hit files ({SIMPLE_CAP} for one-word names) is too common and is skipped (listed). With "
           f"more than {RARE} text hit files, a `Type::name` mechanism also needs `Type` in the file (a CamelCase "
           "`Type::Variant` needs it on the hit line). A file that defines an item of that name itself is not a reader. "
           "A hit file is listed when the sheet does not own it and does not name it (Files, Reader column or Requests "
           "table, by path suffix), unless the file's own set names the item. `owner` is the set that owns the file, "
           "or `-`.", ""]
    for s in sheets:
        if s.id not in results and s.id not in skipped:
            continue
        out.append(f"## {s.id}")
        pf, wide = results.get(s.id, ({}, {}))
        if wide:
            out += ["", f"Wide (more than {WIDE_CAP} unnamed hit files; the plan must give a rule, not a list): " +
                    ", ".join(f"`{k}` {a} of {b} files" for k, (a, b) in sorted(wide.items()))]
        if pf:
            out += ["", "| file | identifiers (first lines) | owner |", "|---|---|---|"]
            for (repo, p), e in sorted(pf.items())[:60]:
                ids = "; ".join(f"`{n}` :{','.join(map(str, ls))}" for n, ls in sorted(e["idents"].items()))
                out.append(f"| {repo}:{p} | {ids} | {', '.join(e['owner']) or '-'} |")
            if len(pf) > 60:
                out.append(f"| ... {len(pf) - 60} more files | | |")
        if s.id in skipped:
            out += ["", "Skipped as too common: " + ", ".join(skipped[s.id])]
        out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- line refs

def segments(text: str):
    """Cells of table rows and sentences of prose lines."""
    for line in text.splitlines():
        for cell in (line.split(" | ") if line.startswith("|") else [line]):
            yield from re.split(r"(?<=[.;])\s+(?=[A-Z(])", cell)


def ranges_of(tail: str) -> list[tuple[int, int]]:
    return [(int(a), int(b) if b else int(a)) for a, b in re.findall(r"(\d+)(?:-(\d+))?", tail)]


def audit_linerefs(sheets: list[Sheet], T: Trees):
    res, total = {}, 0
    for s in sheets:
        owned = {p for p, _ in s.files}
        found = []
        for seg in segments(s.text):
            refs = list(re.finditer(r"((?:[\w.-]+/)*[\w.-]+\.rs):(\d+)(?:-(\d+))?((?:,\s*`?:\d+(?:-\d+)?`?)*)", seg))
            if not refs:
                continue
            sp_ids = [(mm.start(), nm) for mm in re.finditer(r"`([^`]+)`", seg) for nm, q in idents_of(mm.group(1))]
            if not sp_ids:
                continue
            for k, m in enumerate(refs):
                prev_end = refs[k - 1].end() if k else 0
                next_start = refs[k + 1].start() if k + 1 < len(refs) else len(seg)
                idents = [nm for pos, nm in sp_ids if prev_end <= pos < m.start()] or \
                         [nm for pos, nm in sp_ids if m.end() <= pos < next_start]
                if not idents:
                    continue
                path = m.group(1)
                cands = [(r, path) for r in (s.repo, OTHER[s.repo]) if path in base_files(r)]
                if not cands:
                    pool = [p for p in owned if p.endswith("/" + path)]
                    if len(pool) != 1:
                        pool = sorted({f for r in REPOS for f in T.files[r] if f.endswith("/" + path)})
                    if len(pool) != 1:
                        continue
                    cands = [(s.repo_of(pool[0]), pool[0])]
                repo, p = cands[0]
                lines = T.lines(repo, p)
                if lines is None:
                    continue
                for lo, hi in [(int(m.group(2)), int(m.group(3) or m.group(2)))] + ranges_of(m.group(4)):
                    if lo > len(lines):
                        found.append((p, lo, hi, f"line past end of file ({len(lines)} lines)", idents))
                        continue
                    a, b = max(1, lo - 20), min(len(lines), hi + 20)
                    window = "\n".join(lines[a - 1:b])
                    if any(re.search(rf"\b{re.escape(i)}\b", window) for i in idents):
                        continue
                    near = None
                    for i in idents:
                        ls = [n for n, l in enumerate(lines, 1) if re.search(rf"\b{re.escape(i)}\b", l)]
                        if ls:
                            d = min(ls, key=lambda n: abs(n - lo))
                            if near is None or abs(d - lo) < abs(near[1] - lo):
                                near = (i, d)
                    why = f"`{near[0]}` is at :{near[1]}" if near else "no named identifier in the file"
                    found.append((p, lo, hi, why, idents))
        if found:
            seen, uniq = set(), []
            for f in found:
                if (f[0], f[1], f[3]) not in seen:
                    seen.add((f[0], f[1], f[3]))
                    uniq.append(f)
            res[s.id] = uniq
            total += len(uniq)
    return res, total


def fmt_linerefs(res, total, sheets) -> str:
    strong = sum(1 for v in res.values() for f in v if "is at" in f[3] or "past end" in f[3])
    out = ["# line-refs: `path:N` references whose identifier is not near the line", "",
           "How it decides. In every table cell or sentence of a sheet that has a `path:N` or `path:N-M` reference "
           "(also `, :N` continuations) and names backticked identifiers, the reference is stale when none of those "
           "identifiers (4+ characters, not a common word) appears within 20 lines of N..M in the file at the writing "
           "base, or when N is past the file's end. `is at :K` means one of the identifiers is in the file at K (a "
           "moved line, the strong signal; `port-set remap` was likely not run); `no named identifier in the file` "
           "usually means the cell names a new item the writer adds, and is weaker. Bare file names resolve by a "
           "unique path suffix; ambiguous ones are skipped. An identifier is bound to the reference that follows it "
           "in its cell or sentence (the one before it when none follows).", "",
           f"{total} references flagged: {strong} strong, {total - strong} weak.", ""]
    for title, pick in (("Strong", lambda f: "no named identifier" not in f[3]),
                        ("Weak", lambda f: "no named identifier" in f[3])):
        out += [f"## {title}", ""]
        for s in sheets:
            rows = [f for f in res.get(s.id, []) if pick(f)]
            if rows:
                out.append(f"### {s.id}")
                for p, lo, hi, why, ids in rows:
                    out.append(f"- `{p}:{lo}{'-' + str(hi) if hi != lo else ''}` {why}; names "
                               + ", ".join(f"`{i}`" for i in dict.fromkeys(ids)))
                out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- tests

def audit_tests(sheets: list[Sheet], T: Trees):
    def name_of(sp):
        return re.sub(r"\(.*$", "", sp.split("::")[-1]).strip()

    T.scan({x for s in sheets for r in s.tests for sp in spans_of(r[1] if len(r) > 1 else "") for x in [name_of(sp)] if x})

    def elsewhere(nm):
        return [p for (rp, p), ls in T.where(nm).items()
                if any(re.match(rf"\s*(?:pub\s+)?(?:async\s+)?fn\s+{re.escape(nm)}\b", T.lines(rp, p)[l - 1]) for l in ls)][:2]

    res, n = {}, 0
    for s in sheets:
        bad = []
        mine_paths = {p for p, _ in s.files}
        for r in s.tests:
            if len(r) < 3:
                continue
            verdict = r[2].strip().lower().split()[0].strip("`*.,;") if r[2].strip() else ""
            if verdict not in ("keep", "rewrite", "move", "delete"):
                continue
            n += 1
            m = re.search(r"[\w./-]+\.rs", r[0])
            names = [x for sp in spans_of(r[1]) for x in [name_of(sp)] if x]
            if not m or not names:
                continue
            path = m.group(0)
            cands = [(repo, path) for repo in (s.repo, OTHER[s.repo]) if path in base_files(repo)]
            if not cands:
                suff = sorted({(repo, f) for repo in REPOS for f in T.files[repo] if f.endswith("/" + path)})
                mine = [x for x in suff if x[1] in mine_paths]
                own = [x for x in suff if x[0] == s.repo]
                cands = mine[:1] if len(mine) == 1 else suff if len(suff) == 1 else own[:1] if len(own) == 1 else []
            if not cands:
                e = elsewhere(names[0])
                bad.append((path, names[0], verdict, "file not in either tree" + (f"; fn is in {', '.join(e)}" if e else "")))
                continue
            repo, p = cands[0]
            t = T.text(repo, p) or ""
            nm = names[0]
            if re.search(rf"\bfn\s+{re.escape(nm)}\b", t):
                continue
            if re.search(rf"\b{re.escape(nm)}\b", t):
                bad.append((p, nm, verdict, "name present but not as `fn` (macro-made test or renamed)"))
            else:
                e = elsewhere(nm)
                bad.append((p, nm, verdict, "no such function in the file" + (f"; fn is in {', '.join(e)}" if e else "")))
        if bad:
            res[s.id] = bad
    return res, n


def fmt_tests(res, n, sheets) -> str:
    total = sum(map(len, res.values()))
    out = ["# tests: Tests-table rows whose function is not in the file", "",
           "How it decides. Each Tests row with verdict keep, rewrite or delete names a test in backticks (the last "
           "`::` segment, arguments dropped) and a file. The check passes when the file (resolved in the set's repo, "
           "then the other repo, then by a unique path suffix) has `fn <name>` at the writing base. Rows of verdict "
           "`new` are not checked. A name that appears without `fn` (made by a macro) is listed as weaker.", "",
           f"{n} rows checked, {total} flagged.", ""]
    for s in sheets:
        if s.id in res:
            out.append(f"## {s.id}")
            out += [f"- `{p}` `{nm}` ({v}): {why}" for p, nm, v, why in res[s.id]]
            out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- markers

def audit_markers(T: Trees, owners: Owners):
    rows, setcount, wrong = [], {}, []
    wr = {k: sorted(v) for k, v in writers().items()}
    for p in T.files["fw"]:
        t = T.text("fw", p)
        if not t or ("todo!(" not in t and "P3(" not in t):
            continue
        own = owners.of("fw", p)
        for n, line in enumerate(T.lines("fw", p), 1):
            for m in re.finditer(r"P3\(([^)]*)\)", line):
                for sid in [x.strip() for x in m.group(1).split(",") if x.strip()]:
                    ok = sid in own
                    rows.append((sid, f"{p}:{n}", m.group(0), ok))
                    setcount[sid] = setcount.get(sid, 0) + 1
                    if not ok:
                        wrong.append((sid, f"{p}:{n}", m.group(0), own))
            for m in re.finditer(r'todo!\("([^"]+)"\)', line):
                ws = wr.get(m.group(1), [])
                ok = bool(set(ws) & set(own))
                rows.append((ws[0] if ws else "-", f"{p}:{n}", m.group(0), ok))
                for w in ws[:1]:
                    setcount[w] = setcount.get(w, 0) + 1
                if not ok:
                    wrong.append((ws[0] if ws else "-", f"{p}:{n}", m.group(0), own))
    return rows, setcount, wrong


def fmt_markers(rows, setcount, wrong) -> str:
    out = ["# markers: P3 and todo! markers in the framework stubs", "",
           "How it decides. Every `P3(<set>[, <set>])` marker and `todo!(\"<id>\")` in the framework tree's `.rs` "
           "files at its writing base. A `P3` marker is misplaced when its set does not own the file (exact path, "
           "directory entry or glob in a Files table). A `todo!` is attributed to the set that writes the id, and is "
           "misplaced when that set does not own the file; `-` means no sheet writes the id. Per set: the markers it "
           "must clear.", "", f"{len(rows)} markers, {len(wrong)} misplaced.", "", "## Misplaced", ""]
    out += [f"- {sid}: `{loc}` {m} (file owned by {', '.join(own) or 'nobody'})" for sid, loc, m, own in wrong]
    out += ["", "## Per set", "", "| set | markers to clear |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in sorted(setcount.items())]
    return "\n".join(out)


# ---------------------------------------------------------------- waits

def audit_waits(every: list[Sheet]):
    ids = {s.id for s in every}
    graph, unknown, selfw = {}, {}, []
    for s in every:
        key = next((k for k in s.head if k.startswith("Waits on")), None)
        deps = set(SET_ID.findall(s.head.get(key, ""))) if key else set()
        if s.id in deps:
            selfw.append(s.id)
            deps.discard(s.id)
        graph[s.id] = {d for d in deps if d in ids}
        if deps - ids:
            unknown[s.id] = sorted(deps - ids)
    # Tarjan's strongly connected components, iterative.
    index, low, onstack, stack, sccs, counter = {}, {}, set(), [], [], [0]

    def strong(v):
        work = [(v, iter(sorted(graph[v])))]
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        onstack.add(v)
        while work:
            node, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    onstack.add(w)
                    work.append((w, iter(sorted(graph[w]))))
                    break
                if w in onstack:
                    low[node] = min(low[node], index[w])
            else:
                work.pop()
                if work:
                    low[work[-1][0]] = min(low[work[-1][0]], low[node])
                if low[node] == index[node]:
                    comp = []
                    while True:
                        w = stack.pop()
                        onstack.discard(w)
                        comp.append(w)
                        if w == node:
                            break
                    if len(comp) > 1:
                        sccs.append(sorted(comp))

    for v in sorted(graph):
        if v not in index:
            strong(v)
    comp = {x: ("cycle", i) for i, c in enumerate(sccs) for x in c}

    def unit(v):
        return comp.get(v, ("set", v))

    cdeps = {}
    for v in graph:
        cdeps.setdefault(unit(v), set()).update(unit(d) for d in graph[v] if unit(d) != unit(v))
    waves, done, rest = [], set(), set(cdeps)
    while rest:
        w = sorted(c for c in rest if cdeps[c] <= done)
        if not w:
            break
        waves.append(w)
        done |= set(w)
        rest -= set(w)
    waves = [[x[1] if x[0] == "set" else f"[cycle {x[1]}: {len(sccs[x[1]])} sets]" for x in w] for w in waves]
    return sccs, unknown, selfw, waves


def fmt_waits(sccs, unknown, selfw, waves) -> str:
    out = ["# waves: dependency waves from the `Waits on` lines", "",
           "How it decides. Set ids (`<area>-w<n>`) in each sheet's `Waits on` head line are the edges. A set is in "
           "wave k when all its dependencies are in earlier waves. Sets in a cycle form one unit placed together; a "
           "set waiting on a cycle comes after it. The waves are a write order that never codes against an unwritten "
           "signature; findings are cycles, unknown ids and self-waits.", "",
           f"{len(sccs)} cycles, {len(unknown)} sets with unknown ids, {len(selfw)} self-waits; {len(waves)} waves.", ""]
    out += [f"- cycle {i} ({len(c)} sets): {', '.join(c)}" for i, c in enumerate(sccs)]
    out += [f"- {k} waits on unknown {', '.join(v)}" for k, v in sorted(unknown.items())]
    out += [f"- {k} waits on itself" for k in selfw]
    out += ["", "## Waves", ""]
    out += [f"{i}. ({len(w)}) " + ", ".join(w) for i, w in enumerate(waves)]
    return "\n".join(out)


# ---------------------------------------------------------------- sizes

def audit_sizes(sheets: list[Sheet], T: Trees):
    missing = [str(ctx.ref_tree(r)) for r in REPOS if T.roots[r] is None]
    if missing:   # the bundle reads the racheck base checkouts; without them its file texts would be empty
        return [(s.id, None, None, "not built: no checkout at " + ", ".join(missing)) for s in sheets]
    res = []
    for s in sheets:
        s.shared = True   # read the racheck base checkouts: no worktree per set
        try:
            b = build_bundle(s)
        except (Exception, SystemExit) as e:   # a sheet the script cannot build is itself a finding
            res.append((s.id, None, None, f"build failed: {e}"))
            continue
        finally:
            s.shared = False
        w = sum(int(re.sub(r"\D", "", r[2]) or 0) for r in s.table("Files") if len(r) > 3)
        secs = sorted(((len(x) // 4, x.split("\n", 1)[0].split(" ", 1)[-1]) for x in b.split("\n## ")[1:]
                       if x.startswith(("File ", "Excerpt "))), reverse=True)
        note = "; ".join(f"{h.split(' (')[0]} {t // 1000}k" for t, h in secs[:3]) if len(b) // 4 > BUNDLE_TOKENS else ""
        res.append((s.id, len(b) // 4, w, note))
    return res


def fmt_sizes(sz) -> tuple[str, int]:
    over = [r for r in sz if r[1] and r[1] > BUNDLE_TOKENS]
    big = [r for r in sz if r[2] and r[2] > WRITE_LINES]
    failed = [r for r in sz if r[1] is None]
    out = ["# sizes: bundle size per set", "",
           "How it decides. The writer bundle is built for each sheet from the racheck base checkouts (no worktrees). "
           f"Tokens are chars/4. Flagged: bundles over {BUNDLE_TOKENS // 1000}k tokens, sets whose Files rows write "
           f"more than {WRITE_LINES} lines (split candidates) and sheets the bundle builder cannot read. A set that "
           "edits files its dependencies change gets a slightly different bundle from its real tree.", "",
           f"{len(sz)} sets: {len(over)} over {BUNDLE_TOKENS // 1000}k tokens, {len(big)} over {WRITE_LINES} write "
           f"lines, {len(failed)} failed.", "", "| set | tokens | write lines | flags |", "|---|---|---|---|"]
    for sid, tok, w, note in sorted(sz, key=lambda r: -(r[1] or 0)):
        flags = [f for f, c in ((f"over {BUNDLE_TOKENS // 1000}k", tok and tok > BUNDLE_TOKENS),
                                (f"write > {WRITE_LINES}", w and w > WRITE_LINES)) if c]
        text = ", ".join(flags) + (f"; largest: {note}" if note and flags else "") if flags else note
        out.append(f"| {sid} | {tok if tok is not None else '-'} | {w if w is not None else '-'} | {text} |")
    return "\n".join(out), len(over) + len(big) + len(failed)


# ---------------------------------------------------------------- names

FNDEF = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:const\s+|async\s+|unsafe\s+)*fn\s+(\w+)")
IMPL = re.compile(r"^\s{0,4}impl(?:<[^>]*>)?\s+(?:(?:[\w:<>,' &]+?)\s+for\s+)?(\w+)")
STRUCT = re.compile(r"^\s{0,4}(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum)\s+(\w+)")
FIELD = re.compile(r"^\s+(?:pub(?:\([^)]*\))?\s+)?(\w+)\s*:")


class TypeDefs:
    """Per-crate index of inherent methods, `#[prop]` fields and type definitions by (type, name); built on use."""

    def __init__(self, T: Trees):
        self.T, self.crates = T, {}

    def crate(self, d: str) -> dict:
        if d in self.crates:
            return self.crates[d]
        idx = {}
        for p in self.T.files["fw"]:
            if not p.startswith(d + "/") or "/tests/" in p or p.endswith("/tests.rs"):
                continue
            cur, struct, prop = None, None, False
            for n, line in enumerate(self.T.lines("fw", p) or [], 1):
                m = IMPL.match(line)
                if m and not re.match(r"^\s{0,4}impl[^{]*\bfor\b", line):
                    cur = m.group(1)
                elif line.startswith("}"):
                    cur, struct = None, None
                ms = STRUCT.match(line)
                if ms:
                    struct, cur = ms.group(1), None
                    idx.setdefault(("type", ms.group(1)), []).append((p, n))
                mt = re.match(r"^\s{0,4}(?:pub(?:\([^)]*\))?\s+)?trait\s+(\w+)", line)
                if mt:
                    idx.setdefault(("type", mt.group(1)), []).append((p, n))
                if struct:
                    if "#[prop" in line:
                        prop = True
                    mf = FIELD.match(line)
                    if mf and prop:
                        idx.setdefault((struct, mf.group(1)), []).append((p, n))
                    if mf:
                        prop = False
                elif cur:
                    mf = FNDEF.match(line)
                    if mf:
                        idx.setdefault((cur, mf.group(1)), []).append((p, n))
        self.crates[d] = idx
        return idx


def audit_names(sheets: list[Sheet], T: Trees):
    rows, td, W = contract_table(), TypeDefs(T), writers()
    res, n = {}, 0
    for s in sheets:
        found = []
        deleted = {p for p, a in s.files if a == "delete"}
        for cid in sorted(i for i, ws in W.items() if s.id in ws):
            row = rows.get(cid)
            if not row or row["repo"] != "fw" or not row["kind"].startswith("new") or not row["crate_dir"]:
                continue
            sig, f = row["sig"], (row["file"] or [""])[0]
            idx = td.crate(row["crate_dir"])
            m = re.match(r"\s*`?(?:pub\s+)?impl(?:<[^>]*>)?\s+(?:[\w:]+\s+for\s+)?(\w+)", sig)
            ty = m.group(1) if m else None
            pairs = [(mm.group(1) or ty, mm.group(2)) for mm in re.finditer(r"\bfn\s+(?:(\w+)::)?(\w+)", sig)
                     if (mm.group(1) or ty) and mm.group(2) not in RUST_KW]
            pairs += [("type", mm.group(1)) for mm in re.finditer(r"\b(?:struct|enum|trait)\s+(\w+)", sig)]
            for t_, nm in pairs:
                n += 1
                if nm in row["repl"]:
                    continue
                defs = [x for x in idx.get((t_, nm), []) if x[0] not in deleted]
                if len(defs) >= 2:
                    found.append((cid, t_, nm, f, defs[:3]))
        if found:
            res[s.id] = found
    return res, n


def fmt_names(res, n, sheets) -> str:
    total = sum(map(len, res.values()))
    out = ["# names: new names that already exist in the same crate", "",
           "How it decides. For every contract id a sheet writes with kind `new` (framework rows), each `fn` the "
           "signature names is bound to its type (`impl Type { .. }` or `fn Type::name`), and each `struct`, `enum` and "
           "`trait` is taken as a type. The framework tree is scanned per crate for inherent methods (`impl Type`, not "
           "`impl Trait for`), `#[prop]` fields (which generate the builder of the same name) and type definitions. A "
           "name collides when the same (type, name) has two or more definitions in the crate (the stub and an older "
           "one), leaving out files the sheet deletes and names the row's Replaces cell lists. Test files are not "
           "scanned. Types match by name only, so two types of one name in different modules of a crate can show as "
           "false positives.", "", f"{n} names checked, {total} collisions.", ""]
    for s in sheets:
        if s.id in res:
            out.append(f"## {s.id}")
            for cid, t_, nm, f, other in res[s.id]:
                what = f"type `{nm}`" if t_ == "type" else f"`{t_}::{nm}`"
                out.append(f"- {cid} {what} (row file `{f}`) also at " + ", ".join(f"`{p}:{l}`" for p, l in other))
            out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- command

def cmd_audit(a) -> Outcome:
    t0 = time.time()
    every = all_sheets()
    known = {s.id for s in every}
    for x in a.sets:
        if x not in known:
            raise SystemExit(f"no sheet {x} in {ctx.sheets}")
    sheets = [s for s in every if not a.sets or s.id in a.sets]
    only = set(a.only.split(",")) if a.only else set(GATING + ADVISORY)
    if only - set(GATING + ADVISORY):
        raise SystemExit(f"--only: unknown checks {sorted(only - set(GATING + ADVISORY))}; "
                         f"checks: {', '.join(GATING + ADVISORY)}")
    out_dir = Path(ctx.cfg.path("work.dir")) / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    T, owners = Trees(), Owners(every)
    summary = []

    def emit(name, text, count, what):
        (out_dir / f"{name}.md").write_text(text + "\n")
        summary.append((name, count, what))
        print(f"{name}: {count} {what}  ({time.time() - t0:.0f}s)")

    if "stubs" in only:
        missing, names, checked = audit_stubs(sheets, every, T)
        emit("stubs", fmt_stubs(missing, names, checked), len(missing) + len(names),
             f"findings ({checked} pinned ids checked; {len(names)} decision names)")
    if "stories" in only:
        sf, tf, n = audit_stories(sheets, every, T)
        emit("stories", fmt_stories(sf, tf, n), len(sf) + len(tf), f"findings ({n} components checked)")
    if "decision-files" in only:
        df = audit_decision_files(sheets, owners)
        emit("decision-files", fmt_decision_files(df), len(df), "paths outside their set's Files table")
    if "readers" in only:
        res, n, skipped, exact = audit_readers(sheets, every, T, owners)
        emit("readers", fmt_readers(res, skipped, sheets, exact), n, f"files missed in {len(res)} sheets"
             + ("" if exact else " (text hits: no SCIP index)"))
    if "line-refs" in only:
        lr, n = audit_linerefs(sheets, T)
        emit("line-refs", fmt_linerefs(lr, n, sheets), n, f"stale refs in {len(lr)} sheets")
    if "tests" in only:
        tr, n = audit_tests(sheets, T)
        emit("tests", fmt_tests(tr, n, sheets), sum(map(len, tr.values())), f"missing tests in {len(tr)} sheets ({n} rows)")
    if "markers" in only:
        rows, setcount, wrong = audit_markers(T, owners)
        emit("markers", fmt_markers(rows, setcount, wrong), len(wrong), f"misplaced of {len(rows)} markers")
        (out_dir / "markers.tsv").write_text("set\tpath:line\tmarker\n" +
                                             "".join(f"{s}\t{loc}\t{m}\n" for s, loc, m, _ in sorted(rows)))
    if "waves" in only:
        sccs, unknown, selfw, waves = audit_waits(every)
        emit("waves", fmt_waits(sccs, unknown, selfw, waves), len(sccs) + len(unknown) + len(selfw),
             f"cycles, unknown ids and self-waits; {len(waves)} waves")
    if "sizes" in only:
        text, n = fmt_sizes(audit_sizes(sheets, T))
        emit("sizes", text, n, "flagged")
    if "names" in only:
        nm, n = audit_names(sheets, T)
        emit("names", fmt_names(nm, n, sheets), sum(map(len, nm.values())), f"collisions ({n} names checked)")

    gate = {name: c for name, c, _ in summary if name in GATING}
    rd = ["# Audit summary", "", f"Sheets audited: {len(sheets)} of {len(every)}. Run time {time.time() - t0:.0f} s. "
          "Each check file starts with how it decides. The gating checks must report 0 before writing starts.", "",
          "| check | gates writing | findings | what |", "|---|---|---|---|"]
    rd += [f"| [{n}]({n}.md) | {'yes' if n in GATING else 'no'} | {c} | {w} |" for n, c, w in summary]
    (out_dir / "README.md").write_text("\n".join(rd) + "\n")
    print(f"done in {time.time() - t0:.0f}s: {out_dir}")
    open_gates = {k: v for k, v in gate.items() if v}
    text = ("gating checks clean" if not open_gates else
            "gating findings: " + ", ".join(f"{k} {v}" for k, v in open_gates.items()))
    advisory = {name: c for name, c, _ in summary if name not in GATING}
    return Outcome(text, ok=not open_gates, log=out_dir / "README.md", data={"gating": gate, "advisory": advisory})


def register(sub) -> None:
    s = sub.add_parser("audit", help="token-free plan checks over the sheets, decisions and both trees (<work.dir>/audit/)")
    s.add_argument("sets", nargs="*", metavar="SET", help="audit only these sets (markers and waves always read all)")
    s.add_argument("--only", metavar="CHECK,...", help=f"run only these checks: {', '.join(GATING + ADVISORY)}")
    s.set_defaults(func=cmd_audit, owns_state=False, fail_exit=True)
