"""A version's winget manifests, as a pull request to microsoft/winget-pkgs.

    GH_TOKEN=... python packaging/winget_submit.py 0.2.0 DIR [--dry-run]

DIR holds manifests/d/Divengine/Divide/<version>/ (packaging/manifests.py --winget DIR). The token is a
classic one with public_repo: the pull request comes from its user's fork of winget-pkgs (made if
missing, brought up to date first). Nothing is cloned (winget-pkgs is very large): the commit is made
with GitHub's API, on the fork's master. --dry-run says what it would send and stops.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

UPSTREAM = "microsoft/winget-pkgs"
FOLDER = "manifests/d/Divengine/Divide"
PACKAGE = "Divengine.Divide"


def gh(*args: str, body: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["gh", *args] + (["--input", "-"] if body is not None else [])
    return subprocess.run(cmd, input=json.dumps(body) if body is not None else None, text=True,
                          capture_output=True, check=check)


def api(path: str, method: str = "GET", body: dict | None = None):
    out = gh("api", "-X", method, path, body=body).stdout
    return json.loads(out) if out.strip() else None


def exists(path: str) -> bool:
    return gh("api", path, "--silent", check=False).returncode == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version")
    parser.add_argument("dir", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    source = args.dir / FOLDER / args.version
    files = sorted(source.glob("*.yaml"))
    if not files:
        print(f"no manifests in {source}", file=sys.stderr)
        return 1
    if exists(f"repos/{UPSTREAM}/contents/{FOLDER}/{args.version}"):
        print(f"winget-pkgs already has {PACKAGE} {args.version}.")
        return 0
    new = not exists(f"repos/{UPSTREAM}/contents/{FOLDER}")
    title = f"{'New package' if new else 'New version'}: {PACKAGE} version {args.version}"
    paths = [f"{FOLDER}/{args.version}/{f.name}" for f in files]
    if args.dry_run:
        print(title, *paths, sep="\n  ")
        return 0

    login = api("user")["login"]
    fork = f"{login}/winget-pkgs"
    if not exists(f"repos/{fork}"):
        gh("repo", "fork", UPSTREAM, "--clone=false")
        for _ in range(60):
            if exists(f"repos/{fork}"):
                break
            time.sleep(5)
    gh("repo", "sync", fork, "--source", UPSTREAM, "--branch", "master")
    base = api(f"repos/{fork}/git/ref/heads/master")["object"]["sha"]
    base_tree = api(f"repos/{fork}/git/commits/{base}")["tree"]["sha"]
    tree = api(f"repos/{fork}/git/trees", "POST", {
        "base_tree": base_tree,
        "tree": [{"path": p, "mode": "100644", "type": "blob", "content": f.read_text(encoding="utf-8")}
                 for p, f in zip(paths, files)]})
    commit = api(f"repos/{fork}/git/commits", "POST", {"message": title, "tree": tree["sha"], "parents": [base]})
    branch = f"{PACKAGE}-{args.version}"
    if exists(f"repos/{fork}/git/ref/heads/{branch}"):
        api(f"repos/{fork}/git/refs/heads/{branch}", "PATCH", {"sha": commit["sha"], "force": True})
    else:
        api(f"repos/{fork}/git/refs", "POST", {"ref": f"refs/heads/{branch}", "sha": commit["sha"]})
    body = f"divide {args.version}: https://github.com/divengine/divide/releases/tag/v{args.version}"
    print(gh("pr", "create", "--repo", UPSTREAM, "--base", "master", "--head", f"{login}:{branch}",
             "--title", title, "--body", body).stdout.strip())
    return 0


if __name__ == "__main__":
    sys.exit(main())
