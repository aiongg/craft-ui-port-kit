"""codemod: each recipe at rustc's spans, the E0061 cascade over rounds, declined and unhandled errors listed.

The JSON fixtures are real rustc output for the .rs fixtures (in cargo's compiler-message form); cascade.<n>.json is
the check after round n-1 was applied."""
import json
import shutil

from lib import FIXTURES, check, git

FX = FIXTURES / "codemod"


def tree(s, fixture: str):
    t = s.tree("app", {"src/lib.rs": (FX / fixture).read_text()})
    shutil.copy(FX / "map.toml", s.root / "map.toml")
    return t


def case_recipes(s):
    t = tree(s, "recipes.rs")
    p = s.run("codemod", "r-diff", "--json", str(FX / "recipes.json"), "--tree", str(t), "--map", str(s.root / "map.toml"))
    check(p.returncode == 1, "unhandled errors exit 1", p)
    for line in ("+fn panel(doc: &Doc, ctx: &mut Ctx<'_>) -> u32 {", "+    draw(doc, ctx)",  # E0061 and cascade
                 "+    let n = doc.model.pages;",  # E0609
                 "+    doc.view.set_zoom(2.0);", "+    n as f32 + doc.view.zoom() + doc.view.scale",  # E0615
                 "+    let first = doc.first();", "+    doc.items_mut().push(first);"):  # E0502
        check(line in p.stdout.splitlines(), f"diff has {line!r}", p)
    check(git(t, "status", "--porcelain") == "", "without --apply nothing changes")
    rd = s.work / "runs" / "r-diff"
    un = (rd / "unhandled.md").read_text()
    check("## E0308: 1" in un and "mismatched types" in un, f"E0308 listed by code: {un}")
    check("`scale`" in un and "declined: the method takes arguments" in un, f"declined site with its reason: {un}")
    rem = (rd / "remaining.errors").read_text().splitlines()
    check(sorted(l.split(": error")[1][:7] for l in rem) == ["[E0308]", "[E0615]"]
          and rem[0].startswith("src/lib.rs:"), f"remaining.errors in compile-gate's format: {rem}")
    sm = json.loads((rd / "summary.json").read_text())
    check(sm["fixed"] == {"E0061": 1, "E0609": 1, "E0615": 2, "E0502": 1} and sm["unhandled"] == {"E0308": 1, "E0615": 1},
          f"summary counts: {sm}")
    check(p.stdout.splitlines()[-1].startswith("codemod r-diff: 5 fixed"), "summary line", p)

    p = s.run("codemod", "r-apply", "--json", str(FX / "recipes.json"), "--tree", str(t), "--map", str(s.root / "map.toml"),
              "--apply")
    src = (t / "src/lib.rs").read_text()
    check("doc.view.set_zoom(2.0);" in src and "let first = doc.first();\n    doc.items_mut().push(first);" in src,
          "--apply writes the edits", p)
    msg = git(t, "log", "-1", "--format=%s").strip()
    check(msg == "codemod r-apply: 5 fixed (E0615 2, E0061 1, E0502 1, E0609 1)" and git(t, "status", "--porcelain") == "",
          f"one commit naming the label and recipes: {msg!r}", p)
    p = s.run("codemod", "r-nomap", "--json", str(FX / "recipes.json"), "--tree", str(t), "--apply")
    check(p.returncode == 1, "without a map, E0061 and E0609 are listed, not guessed", p)
    (t / "src/lib.rs").write_text("dirty\n")
    p = s.run("codemod", "r-dirty", "--json", str(FX / "recipes.json"), "--tree", str(t), "--apply")
    check(p.returncode == 2 and "uncommitted" in p.stderr, "--apply refuses a dirty tree", p)


def case_cascade_rounds(s):
    t = tree(s, "cascade.rs")
    s.config({"app.integration": str(t)})
    for n in (1, 2, 3):
        shutil.copy(FX / f"cascade.{n}.json", s.root / "cl-logs" / f"check-all.{n}.log")
        (s.root / "cl-logs" / f"check-all.{n}.rc").write_text("101")
    rd = s.work / "runs" / "r1-compile"
    rd.mkdir(parents=True)
    (rd / "summary.json").write_text(json.dumps({"framework": {"crates": [{"crate": "a", "status": "ok"}]},
                                                 "app": {"status": "failed"}}))
    p = s.run("codemod", "c1", "--gate", "r1-compile", "--map", str(s.root / "map.toml"), "--apply", "--rounds", "5")
    calls = s.cl_calls()
    check(len(calls) == 3 and all(c[:2] == ["check", "all"] and "--keep-going" in c and c[-2:] == ["--message-format", "json"]
                                  for c in calls), f"three app checks with JSON, then no edit left: {calls}", p)
    src = (t / "src/lib.rs").read_text()
    check("fn panel(doc: &Doc, ctx: &mut Ctx<'_>) -> u32 {\n    draw(doc, ctx)" in src, "round 1: fill and cascade", p)
    check("ctx.s.len() as u32 + panel(doc, ctx)" in src and "fn toolbar(doc: &Doc, ctx: &mut Ctx<'_>) -> u32 {" in src,
          "round 2: a caller that has the binding gets the argument only", p)
    check("fn show(&self, doc: &Doc) -> u32 {\n        panel(doc)" in src, "the trait method is left alone", p)
    un = (s.work / "runs" / "c1" / "unhandled.md").read_text()
    check("`show` needs parameter `ctx`, but the trait fixes its signature" in un, f"trait caller declined: {un}")
    check(git(t, "rev-list", "--count", "HEAD").strip() == "2", "one commit for all rounds", p)
    sm = json.loads((s.work / "runs" / "c1" / "summary.json").read_text())
    check(sm["rounds"] == 2 and sm["fixed"] == {"E0061": 2} and sm["exit"] == 1, f"summary: {sm}")
