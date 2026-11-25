"""minimal-port: the sites report, the repin and each rewrite class on a small app tree; dry run, --apply, idempotence."""
import json

from lib import check, git

FW_URL = "https://example.invalid/fw/craft-libs"
EGUI = "https://example.invalid/fw/egui.git"
OLD, EGUI_OLD, EGUI_NEW = "a" * 40, "1" * 40, "2" * 40

ROOT_MANIFEST = f'''[workspace]
members = ["crates/ui"]

[workspace.dependencies]
craft-ui = {{ version = "0.1.0", git = "{FW_URL}", rev = "{OLD}", features = ["serde", "native-windows"] }}
craft-update = {{ git = "{FW_URL}", rev = "{OLD}", features = ["egui"] }}
craft-keymap = {{ git = "{FW_URL}", rev = "{OLD}", features = [
    "ui",
] }}

[dependencies.craft-quit]
git = "{FW_URL}"
rev = "{OLD}"
features = ["egui"]

[patch.crates-io]
egui = {{ git = "{EGUI}", rev = "{EGUI_OLD}" }}
egui_demo_lib = {{ git = "{EGUI}", rev = "{EGUI_OLD}" }}
winit = {{ git = "https://example.invalid/other/winit", rev = "{EGUI_OLD}" }}
krilla = {{ git = "https://example.invalid/other/krilla", rev = "{EGUI_OLD}" }}
'''

CRATE_MANIFEST = '''[package]
name = "ui"

[dependencies]
craft-ui.workspace = true
craft-keymap = { workspace = true }
'''

DOCK = '''use craft_ui::docking::{
    Action, DockArea,
    Placement, Side,
};
use craft_ui::layout::{SplitAxis, SplitSize, split_rect};

/// A `Side` in a comment stays.
pub fn place(side: Side) -> Placement<u32> {
    let label = "Side";
    let axis = SplitAxis::Horizontal;
    let depth = craft_ui::docking::MAX_DEPTH;
    let monitor: Option<craft_ui::docking::Monitor> = None;
    let size = SplitSize::FixedFirst(1.0);
    todo!("{label} {axis:?} {depth} {monitor:?} {size:?} {side:?} {:?}", craft_ui::layout::SplitAxis::Vertical)
}

mod tests;
'''

DOCK_TESTS = '''use super::{Action, Side};

fn start() -> Side {
    Side::Start
}
'''

OWN_AXIS = '''use craft_ui::layout::SplitAxis;

enum Axis { Up }

fn f() -> SplitAxis { SplitAxis::Vertical }
'''

COMBO = '''fn combos(ui: &mut egui::Ui, v: &mut u32) {
    craft_ui::ComboBox::from_id_salt("a").selected_text("A").show_ui(ui, |ui| ui.label("x"));
    craft_ui::ComboBox::from_id_salt("b").selected_text({ let t = "B"; t }).show_ui(ui, |ui| ui.label("y"));
    craft_ui::ComboBox::from_id_salt("font").show_ui_with_header(ui, |ui| {}, |ui| {});
}
'''

KEYS = '''use craft_keymap::{Bindable, Kind, Keymap};
use craft_keymap::egui::Hit;

fn kinds(k: Kind, b: &Bindable, h: Hit, m: &Keymap) -> bool { matches!(k, Kind::Run) }
'''

OWN_KIND = '''pub enum Kind { Run }
fn mine(k: Kind) -> bool { matches!(k, Kind::Run) }
'''

APP = '''impl eframe::App for App {
    fn ui(&mut self, ctx: &egui::Context) {
        if ctx.input(|i| i.key_pressed(egui::Key::Escape)) {}
        let _ = craft_update::CheckResultDialog::new();
    }
}
'''


def setup(s):
    fw = s.tree("fw", {"Cargo.toml": f'[patch.crates-io]\negui = {{ git = "{EGUI}", rev = "{EGUI_NEW}" }}\n'
                                      'krilla = { path = "vendor/krilla" }\n'})
    rev = git(fw, "rev-parse", "HEAD").strip()
    app = s.tree("app", {"Cargo.toml": ROOT_MANIFEST, "crates/ui/Cargo.toml": CRATE_MANIFEST,
                         "crates/ui/src/lib.rs": "mod dock;\nmod combo;\nmod keys;\nmod own_axis;\nmod own_kind;\nmod app;\n",
                         "crates/ui/src/dock.rs": DOCK, "crates/ui/src/dock/tests.rs": DOCK_TESTS,
                         "crates/ui/src/own_axis.rs": OWN_AXIS, "crates/ui/src/combo.rs": COMBO,
                         "crates/ui/src/keys.rs": KEYS, "crates/ui/src/own_kind.rs": OWN_KIND,
                         "crates/ui/src/app.rs": APP})
    s.config({"framework.checkout": str(fw), "framework.repo": FW_URL, "app.checkout": str(app), "plan.base": rev})
    return app, rev


def case_sites(s):
    app, _ = setup(s)
    p = s.run("minimal-port", "sites")
    check(p.returncode == 1 and p.stdout.splitlines()[-1].startswith("minimal-port sites:"), "port items exit 1", p)
    d = json.loads((s.work / "runs/minimal/sites.json").read_text())
    check(d["writers"] == ["host", "dock"], f"a dock site asks for a host and a dock writer: {d['writers']}")
    for item, file in (("host", "crates/ui/src/app.rs"), ("input", "crates/ui/src/app.rs"),
                       ("dialogs", "crates/ui/src/app.rs"), ("combo", "crates/ui/src/combo.rs"),
                       ("dock", "crates/ui/src/dock.rs"), ("helpers", "crates/ui/src/dock.rs")):
        check(any(x["file"] == file for x in d["items"].get(item, [])), f"{item} site found in {file}: {d['items'].get(item)}")
    check("crates/ui/src/dock.rs" in d["dock_files"], "the dock file is sized", p)
    check(not any("A `Side` in a comment" in x["text"] for v in d["items"].values() for x in v), "comments are not sites")
    check(git(app, "status", "--porcelain") == "", "sites changes nothing")


def case_repin(s):
    app, rev = setup(s)
    p = s.run("minimal-port", "repin")
    check(p.returncode == 1, "a listed patch or features array exits 1", p)
    for line in (f'+craft-ui = {{ version = "0.1.0", git = "{FW_URL}", rev = "{rev}" }}',
                 f'+craft-update = {{ git = "{FW_URL}", rev = "{rev}", features = ["ui"] }}',
                 f'+egui = {{ git = "{EGUI}", rev = "{EGUI_NEW}" }}',
                 f'+egui_demo_lib = {{ git = "{EGUI}", rev = "{EGUI_NEW}" }}', '+features = ["ui"]'):
        check(line in p.stdout.splitlines(), f"repin diff has {line!r}", p)
    check("winit: the framework patches nothing from" in p.stdout and "craft-keymap features over several lines" in p.stdout,
          "an unknown fork and a multi-line features array are listed", p)
    check("krilla: the framework patches it from a path" in p.stdout and "  note " in p.stdout,
          "a crate the framework vendors is a note", p)
    check(git(app, "status", "--porcelain") == "", "without --apply nothing changes")
    p = s.run("minimal-port", "repin", "--apply")
    check(git(app, "log", "-1", "--format=%s").startswith("minimal-port repin: ") and git(app, "status", "--porcelain") == "",
          "--apply commits once", p)
    p = s.run("minimal-port", "repin")
    check(p.stdout.splitlines()[-1].startswith("minimal-port repin: 0 edits"), "a second repin changes nothing", p)


def case_repin_other_url(s):
    app, rev = setup(s)
    other = "https://example.invalid/up/craft-libs.git"
    (app / "crates/ui/Cargo.toml").write_text(CRATE_MANIFEST + f'craft-extra = {{ git = "{other}", rev = "{OLD}" }}\n')
    git(app, "commit", "-qam", "other url")
    p = s.run("minimal-port", "repin")
    check(f'+craft-extra = {{ git = "{FW_URL}", rev = "{rev}" }}' in p.stdout.splitlines(), "a manifest's other framework URL is repinned", p)


def case_rewrite(s):
    app, _ = setup(s)
    p = s.run("minimal-port", "rewrite", "--apply")
    check(p.returncode == 1, "the header menu is listed, exit 1", p)
    src = lambda f: (app / "crates/ui/src" / f).read_text()  # noqa: E731
    dock = src("dock.rs")
    for want in ("use craft_behavior::dock::{Action, DockEdge, DockPlacement};", "use craft_ui::docking::DockArea;",
                 "use craft_behavior::flow::Axis;", "use craft_behavior::dock::SplitSize;", "use craft_ui::layout::split_rect;",
                 "pub fn place(side: DockEdge) -> DockPlacement<u32>", "let axis = Axis::X;",
                 "craft_behavior::dock::MAX_DEPTH", "Option<craft_behavior::Monitor>", "craft_behavior::flow::Axis::Y",
                 "/// A `Side` in a comment stays.", 'let label = "Side";'):
        check(want in dock, f"dock.rs has {want!r}:\n{dock}", p)
    check("use super::{Action, DockEdge};" in src("dock/tests.rs") and "DockEdge::Start" in src("dock/tests.rs"),
          f"a child module's `use super::` follows the rename:\n{src('dock/tests.rs')}", p)
    own = src("own_axis.rs")
    check("use craft_behavior::flow::Axis as SplitAxis;" in own and "SplitAxis::Y" in own and "enum Axis" in own,
          f"a file binding the new name imports it under the old one:\n{own}", p)
    combo = src("combo.rs")
    check(combo.count("egui::ComboBox::from_id_salt") == 2 and 'craft_ui::ComboBox::from_id_salt("font")' in combo,
          f"plain chains move to egui, the header chain stays:\n{combo}", p)
    keys = src("keys.rs")
    check("use craft_keymap::{CommandDef, CommandKind, Keymap};" in keys and "use craft_keymap::Hit;" in keys
          and "fn kinds(k: CommandKind, b: &CommandDef" in keys and "CommandKind::Run" in keys, f"keymap renames:\n{keys}", p)
    check(src("own_kind.rs") == OWN_KIND, "an app's own Kind is untouched", p)
    crate = (app / "crates/ui/Cargo.toml").read_text()
    root = (app / "Cargo.toml").read_text()
    check("craft-behavior.workspace = true" in crate and f'craft-behavior = {{ git = "{FW_URL}", rev = "{OLD}" }}' in root,
          f"craft-behavior added in the crate's form and in the workspace table:\n{crate}\n{root}", p)
    check(git(app, "log", "-1", "--format=%s").startswith("minimal-port rewrite: ") and git(app, "status", "--porcelain") == "",
          "--apply commits once", p)
    p = s.run("minimal-port", "rewrite")
    check(p.stdout.splitlines()[-1].startswith("minimal-port rewrite: 0 edits"), "a second rewrite changes nothing", p)
    p = s.run("minimal-port", "rewrite", "--only", "nonesuch")
    check(p.returncode == 2 and "unknown class" in p.stderr, "an unknown class is a usage error", p)


def case_minimal_mode(s):
    """work.mode = minimal: no phases, the hook names the minimal runbook, the landing gate wants a passed run."""
    s.config({"work.mode": "minimal", "minimal.run_platforms": ["linux", "macos"]})
    p = s.run("track", "phase", "0")
    check(p.returncode == 1 and "minimal port" in p.stderr, "track phase refuses in minimal mode", p)
    p = s.run("lead-context", "--cwd", str(s.work), stdin="")
    check("process/minimal-port.md" in p.stdout and "steps, not phases" in p.stdout, "the hook names the minimal runbook", p)
    sha = "0123456789abcdef0123456789abcdef01234567"
    p = s.run("land/exit-gate.py", "app", sha)
    check(p.returncode == 1 and "linux: no run recorded" in p.stderr, "no run: the app may not land", p)
    s.run("track", "event", "run", "linux checklist passed", "--data", "platform=linux", "--data", f"sha={sha[:12]}",
          "--data", "result=pass")
    s.run("track", "event", "run", "macOS: Cmd+Q lost changes", "--data", "platform=macos", "--data", f"sha={sha[:12]}",
          "--data", "result=fail")
    p = s.run("land/exit-gate.py", "app", sha)
    check(p.returncode == 1 and "macos: a run for" in p.stderr and "linux" not in p.stderr.split("platforms not passed")[1],
          "a failed platform blocks; a passed one does not", p)
    s.run("track", "event", "run", "macOS checklist passed", "--data", "platform=macos", "--data", f"sha={sha}",
          "--data", "result=pass")
    p = s.run("land/exit-gate.py", "app", sha)
    check(p.returncode == 1 and "macos: a run" in p.stderr, "a pass recorded after a failed row does not clear it", p)
    sha2 = "fedcba9876543210fedcba9876543210fedcba98"
    for plat in ("linux", "macos"):
        s.run("track", "event", "run", f"{plat} row 1", "--data", f"platform={plat}", "--data", f"sha={sha2[:12]}",
              "--data", "result=pass")
        s.run("track", "event", "run", f"{plat} row 2", "--data", f"platform={plat}", "--data", f"sha={sha2[:12]}",
              "--data", "result=pass")
    p = s.run("land/exit-gate.py", "app", sha2)
    check(p.returncode == 0 and "2 of 2 platforms passed" in p.stdout, "every platform passed: the app may land", p)
    sha3 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    na = ["track", "event", "run", "linux: update dialog", "--data", "platform=linux", "--data", f"sha={sha3[:12]}",
          "--data", "result=na"]
    p = s.run(*na)
    check(p.returncode != 0 and "reason" in p.stderr, "result=na without reason is rejected", p)
    p = s.run(*na, "--data", "reason=webview paints black")
    check(p.returncode != 0 and "covered" in p.stderr, "result=na without covered is rejected", p)
    p = s.run(*na, "--data", "reason=webview paints black", "--data", "covered=macos run")
    check(p.returncode == 0, "result=na with reason and covered is accepted", p)
    s.run("track", "event", "run", "macos ok", "--data", "platform=macos", "--data", f"sha={sha3[:12]}", "--data", "result=pass")
    p = s.run("land/exit-gate.py", "app", sha3)
    check(p.returncode == 1 and "linux: no pass recorded" in p.stderr and "macos" not in p.stderr.split("not passed")[1],
          "na alone does not satisfy a platform", p)
    s.run("track", "event", "run", "linux other rows", "--data", "platform=linux", "--data", f"sha={sha3[:12]}", "--data", "result=pass")
    p = s.run("land/exit-gate.py", "app", sha3)
    check(p.returncode == 0, "na beside a pass does not block", p)
    # rows, replacement and corrections
    sha4 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    def run_ev(plat, text, result, row=None, sha_=sha4):
        args = ["track", "event", "run", text, "--data", f"platform={plat}", "--data", f"sha={sha_[:12]}", "--data", f"result={result}"]
        if row:
            args += ["--data", f"row={row}"]
        s.run(*args)
    run_ev("linux", "r1 bad", "fail", "r1")
    run_ev("linux", "r2 ok", "pass", "r2")
    run_ev("macos", "r1 ok", "pass", "r1")
    p = s.run("land/exit-gate.py", "app", sha4)
    check(p.returncode == 1 and "linux: a run" in p.stderr and "macos: a run" not in p.stderr, "a failed row blocks its platform only", p)
    run_ev("macos", "r1 other commit ok", "pass", "r1", sha_=sha3)
    run_ev("linux", "r3 other row ok", "pass", "r3")
    p = s.run("land/exit-gate.py", "app", sha4)
    check(p.returncode == 1, "no replacement across rows or commits", p)
    run_ev("macos", "r1 rerun ok", "pass", "r1")
    run_ev("linux", "r1 rerun ok", "pass", "r1")
    p = s.run("land/exit-gate.py", "app", sha4)
    check(p.returncode == 0 and "replaces" in p.stdout and "'fail' -> 'pass'" in p.stdout, "a later result on the same row replaces the earlier and is printed", p)
    # id-less events are unchanged: a pass after a fail does not clear it (above); corrections
    sha5 = "cccccccccccccccccccccccccccccccccccccccc"
    run_ev("linux", "idless bad", "fail", sha_=sha5)
    run_ev("macos", "idless ok", "pass", sha_=sha5)
    run_ev("linux", "idless ok", "pass", sha_=sha5)
    p = s.run("land/exit-gate.py", "app", sha5)
    check(p.returncode == 1, "an id-less fail keeps blocking", p)
    evfile = next(iter(s.work.rglob("events.jsonl")), None)
    def events():
        return [json.loads(l) for l in evfile.read_text().splitlines()] if evfile else []
    ev = events()
    bad = next((e for e in ev if e.get("text") == "idless bad"), None)
    check(bad is not None, "the fail event is readable from the store", None)
    if bad:
        p = s.run("track", "correct", "nonesuch", "pass", "--reason", "x")
        check(p.returncode != 0 and "no event" in p.stderr, "a correction of an unknown id is rejected", p)
        okev = next(e for e in ev if e.get("text") == "idless ok")
        s.run("track", "event", "decision", "not a run")
        dec = events()[-1]
        p = s.run("track", "correct", dec["id"], "pass", "--reason", "x")
        check(p.returncode != 0 and "only `run` events" in p.stderr, "a correction of a non-run event is rejected", p)
        p = s.run("track", "correct", bad["id"], "pass")
        check(p.returncode != 0, "a correction without a reason is rejected", p)
        p = s.run("track", "correct", bad["id"], "na", "--reason", "unreachable")
        check(p.returncode != 0 and "covered" in p.stderr, "a correction to na without covered is rejected", p)
        p = s.run("track", "correct", bad["id"], "pass", "--reason", "x", "--data", "platform=macos")
        check(p.returncode != 0 and "platform" in p.stderr, "a correction naming another platform is rejected", p)
        p = s.run("track", "correct", bad["id"], "pass", "--reason", "x", "--data", f"sha={sha4[:12]}")
        check(p.returncode != 0 and "sha" in p.stderr, "a correction naming another commit is rejected", p)
        p = s.run("track", "correct", bad["id"], "pass", "--reason", "x", "--task", "other")
        check(p.returncode != 0 and "task" in p.stderr, "a correction naming another task is rejected", p)
        p = s.run("track", "correct", bad["id"], "pass", "--reason", "recorded wrongly")
        check(p.returncode == 0, "a correction is accepted", p)
        p = s.run("land/exit-gate.py", "app", sha5)
        check(p.returncode == 0 and "correction" in p.stdout and "'fail' -> 'pass'" in p.stdout and "recorded wrongly" in p.stdout,
              "the corrected fail no longer blocks and the gate prints the correction", p)
        s.run("track", "correct", bad["id"], "fail", "--reason", "second look")
        p = s.run("land/exit-gate.py", "app", sha5)
        check(p.returncode == 1, "the later correction of the same event counts", p)
    p = s.run("land/exit-gate.py", "framework", sha)
    check(p.returncode == 0, "a framework fix lands with no run gate", p)
