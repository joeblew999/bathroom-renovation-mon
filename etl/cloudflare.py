"""Make sure everything the quote needs on Cloudflare exists, the way it should — run it again any time; it changes only
what isn't so yet. With the Cloudflare CLI (`cf`, pinned in mise.toml), logged in by `mise run cf:login`.

    python cloudflare.py login                 (mise run cf:login)
    python cloudflare.py provision [--dry-run] (mise run cf:provision)
    python cloudflare.py access on|off|status  (mise run cf:access-on, cf:access-off, cf:access-status)
    python cloudflare.py deploy [--public]     (mise run web:deploy)

access: Cloudflare Access in front of the web app — on, only the emails in CF_ACCESS_EMAILS (mise.toml's [env]) can open
it, after signing in at the account's Access login; off, anyone with the address can. Toggled any time; the app doesn't
change. deploy: refuses while Access is off (--public deploys anyway), then checks the address sends a visitor to the
Access login — and if it doesn't, takes the app off Cloudflare at once (D1's data stays).

login: logs in cf (a profile for this project, bound to the repo) and wrangler, each by device code — and prints each
link with its code already in it (…?user_code=…), so approving is one tap, from any device.

  1. the D1 database bathroom-quote: made if it isn't there, its primary near Thailand (apac), with read replication on
     (mode auto: Cloudflare places read replicas round the world, and the web app's sessions read from the nearest);
     if it is there, read replication is switched on if it isn't already;
  2. its id written into etl/wrangler.toml — commit it: it isn't a secret, and every clone then uses the same database.
--dry-run shows the requests cf would make, and changes nothing (it needs no login).
"""
import json, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE / "wrangler.toml"
NAME = re.search(r'database_name = "([^"]+)"', CONFIG.read_text())[1]
PRIMARY = "apac"            # where the primary is made: Asia-Pacific, near the site (Thailand)
REPLICATION = "auto"        # read replicas, placed by Cloudflare
PLACEHOLDER = "00000000-0000-0000-0000-000000000000"
WORKER = re.search(r'^name = "([^"]+)"', CONFIG.read_text(), re.M)[1]
WORKERS_SUBDOMAIN = "gedw99"        # the account's workers.dev subdomain: the app is at <worker>.<subdomain>.workers.dev
HOST = f"{WORKER}.{WORKERS_SUBDOMAIN}.workers.dev"
SESSION = "24h"                     # how long a sign-in lasts
ACCESS_LOGIN = "cloudflareaccess.com"   # where Access sends a visitor who hasn't signed in


DEVICE_URL = re.compile(r"https://dash\.cloudflare\.com/oauth2/device\S*")
DEVICE_CODE = re.compile(r"^\s*([A-Za-z0-9-]{6,12})\s*$")    # the code, on a line of its own
PROFILE = "bathroom-quote"  # cf's login for this project


def device_login(cmd):
    """Run a device-code login, passing its output through, and print its link with the code in it as soon as both appear."""
    proc = subprocess.Popen(cmd, cwd=HERE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    url = code = None
    for line in proc.stdout:
        print(line, end="", flush=True)
        url = url or (DEVICE_URL.search(line) or [None])[0]
        if url and not code and (m := DEVICE_CODE.match(line)) and m[1] not in url:
            code = m[1]
            link = url if "user_code=" in url else f"{url.split('/verify')[0]}?user_code={code}"   # the form Cloudflare documents: /oauth2/device?user_code=…
            print(f"\n>>> Approve here (the code is in the link): {link}\n", flush=True)
    if proc.wait():
        sys.exit(f"ERROR: {' '.join(cmd[:3])} didn't log in")


def login():
    device_login(["cf", "auth", "create", PROFILE, "--no-browser"])
    cf("auth", "activate", PROFILE, str(HERE.parent))       # bound to this repo: cf uses it here and in every folder below
    device_login(["wrangler", "login", "--device", "--browser=false"])
    print("Logged in: cf (profile bathroom-quote, bound to this repo) and wrangler. Next: mise run cf:provision")


def cf(*args):
    run = subprocess.run(["cf", *args], capture_output=True, text=True)
    if run.returncode:
        sys.exit(f"ERROR: cf {' '.join(args)} failed:\n{run.stdout[-2000:]}{run.stderr[-2000:]}")
    out = run.stdout.strip()
    try:
        return json.loads(out) if out else None
    except json.JSONDecodeError:
        return out


def items(got):
    """The databases in cf's answer, however it wraps them."""
    if isinstance(got, dict):
        got = got.get("result", got.get("results", got.get("databases", [got])))
    return got if isinstance(got, list) else []


def provision(dry):
    if dry:
        print(json.dumps(cf("d1", "create", "--name", NAME, "--primary-location-hint", PRIMARY,
                            "--read-replication-mode", REPLICATION, "--dry-run"), indent=2))
        print("(dry run: nothing made; with a login, an existing database would only have read replication switched on)")
        return
    who = cf("auth", "whoami")
    if isinstance(who, dict) and not who.get("authenticated", True):
        sys.exit("ERROR: not logged in to Cloudflare: run `mise run cf:login` first")
    found = [d for d in items(cf("d1", "list", "--name", NAME)) if d.get("name") == NAME]
    if not found:
        made = cf("d1", "create", "--name", NAME, "--primary-location-hint", PRIMARY, "--read-replication-mode", REPLICATION)
        db = made.get("result", made) if isinstance(made, dict) else {}
        print(f"Made the D1 database {NAME} ({db.get('uuid')}), primary in {PRIMARY}, read replication {REPLICATION}.")
    else:
        db = found[0]
        detail = cf("d1", "get", db["uuid"])
        detail = detail.get("result", detail) if isinstance(detail, dict) else {}
        mode = (detail.get("read_replication") or {}).get("mode")
        if mode != REPLICATION:
            cf("d1", "edit", db["uuid"], "--read-replication-mode", REPLICATION)
            print(f"The D1 database {NAME} ({db['uuid']}) had read replication {mode}: switched it to {REPLICATION}.")
        else:
            print(f"The D1 database {NAME} ({db['uuid']}) is there, with read replication {REPLICATION}.")
    uuid = db.get("uuid")
    if not uuid:
        sys.exit(f"ERROR: cf gave no id for {NAME}: {db}")
    text = CONFIG.read_text()
    now = re.search(r'database_id = "([^"]+)"', text)[1]
    if now != uuid:
        if now != PLACEHOLDER:
            sys.exit(f"ERROR: etl/wrangler.toml names another database ({now}), not {NAME} ({uuid}): check which is meant")
        CONFIG.write_text(text.replace(f'database_id = "{PLACEHOLDER}"   # not made yet: db:push and db:pull refuse until the real id is here',
                                       f'database_id = "{uuid}"   # made by `mise run cf:provision` (read replication {REPLICATION})'))
        print("Wrote its id into etl/wrangler.toml — commit it. Then `mise run db:push` fills it, `mise run web:deploy` puts the app on it.")


def access_app():
    """The Access application in front of the app's address, or None."""
    return next((a for a in items(cf("zero-trust", "access", "applications", "list", "--domain", HOST)) if a.get("domain") == HOST), None)


def emails():
    import os
    got = [e.strip() for e in os.environ.get("CF_ACCESS_EMAILS", "").split(",") if e.strip()]
    if not got:
        sys.exit("ERROR: CF_ACCESS_EMAILS (mise.toml's [env]) names nobody to let in")
    return got


def access(what):
    app = access_app()
    if what == "status":
        if not app:
            print(f"Access is OFF: anyone with the address can open https://{HOST}")
        else:
            who = [i.get("email", {}).get("email") for p in app.get("policies", []) for i in p.get("include", [])]
            print(f"Access is ON at https://{HOST}: only {', '.join(w for w in who if w) or '(see the policy)'} can open it")
        return bool(app)
    if what == "on":
        if app:
            print(f"Access is already on at https://{HOST}"); return True
        body = {"name": WORKER, "type": "self_hosted", "domain": HOST, "session_duration": SESSION, "app_launcher_visible": False,
                "policies": [{"name": "owner", "decision": "allow", "include": [{"email": {"email": e}} for e in emails()]}]}
        cf("zero-trust", "access", "applications", "create", "--body", json.dumps(body))
        print(f"Access is ON at https://{HOST}: only {', '.join(emails())} can open it")
        return True
    if what == "off":
        if app:
            cf("zero-trust", "access", "applications", "delete", app["id"])
        print(f"Access is OFF: anyone with the address can open https://{HOST}")
        return False
    sys.exit(__doc__)


def guarded(url):
    """Whether the address sends a visitor who hasn't signed in to the Access login."""
    import urllib.request, urllib.error
    class Stop(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k): return None
    try:
        r = urllib.request.build_opener(Stop).open(url, timeout=20)
        return False, f"{r.status}, the app itself"
    except urllib.error.HTTPError as e:
        where = e.headers.get("Location", "")
        return ACCESS_LOGIN in where, f"{e.code} to {where or 'nowhere'}"


def deploy(public):
    if PLACEHOLDER in CONFIG.read_text():
        sys.exit("ERROR: there is no D1 database yet: mise run cf:provision first")
    on = access("status")
    if not on and not public:
        sys.exit("ERROR: Access is off, so the app would be open to anyone: mise run cf:access-on first (or web:deploy --public)")
    run = subprocess.run(["wrangler", "deploy", "--config", str(CONFIG)], cwd=HERE, text=True)
    if run.returncode:
        sys.exit("ERROR: wrangler deploy failed")
    if on:
        import time
        for _ in range(10):                                  # Access and the new route can take a few seconds to agree
            ok, what = guarded(f"https://{HOST}/")
            if ok:
                break
            time.sleep(3)
        if not ok:
            subprocess.run(["wrangler", "delete", "--config", str(CONFIG), "--force"], cwd=HERE)   # the data in D1 stays
            sys.exit(f"ERROR: https://{HOST}/ answered {what}, not the Access login — the app is taken off Cloudflare again "
                     "(its data in D1 is untouched)")
        print(f"Deployed: https://{HOST}/ sends a visitor to the Access login ({what})")


if __name__ == "__main__":
    if sys.argv[1:2] == ["login"]:
        login()
    elif sys.argv[1:2] == ["access"] and sys.argv[2:3]:
        access(sys.argv[2])
    elif sys.argv[1:2] == ["deploy"]:
        deploy("--public" in sys.argv[2:])
    elif sys.argv[1:2] == ["provision"]:
        provision("--dry-run" in sys.argv[2:])
    else:
        sys.exit(__doc__)
