pub struct Ctx<'a> {
    pub s: &'a str,
}

mod v {
    pub struct View {
        z: f32,
    }

    impl View {
        pub fn zoom(&self) -> f32 {
            self.z
        }

        pub fn scale(&self, k: f32) -> f32 {
            self.z * k
        }

        pub fn set_zoom(&mut self, z: f32) {
            self.z = z;
        }
    }
}

pub struct Model {
    pub pages: u32,
}

pub struct Doc {
    pub model: Model,
    pub view: v::View,
    pub items: Vec<u32>,
}

impl Doc {
    fn first(&self) -> u32 {
        self.items[0]
    }

    fn items_mut(&mut self) -> &mut Vec<u32> {
        &mut self.items
    }
}

fn draw(doc: &Doc, ctx: &mut Ctx<'_>) -> u32 {
    doc.model.pages + ctx.s.len() as u32
}

// E0061: the call gets `ctx`, and `panel` gets the parameter.
fn panel(doc: &Doc) -> u32 {
    draw(doc)
}

// E0609 and E0615.
fn fields(doc: &mut Doc) -> f32 {
    let n = doc.pages;
    doc.view.zoom = 2.0;
    n as f32 + doc.view.zoom + doc.view.scale
}

// E0502.
fn hoist(doc: &mut Doc) {
    doc.items_mut().push(doc.first());
}

// E0308: no recipe.
fn wrong() -> u32 {
    "one"
}
