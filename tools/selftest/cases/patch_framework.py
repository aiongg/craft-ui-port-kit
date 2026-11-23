"""patch-framework: the app's patch lines stay, a rerun changes nothing, 0 framework packages is an error."""
from lib import check

URL = "https://example.invalid/fw"
MANIFEST = f'''[package]
name = "app"

[dependencies]
craft-ui = {{ git = "{URL}", rev = "abc" }}

[patch.crates-io]
# the app's own patch
foo = {{ path = "../foo" }}
craft-x = {{ git = "{URL}", rev = "abc" }}
'''
LOCK = f'''version = 4

[[package]]
name = "app"
version = "0.1.0"

[[package]]
name = "craft-ui"
version = "0.1.0"
source = "git+{URL}?rev=abc#abc"

[[package]]
name = "craft-x"
version = "0.1.0"
source = "git+{URL}?rev=abc#abc"
'''


def setup(s, lock=LOCK):
    s.config({"framework.patch_urls": [URL], "framework.integration": str(s.root / "fw")})
    s.tree("fw", {"Cargo.toml": '[workspace]\n\n[patch.crates-io]\negui = { path = "vendor/egui" }\n',
                  "crates/ui/Cargo.toml": '[package]\nname = "craft-ui"\n',
                  "crates/x/Cargo.toml": '[package]\nname = "craft-x"\n'})
    return s.tree("app", {"Cargo.toml": MANIFEST, "Cargo.lock": lock})


def case_rerun_is_a_no_op(s):
    app = setup(s)
    p = s.run("patch-framework")
    check(p.returncode == 0, "first run", p)
    once = (app / "Cargo.toml").read_text()
    check('foo = { path = "../foo" }' in once and "# the app's own patch" in once, "the app's line stays", p)
    check(f'# port-kit overridden: craft-x = {{ git = "{URL}"' in once, "overridden app line commented out", p)
    check(f'craft-x = {{ path = "{s.root}/fw/crates/x" }}' in once and f'egui = {{ path = "{s.root}/fw/vendor/egui" }}' in once,
          "overrides added", p)
    check(f'[patch."{URL}"]\ncraft-ui = {{ path = "{s.root}/fw/crates/ui" }}' in once, "url table", p)
    (app / "Cargo.lock").write_text('version = 4\n\n[[package]]\nname = "craft-ui"\nversion = "0.1.0"\n')  # a local build
    p = s.run("patch-framework")
    check(p.returncode == 0 and (app / "Cargo.toml").read_text() == once, "the rerun changes nothing", p)


def case_no_framework_package(s):
    setup(s, lock='version = 4\n\n[[package]]\nname = "app"\nversion = "0.1.0"\n')
    p = s.run("patch-framework")
    check(p.returncode == 1 and "takes no package" in p.stderr, "0 packages exits 1", p)


def case_cargo_config_leaves_the_manifest(s):
    app = setup(s)
    cfg = s.root / "slot" / ".cargo" / "config.toml"
    p = s.run("patch-framework", "--cargo-config", str(cfg), str(app / "Cargo.toml"), str(app / "Cargo.lock"),
              str(s.root / "fw"))
    check(p.returncode == 0 and (app / "Cargo.toml").read_text() == MANIFEST, "the manifest is not changed", p)
    text = cfg.read_text()
    check(f'craft-x = {{ path = "{s.root}/fw/crates/x" }}' in text
          and f'[patch."{URL}"]\ncraft-ui = {{ path = "{s.root}/fw/crates/ui" }}' in text, f"config tables: {text}", p)
