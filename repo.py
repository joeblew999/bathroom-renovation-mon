"""The repo's own chores, in Python, so a task stays one line and runs the same on macOS, Linux and Windows (mise.toml's
structure, held by mise-check: no shell logic in a task).

    python repo.py setup      (part of mise run root:setup) Chromium for the PDF; on GitHub's runner, its libraries too
    python repo.py lint       (mise run quote:lint) pyflakes on every Python file git tracks
    python repo.py publish    (mise run root:publish) push main — only from main, with nothing uncommitted, once the
                              structure check and quote:check pass; then GitHub builds and publishes

Messages are for whoever runs them: English only (README rule 1).
"""
import os, subprocess, sys

MAIN = "main"     # the branch that publishes


def run(*cmd, quiet=False):
    """Run a command; stop with its exit code if it fails."""
    done = subprocess.run(cmd, capture_output=quiet, text=True)
    if done.returncode:
        sys.exit(done.returncode)
    return done.stdout


def setup():
    run(sys.executable, "-m", "playwright", "install", "chromium")
    if os.environ.get("CI"):                 # GitHub's runner only: Chromium's Linux libraries and fonts (the Thai font too)
        run(sys.executable, "-m", "playwright", "install-deps", "chromium")


def lint():
    files = run("git", "ls-files", "*.py", quiet=True).split()
    run(sys.executable, "-m", "pyflakes", *files)


def publish():
    branch = run("git", "branch", "--show-current", quiet=True).strip()
    if branch != MAIN:
        sys.exit(f"ERROR: on {branch}, not {MAIN} — publish checks the files here and pushes {MAIN}, so it must be run on {MAIN}")
    if run("git", "status", "--porcelain", quiet=True).strip():
        sys.exit("ERROR: uncommitted changes or new files — commit them first, so what is checked is what is pushed")
    run("mise", "run", "root:check-mise")
    run("mise", "run", "quote:check")
    run("git", "push", "origin", MAIN)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    {"setup": setup, "lint": lint, "publish": publish}.get(what, lambda: sys.exit(__doc__))()
