"""Pixel work for look pages: panel crops, difference images and crops of the regions that differ.

Needs Pillow and numpy (tools/look re-runs itself under `uv run --with pillow --with numpy` when they are missing).

A pixel differs visibly when one colour channel differs by more than the threshold (look.threshold, default 16 of
255). Shots of different sizes are compared over their shared area; the pixels outside it count as visibly
different.

Region crops are at the shots' own pixels, never enlarged or shrunk, and each fits in the reader limit
(look.reader_max_px): the production and port halves sit side by side when that fits, else one above the other,
and a region too large for either is cut into tiles that fit, each written as its own crop.
"""
from __future__ import annotations

from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

PAD_FILL = (70, 70, 70)   # outside the smaller of two differently sized shots
SHEET_GAP = 8             # pixels between the production and port halves of a region crop
SHEET_FILL = (255, 0, 255)


def crop_to(src: Path, box, dst: Path) -> tuple[int, int]:
    """Write `src` cropped to box (x0, y0, x1, y1), or whole when box is None. Returns the written size."""
    im = Image.open(src).convert("RGB")
    if box:
        x0, y0, x1, y1 = box
        im = im.crop((max(0, x0), max(0, y0), min(im.width, x1), min(im.height, y1)))
    im.save(dst, optimize=True)
    return im.size


def _delta(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Largest channel difference per pixel over the union of both sizes (255 outside the shared area)."""
    h, w = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])
    ch, cw = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    d = np.full((h, w), 255, dtype=np.int16)
    d[:ch, :cw] = np.abs(a[:ch, :cw] - b[:ch, :cw]).max(axis=2)
    return d


def _rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)


def compare(up_png: Path, port_png: Path, diff_png: Path, threshold: int) -> dict:
    """Write the difference image and return the shares of differing pixels.

    The image is the port shot in dim grey, pixels that differ by 1..threshold in dark amber, and visibly
    different ones in red."""
    a, b = _rgb(up_png), _rgb(port_png)
    d = _delta(a, b)
    h, w = d.shape
    base = np.zeros((h, w, 3), dtype=np.uint8)
    grey = b.mean(axis=2) * 0.35 + 20
    base[: b.shape[0], : b.shape[1]] = grey[..., None].astype(np.uint8)
    small = (d > 0) & (d <= threshold)
    big = d > threshold
    base[small] = (125, 90, 25)
    base[big] = (255, 40, 40)
    Image.fromarray(base).save(diff_png, optimize=True)
    n = h * w
    return {"visible": round(100 * float(big.sum()) / n, 2), "any": round(100 * float((d > 0).sum()) / n, 2),
            "same_size": a.shape == b.shape, "up_size": [a.shape[1], a.shape[0]],
            "port_size": [b.shape[1], b.shape[0]]}


def regions(mask: np.ndarray, gap: int, pad: int) -> list[list[int]]:
    """Boxes (x0, y0, x1, y1) of the groups of True pixels; groups closer than `gap` pixels join, boxes grow by
    `pad`, and boxes that then overlap merge."""
    h, w = mask.shape
    cell = max(2, gap // 2)
    ch, cw = -(-h // cell), -(-w // cell)
    grid = np.zeros((ch, cw), bool)
    ys, xs = np.nonzero(mask)
    grid[ys // cell, xs // cell] = True
    seen = np.zeros_like(grid)
    boxes = []
    for sy, sx in zip(*np.nonzero(grid)):
        if seen[sy, sx]:
            continue
        q = deque([(sy, sx)])
        seen[sy, sx] = True
        cells = []
        while q:
            y, x = q.popleft()
            cells.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < ch and 0 <= nx < cw and grid[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        q.append((ny, nx))
        cy, cx = zip(*cells)
        y0, x0 = min(cy) * cell, min(cx) * cell
        sub = mask[y0:(max(cy) + 1) * cell, x0:(max(cx) + 1) * cell]
        yy, xx = np.nonzero(sub)
        y0, x0 = int(y0), int(x0)
        boxes.append([x0 + int(xx.min()), y0 + int(yy.min()), x0 + int(xx.max()) + 1, y0 + int(yy.max()) + 1])
    boxes = [[max(0, b[0] - pad), max(0, b[1] - pad), min(w, b[2] + pad), min(h, b[3] + pad)] for b in boxes]
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    del boxes[j]
                    merged = True
                    break
            if merged:
                break
    return boxes


def _padded(path: Path, w: int, h: int) -> Image.Image:
    im = Image.open(path).convert("RGB")
    out = Image.new("RGB", (w, h), PAD_FILL)
    out.paste(im, (0, 0))
    return out


def tiles(box, limit: int) -> list[tuple[list[int], str]]:
    """Cut box (x0, y0, x1, y1) into boxes whose two-half crop fits in limit x limit; each with its layout,
    `side` (production left, port right) or `stacked` (production above port)."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    half = max(1, (limit - SHEET_GAP) // 2)
    if 2 * w + SHEET_GAP <= limit and h <= limit:
        return [(list(box), "side")]
    if w <= limit and 2 * h + SHEET_GAP <= limit:
        return [(list(box), "stacked")]
    tw, th, layout = (min(w, limit), half, "stacked") if w >= h else (half, min(h, limit), "side")
    return [([x, y, min(x + tw, x1), min(y + th, y1)], layout)
            for y in range(y0, y1, th) for x in range(x0, x1, tw)]


def region_crops(up_png: Path, port_png: Path, out_dir: Path, sid: str, threshold: int, limit: int,
                 gap: int = 12, pad: int = 6, most: int = 20) -> tuple[int, list[dict]]:
    """Write `crop-<sid>-<n>.png` (production and port halves, at native scale, within limit x limit) for the
    largest visibly differing regions, a region too large cut into tiles. Returns (number of regions and tiles,
    [{file, box, px, layout}] of the ones written, largest first)."""
    a, b = _rgb(up_png), _rgb(port_png)
    mask = _delta(a, b) > threshold
    if not mask.any():
        return 0, []
    boxes = [tile for bx in regions(mask, gap, pad) for tile in tiles(bx, limit)]
    boxes = [(bx, lay, int(mask[bx[1]:bx[3], bx[0]:bx[2]].sum())) for bx, lay in boxes]
    boxes = sorted((t for t in boxes if t[2]), key=lambda t: -t[2])
    h, w = mask.shape
    ia, ib = _padded(up_png, w, h), _padded(port_png, w, h)
    out = []
    for n, ((x0, y0, x1, y1), layout, px) in enumerate(boxes[:most], 1):
        ca, cb = (im.crop((x0, y0, x1, y1)) for im in (ia, ib))
        if layout == "side":
            sheet = Image.new("RGB", (ca.width * 2 + SHEET_GAP, ca.height), SHEET_FILL)
            sheet.paste(cb, (ca.width + SHEET_GAP, 0))
        else:
            sheet = Image.new("RGB", (ca.width, ca.height * 2 + SHEET_GAP), SHEET_FILL)
            sheet.paste(cb, (0, ca.height + SHEET_GAP))
        sheet.paste(ca, (0, 0))
        name = f"crop-{sid}-{n}.png"
        sheet.save(Path(out_dir) / name, optimize=True)
        out.append({"file": name, "box": [x0, y0, x1, y1], "px": px, "layout": layout})
    return len(boxes), out
