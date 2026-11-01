"""The drawings' design checks — how each drawing reads: problems in how a drawing is laid out, measured in
Chromium, the browser that prints the PDF, on the drawings as drawn (svg text, with style.css).

    drawing_design_checks.check(svgs, style)   # [(index of the drawing, kind, what, other)]

The checks, each worded by its label in room.toml:
  - something drawn runs off the edge of its drawing                                warn_off_drawing
  - two words or tags drawn over each other                                         warn_overlap
  - a label outside the drawing's face (a wall name, a joint mark, a heading …) with
    a line or a fill drawn through it                                               warn_covered

`what` and `other` are what each thing says: a text's own words, a tag's number, or for a line the tag it
belongs to (its data-of). A line that belongs to nothing is named "" — the wording says so.
It knows nothing about bathrooms or the parts; it reads the drawings it is handed.
"""
from common import chromium

OFF, OVERLAP, COVERED = "off", "overlap", "covered"

# What the browser measures on one drawing (the drawing is the page's only svg). Every box is in the
# drawing's own units, rotation included. A word is a text, or a tag or number with its text inside.
MEASURE = """async () => {
  const svg = document.querySelector('svg'), vb = svg.viewBox.baseVal, toUser = svg.getScreenCTM().inverse();
  const MARKERS = ['tag', 'number'], INSIDE = ['tag-text', 'number-text'];
  const WORD_GAP = WORD_GAP_, LETTERS = LETTERS_, EDGE = EDGE_, INK = INK_;
  const CLEAR = ['title', 'subtitle', 'heading', 'key', 'legend', 'legend-note', 'wall-name', 'side-name',
                 'joint-text', 'tick-text', 'warning', 'ok'];
  const is = (e, list) => list.some(c => e.classList.contains(c));
  const corners = (e, letters) => { const b = e.getBBox(), m = toUser.multiply(e.getScreenCTM());  // its own box, turned;
    const t = letters && e.tagName === 'text' ? b.height * (1 - LETTERS) / 2 : 0;    // for a text's letters, its font box
    return [[b.x, b.y + t], [b.x + b.width, b.y + t], [b.x + b.width, b.y + b.height - t], [b.x, b.y + b.height - t]]  // less the space above and below
      .map(([x, y]) => { const q = new DOMPoint(x, y).matrixTransform(m); return [q.x, q.y]; }); };
  const box = e => { const p = corners(e);
    return [Math.min(...p.map(q => q[0])), Math.min(...p.map(q => q[1])), Math.max(...p.map(q => q[0])), Math.max(...p.map(q => q[1]))]; };
  // Two turned boxes come within `gap` of each other when no edge direction of either holds them that far apart
  // (the separating axis test).
  const near = (a, b, gap) => [a, b].every(poly => poly.every((p, i) => {
    const q = poly[(i + 1) % 4], nx = q[1] - p[1], ny = p[0] - q[0], len = Math.hypot(nx, ny);
    const pa = a.map(([x, y]) => (x * nx + y * ny) / len), pb = b.map(([x, y]) => (x * nx + y * ny) / len);
    return Math.max(Math.min(...pa), Math.min(...pb)) - Math.min(Math.max(...pa), Math.max(...pb)) < gap; }));
  const inside = (poly, x, y) => poly.every((p, i) => { const q = poly[(i + 1) % 4];
    return (q[0] - p[0]) * (y - p[1]) - (q[1] - p[1]) * (x - p[0]) >= 0; }) ||
    poly.every((p, i) => { const q = poly[(i + 1) % 4]; return (q[0] - p[0]) * (y - p[1]) - (q[1] - p[1]) * (x - p[0]) <= 0; });
  const name = e => e.tagName === 'text' ? e.textContent : is(e, MARKERS) ? e.nextElementSibling.textContent : (e.dataset.of || '');
  const all = [...svg.querySelectorAll('*')].filter(e => !e.classList.contains('paper'));
  const out = [];
  for (const e of all) { const [x0, y0, x1, y1] = box(e);
    if (x0 < -0.5 || y0 < -0.5 || x1 > vb.width + 0.5 || y1 > vb.height + 0.5) out.push(['off', name(e), '']); }
  const words = all.filter(e => (e.tagName === 'text' && !is(e, INSIDE)) || is(e, MARKERS)), wc = words.map(e => corners(e, true));
  for (let i = 0; i < words.length; i++) for (let j = i + 1; j < words.length; j++)
    if (near(wc[i], wc[j], WORD_GAP)) out.push(['overlap', name(words[i]), name(words[j])]);
  // Everything but the words, drawn on its own; then whatever shows under a label that needs clear ground.
  const clone = svg.cloneNode(true), live = [...svg.querySelectorAll('*')], copy = [...clone.querySelectorAll('*')];
  live.forEach((e, k) => { const cs = getComputedStyle(e);
    for (const p of ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-dasharray', 'opacity'])
      copy[k].style.setProperty(p, cs.getPropertyValue(p)); });
  copy.forEach(c => { if (c.tagName === 'text' || is(c, MARKERS)) c.remove(); });
  const S = 2, img = new Image();
  img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(clone));
  await img.decode();
  const cv = document.createElement('canvas'); cv.width = vb.width * S; cv.height = vb.height * S;
  const g = cv.getContext('2d'); g.drawImage(img, 0, 0, cv.width, cv.height);
  const px = g.getImageData(0, 0, cv.width, cv.height).data;
  for (const e of all.filter(e => e.tagName === 'text' && is(e, CLEAR))) {
    const [x0, y0, x1, y1] = box(e), poly = corners(e), m = 1 / S; let n = 0;
    for (let y = Math.max(0, Math.ceil(y0 * S)); y < Math.min(cv.height, y1 * S); y++)
      for (let x = Math.max(0, Math.ceil(x0 * S)); x < Math.min(cv.width, x1 * S); x++) {
        const k = (y * cv.width + x) * 4;
        if (Math.min(px[k], px[k + 1], px[k + 2]) < INK && inside(poly, x * m, y * m)
            && [[1, 0], [-1, 0], [0, 1], [0, -1]].every(([dx, dy]) => inside(poly, x * m + dx * EDGE, y * m + dy * EDGE))) n++; }
    if (n) out.push(['covered', name(e), '']); }
  return out;
}"""

WORD_GAP = 4     # units kept clear between any two words or tags, so each reads on its own
LETTERS = 0.6    # how much of a text's font box (top to bottom) its letters take; the rest is space above and below
EDGE = 1         # units in from a label's edge where a line may graze it without counting
INK = 230        # a pixel darker than this (0–255, in any colour) is something drawn; the paper is white

_page = []


def page():
    """One page in the run's Chromium, kept for every check this run makes (starting it is the slow part)."""
    if not _page:
        _page.append(chromium().new_page())
    return _page[0]


def check(svgs, style):
    """Every layout problem on every drawing: [(index of the drawing, kind, what, other)], each found once."""
    p, out = page(), []
    for i, svg in enumerate(svgs):
        p.set_content(f'<style>{style}</style><section class="drawing">{svg}</section>')
        for kind, what, other in p.evaluate(MEASURE.replace("WORD_GAP_", str(WORD_GAP)).replace("LETTERS_", str(LETTERS)).replace("EDGE_", str(EDGE))
                                           .replace("INK_", str(INK))):
            if (i, kind, what, other) not in out:
                out.append((i, kind, what, other))
    return out
