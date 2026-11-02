// The quote's web app: a Hono Worker on Cloudflare D1, with HTMX 4 in the page.
//
// The example, off the real data: the materials list still to buy (each product in Thai and English, its quantity, its
// price, and the running total still to buy, worked out by D1 with a window function), with a button on each line to mark
// it on site. Pressing it writes to D1 and returns the fresh list.
//
// Read replicas: every request runs in a D1 session (the Sessions API). The session starts from the bookmark in the
// visitor's cookie, and the request hands back the session's latest bookmark in that cookie, so each visitor's reads only
// go forward and always include their own writes — even when a read is served by a replica that is behind the primary.
// Writes always go to the primary. Without a cookie, a session starts "first-unconstrained" (the nearest copy).
//
// Every word on the page comes from the database (the materials part's labels, symbols and section text, README rule 1):
// this file holds layout only. What a status means is read from its flags, never from its code (the plan, decision 5).
import { Hono, type Context } from "hono";
import { getCookie, setCookie } from "hono/cookie";
import { html, raw } from "hono/html";
import htmx from "htmx.org/dist/htmx.min.js";   // served from here, pinned in package.json: no third-party script host

type Session = D1DatabaseSession;
type Env = { Bindings: { DB: D1Database }; Variables: { session: Session } };

const BOOKMARK = "d1-bookmark";      // the cookie that carries the visitor's D1 bookmark from one request to the next
const FIRST = "first-unconstrained"; // a session with no bookmark yet starts at the nearest copy of the database
const BOOKMARK_MAX_AGE = 60 * 60 * 24 * 30;   // seconds a bookmark is kept (a month: it only ever moves forward)
const LANGS = ["th", "en"] as const; // the order the page gives the two languages in (README rule 4: Thai first)

const app = new Hono<Env>();

// ---------- every request: a D1 session from the visitor's bookmark, and the latest bookmark handed back
app.use("*", async (c, next) => {
  c.set("session", c.env.DB.withSession(getCookie(c, BOOKMARK) || FIRST));
  await next();
  const bookmark = session(c).getBookmark();
  if (bookmark) {
    setCookie(c, BOOKMARK, bookmark, { path: "/", httpOnly: true, secure: true, sameSite: "Strict", maxAge: BOOKMARK_MAX_AGE });
  }
});
const session = (c: Context<Env>): Session => c.get("session");

// ---------- the wording, from the materials part of the database
type Words = { label: (code: string) => string; symbol: (code: string) => string; section: string };

async function words(db: Session): Promise<Words> {
  const [labels, symbols, section] = await db.batch([
    db.prepare("SELECT code, lang, text FROM materials_label"),
    db.prepare("SELECT code, value FROM materials_symbol"),
    db.prepare("SELECT lang, name FROM materials_section_text"),
  ]);
  const text = new Map((labels.results as { code: string; lang: string; text: string }[]).map((r) => [`${r.code}/${r.lang}`, r.text]));
  const marks = new Map((symbols.results as { code: string; value: string }[]).map((r) => [r.code, r.value]));
  const names = new Map((section.results as { lang: string; name: string }[]).map((r) => [r.lang, r.name]));
  return {
    label: (code) => LANGS.map((l) => text.get(`${code}/${l}`)).join(" / "),   // a heading: "Thai / English"
    symbol: (code) => marks.get(code) ?? "",
    section: LANGS.map((l) => names.get(l)).join(" / "),
  };
}

// ---------- the lines still to buy, with the running total still to buy (a window function, run by D1)
type Line = { id: string; th: string; en: string; n: number; unit_th: string; unit_en: string; price: number; approx: number;
              running: number; approx_so_far: number; round_approx: number };

const STILL_TO_BUY = `
  SELECT l.id, th.name AS th, en.name AS en, l.n, uth.name AS unit_th,
         CASE WHEN l.n = 1 THEN uen.name ELSE coalesce(pl.many, uen.name) END AS unit_en,   -- English's plural, as the PDF writes it
         p.price, p.approx,
         sum(l.n * p.price) OVER running AS running, max(p.approx) OVER running AS approx_so_far,
         (SELECT round_approx FROM materials_setting) AS round_approx
  FROM materials_line l
  JOIN materials_status s ON s.code = l.status AND s.to_buy
  JOIN materials_product p ON p.id = l.product
  JOIN materials_work_section ws ON ws.id = l.work_section
  JOIN materials_product_text th ON th.product = p.id AND th.lang = 'th'
  JOIN materials_product_text en ON en.product = p.id AND en.lang = 'en'
  JOIN materials_unit_text uth ON uth.unit = p.unit AND uth.lang = 'th'
  JOIN materials_unit_text uen ON uen.unit = p.unit AND uen.lang = 'en'
  LEFT JOIN materials_unit_plural pl ON pl.unit = p.unit AND pl.lang = 'en'
  WINDOW running AS (ORDER BY ws.pos, p.pos, l.pos)
  ORDER BY ws.pos, p.pos, l.pos`;

// a line bought is on site: the status that is paid and on site, not to buy — chosen by its flags. Only a line still to buy,
// whose product has a price and a shop (what the paid status needs, decision 5's rules), is moved, so the write can't
// leave a problem behind
const MARK_ON_SITE = `
  UPDATE materials_line
  SET status = (SELECT code FROM materials_status WHERE paid AND on_site AND NOT to_buy ORDER BY pos LIMIT 1)
  WHERE id = ?
    AND status IN (SELECT code FROM materials_status WHERE to_buy)
    AND product IN (SELECT p.id FROM materials_product p JOIN materials_product_shop ps ON ps.product = p.id WHERE p.price IS NOT NULL)`;

const money = (w: Words, v: number) => `${w.symbol("currency")}${Math.round(v).toLocaleString("en-US")}`;

// the total still to buy, as the PDF gives it: rounded and marked "about" if any price in it is approximate
const total = (w: Words, last?: Line) =>
  !last ? money(w, 0)
  : last.approx_so_far ? `${w.label("about")} ${money(w, Math.round(last.running / last.round_approx) * last.round_approx)}`
  : money(w, last.running);

async function lineList(db: Session) {
  const [w, { results }] = await Promise.all([words(db), db.prepare(STILL_TO_BUY).all<Line>()]);
  return html`<table id="lines">
  <thead><tr><th>${w.label("item")}</th><th>${w.label("qty")}</th><th>${w.label("price")}</th><th>${w.label("still_to_buy")}</th><th>${w.label("on_site")}</th></tr></thead>
  <tbody>${results.map((r) => html`
    <tr>
      <td>${r.th}<br><span class="en">${r.en}</span></td>
      <td>${r.n} ${r.unit_th} ${w.symbol("times")} ${money(w, r.price)}<br><span class="en">${r.n} ${r.unit_en} ${w.symbol("times")} ${money(w, r.price)}</span></td>
      <td>${r.approx ? w.label("approx") + " " : ""}${money(w, r.price * r.n)}</td>
      <td>${money(w, r.running)}</td>
      <td><button hx-post="/ui/lines/${r.id}/on-site" hx-target="#lines" hx-swap="outerHTML">${w.symbol("on_site")}</button></td>
    </tr>`)}
  </tbody>
  <tfoot><tr><td colspan="3">${w.label("still_to_buy")}</td><td>${total(w, results.at(-1))}</td><td></td></tr></tfoot>
</table>`;
}

// ---------- the page, and its two requests
app.get("/", async (c) => {
  const w = await words(session(c));
  return c.html(html`<!doctype html>
<html lang="th">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${w.section}</title>
  <script src="/htmx.js"></script>
  <style>
    body { font-family: system-ui, sans-serif; margin: 1rem; max-width: 60rem; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border-bottom: 1px solid #ddd; padding: .4rem; text-align: left; vertical-align: top; }
    td:nth-child(n+2):nth-child(-n+4) { text-align: right; white-space: nowrap; }
    .en { color: #555; font-size: .9em; }
    button { font-size: 1.1rem; min-width: 3rem; }
  </style>
</head>
<body>
  <h1>${w.section}</h1>
  <div hx-get="/ui/lines" hx-trigger="load" hx-swap="outerHTML">${w.symbol("none")}</div>
</body>
</html>`);
});

app.get("/ui/lines", async (c) => c.html(await lineList(session(c))));

app.post("/ui/lines/:id/on-site", async (c) => {
  const db = session(c);
  const done = await db.prepare(MARK_ON_SITE).bind(c.req.param("id")).run();
  // the list is read in the same session, after the write: it includes it, wherever the read is served from
  return c.html(await lineList(db), done.meta.changes === 1 ? 200 : 409);
});

app.get("/htmx.js", (c) => c.body(htmx, 200, { "content-type": "text/javascript; charset=utf-8", "cache-control": "public, max-age=31536000, immutable" }));

app.onError((err, c) => {
  console.error(err);                          // for whoever runs it; the page gets the bare status (HTMX 4 swaps error responses)
  return c.text(String(c.res.status || 500), 500);
});

export default app;
