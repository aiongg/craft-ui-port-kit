pub struct Ctx<'a> {
    pub s: &'a str,
}

pub struct Doc {
    pub pages: u32,
}

pub trait Panel {
    fn show(&self, doc: &Doc) -> u32;
}

fn draw(doc: &Doc, ctx: &mut Ctx<'_>) -> u32 {
    doc.pages + ctx.s.len() as u32
}

fn panel(doc: &Doc) -> u32 {
    draw(doc)
}

fn toolbar(doc: &Doc, ctx: &mut Ctx<'_>) -> u32 {
    ctx.s.len() as u32 + panel(doc)
}

struct Side;

impl Panel for Side {
    fn show(&self, doc: &Doc) -> u32 {
        panel(doc)
    }
}
