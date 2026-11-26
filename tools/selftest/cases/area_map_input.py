"""render-prompt --stage maps: the area mappers get every public top-level item of every framework crate's src/ui."""
import importlib.machinery
import importlib.util
import sys

from lib import TOOLS, check

sys.path.insert(0, str(TOOLS))
from portkit import config  # noqa: E402


def case_framework_ui_types(s):
    s.tree("snap-fw", {"crates/layers/src/ui/panel.rs": "pub struct LayersPanel;\nimpl LayersPanel {\n    pub fn show() {}\n}\n"
                                                        "pub(crate) fn hidden() {}\n",
                       "crates/layers/src/model.rs": "pub struct Model;\n",
                       "crates/vector/src/ui.rs": "/// Kinds.\npub enum ShapeKind {}\n"})
    s.config({"framework.snapshot": str(s.root / "snap-fw")})
    loader = importlib.machinery.SourceFileLoader("render_prompt", str(TOOLS / "render-prompt"))
    spec = importlib.util.spec_from_loader("render_prompt", loader)
    rp = importlib.util.module_from_spec(spec)
    loader.exec_module(rp)
    text = rp.framework_ui_types(config.load(str(s.root / "port.toml"))).read_text()
    check("| crates/layers | LayersPanel | struct | crates/layers/src/ui/panel.rs:1 |" in text
          and "| crates/vector | ShapeKind | enum | crates/vector/src/ui.rs:2 |" in text, f"family crates' UI items: {text}")
    check("Model" not in text and "show" not in text and "hidden" not in text,
          f"no item outside src/ui, no method, no crate-private item: {text}")
