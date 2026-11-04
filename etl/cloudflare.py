"""Make sure everything the quote needs on Cloudflare exists, the way it should — run it again any time; it changes only
what isn't so yet. With the Cloudflare CLI (`cf`, pinned in mise.toml), logged in by `mise run cf:login`.

    python cloudflare.py provision [--dry-run]

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


if __name__ == "__main__":
    if sys.argv[1:2] != ["provision"]:
        sys.exit(__doc__)
    provision("--dry-run" in sys.argv[2:])
