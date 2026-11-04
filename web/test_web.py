"""The web app, end to end, with the real tools: wrangler serves it on its local D1 (loaded with the seed files), and Chromium
clicks through it as a person would. Then the change made on D1 travels back: push refuses to wipe it, pull takes it into
the working database, save checks it and writes the seed files, and push is allowed again.

    python test_web.py        (mise run web:test)

It changes the trial's seed files (out/etl/data) and its local D1; `mise run etl:run` and `etl:d1` make them afresh.
"""
import re, shutil, socket, subprocess, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ETL = HERE.parent / "etl"
sys.path.insert(0, str(ETL))
from migrate import DATA, load            # noqa: E402
from d1 import query                      # noqa: E402
import edit                               # noqa: E402

READY_SECONDS = 60                        # how long wrangler may take to start serving
WAIT_MS = 10_000                          # how long the page may take to show a change
results = []


def report(good, what):
    results.append(bool(good))
    print(f"{'OK     ' if good else 'MISSED '}  {what}")


def run(*cmd):
    return subprocess.run(cmd, cwd=ETL, capture_output=True, text=True)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    shutil.rmtree(edit.WORK, ignore_errors=True)
    shutil.rmtree(ETL / ".wrangler", ignore_errors=True)            # a fresh local D1, holding exactly the seed files
    pushed = run("python", "d1.py", "push", "--local")
    report(pushed.returncode == 0, "the local D1 gets the migrations and the seed files")
    port = free_port()
    server = subprocess.Popen(["wrangler", "dev", "--config", "wrangler.toml", "--ip", "127.0.0.1", "--port", str(port)],
                              cwd=ETL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(READY_SECONDS):
            try:
                urllib.request.urlopen(url, timeout=1); break
            except OSError:
                time.sleep(1)
        to_buy = load().execute("SELECT count(*) FROM materials_line l JOIN materials_status s ON s.code = l.status WHERE s.to_buy").fetchone()[0]
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_context().new_page()
            page.goto(url)
            rows = page.locator("#lines tbody tr")
            rows.first.wait_for(timeout=WAIT_MS)                                  # HTMX 4 loads the list after the page
            report(rows.count() == to_buy, f"the page loads the list through HTMX: {rows.count()} lines still to buy, as the data has")
            heading = page.locator("h1").inner_text()
            words = load().execute("SELECT group_concat(name, ' / ') FROM (SELECT name FROM materials_section_text t "
                                   "JOIN common_language l ON l.code = t.lang ORDER BY l.pos)").fetchone()[0]
            report(heading == words, f"its wording comes from the database: {heading!r}")
            before = page.context.cookies()
            b0 = next((c["value"] for c in before if c["name"] == "d1-bookmark"), None)
            report(b0, f"the visitor gets a D1 bookmark in a cookie ({b0})")
            first = page.locator("#lines tbody tr").first
            name = first.locator("td").first.inner_text().splitlines()[-1]
            line = re.search(r"/ui/lines/([0-9a-f-]{36})/", first.locator("button").get_attribute("hx-post"))[1]
            first.locator("button").click()
            page.wait_for_function(f"document.querySelectorAll('#lines tbody tr').length === {to_buy - 1}", timeout=WAIT_MS)
            report(rows.count() == to_buy - 1 and name not in page.locator("#lines tbody").inner_text(),
                   f"marking {name!r} on site writes to D1 and the list that comes back no longer has it — read in the same session")
            b1 = next(c["value"] for c in page.context.cookies() if c["name"] == "d1-bookmark")
            report(b1 > b0, f"the write moves the bookmark forward ({b0} → {b1})")
            # a later visit with that bookmark: the session starts at least there, so the change is in what it reads
            later = browser.new_context()
            later.add_cookies([{"name": "d1-bookmark", "value": b1, "url": url}])
            p2 = later.new_page(); p2.goto(url)
            p2.locator("#lines tbody tr").first.wait_for(timeout=WAIT_MS)
            report(p2.locator("#lines tbody tr").count() == to_buy - 1, "a later visit carrying the bookmark reads its own write")
            # the same press again (a double click, a retried request): nothing changes, and the page says so
            again = page.request.post(f"{url}/ui/lines/{line}/on-site")
            report(again.status == 409 and page.request.get(f"{url}/ui/lines").text().count("<tr>") - 2 == to_buy - 1,
                   "pressing it again changes nothing (409), and the list stays as it is")
            # the recursive pages, read in the same session (its bookmark now past the write)
            db = load()
            tree = db.execute("SELECT depth, item FROM room_show_fitting WHERE lang = 'en'").fetchall()
            page.locator("nav button").nth(1).click()
            page.locator("#fittings li").first.wait_for(timeout=WAIT_MS)
            items = page.locator("#fittings li")
            shown = [(items.nth(i).get_attribute("style"), items.nth(i).locator(".en").inner_text()) for i in range(items.count())]
            report([(f"margin-left: {d * 1.5:g}rem", n) for d, n in tree] == shown,
                   f"the schedule of fittings shows every chain as a tree, indented by depth ({len(tree)} items, from the recursive view)")
            page.locator("nav button").nth(2).click()
            page.locator("#works h3").first.wait_for(timeout=WAIT_MS)
            phases_n = db.execute("SELECT count(*) FROM phases_phase").fetchone()[0]
            steps = db.execute("SELECT number, text FROM phases_show_text WHERE kind = 'step' AND lang = 'en'").fetchall()
            cells = page.locator("#works tbody tr")
            got = [(cells.nth(i).locator("td").nth(0).inner_text(), cells.nth(i).locator("td").nth(2).inner_text()) for i in range(cells.count())]
            report(page.locator("#works h3").count() == phases_n and got == steps and "{" not in page.locator("#works").inner_text(),
                   f"the scope of works shows {phases_n} phases and {len(steps)} steps, every reference filled (the recursive view)")
            report(page.locator("h1, h2").count() == 1, "each page has one heading (the swap replaces the page, it doesn't stack them)")
            browser.close()
        paid = query("--local", f"SELECT s.paid, s.on_site, s.to_buy FROM materials_line l JOIN materials_status s ON s.code = l.status WHERE l.id = '{line}'")[0]
        report(paid == {"paid": 1, "on_site": 1, "to_buy": 0}, "on D1 the line's status is now the one that is paid and on site")
        checked = run("python", "d1.py", "check", "--local")
        report(checked.returncode == 0, "D1's own check views find no problem after the app's write")
    finally:
        server.terminate(); server.wait()
    # ---------- the change goes back to the seed files
    refused = run("python", "d1.py", "push", "--local")
    report(refused.returncode != 0 and "git has never had" in refused.stdout + refused.stderr,
           "db:push refuses to wipe a change made on D1")
    pulled = run("python", "d1.py", "pull", "--local")
    report(pulled.returncode == 0 and "UPDATE materials_line SET status=" in pulled.stdout and "Taken into" in pulled.stdout,
           "db:pull shows the change as one row, and takes it into the working database")
    found, _ = edit.save_working()
    status = load().execute(f"SELECT s.paid FROM materials_line l JOIN materials_status s ON s.code = l.status WHERE l.id = '{line}'").fetchone()
    report(found == [] and status == (1,), "db:save checks it and writes the seed files: they now hold the line as bought")
    again = run("python", "d1.py", "push", "--local")
    report(again.returncode == 0, "db:push is allowed again: D1 holds what the seed files hold")
    shutil.rmtree(edit.WORK, ignore_errors=True)
    print(f"\n{sum(results)}/{len(results)} as they should be  (the trial's seed files now hold the change: mise run etl:run makes them afresh)")
    return all(results)


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
