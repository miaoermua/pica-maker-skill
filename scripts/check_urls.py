#!/usr/bin/env python3
"""HEAD every URL in the changed pica-pkg-repo jobs and report the ones that fail.

A URL that 404s does not stop the build: the fetcher logs a warning, the
validator passes, and the package ships without a container it declared. This
catches that before anything is committed.

    python3 check_urls.py                     # all jobs
    python3 check_urls.py --changed           # jobs touched by git
    python3 check_urls.py --mgr apk --arch x86_64
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

UA = {"User-Agent": "picapkgmaker-url-check"}


def urls_of(job: dict) -> list[str]:
    """Every download URL a job names, expanded for one architecture."""
    source = job.get("source") or {}
    templates = source.get("url_templates") or []
    if source.get("url_template"):
        templates.append(source["url_template"])
    for asset in (source.get("release") or {}).get("assets") or []:
        # A github job builds its URLs from the API; the tag/asset pair is
        # checked by the fetcher, so there is nothing to HEAD here.
        pass
    return [t for t in templates if "{" in t or "http" in t]


def expand(url: str, arch: str | None) -> str:
    if not arch:
        return url
    return url.replace("{arch}", arch).replace("{platform}", arch)


def changed_jobs(repo: pathlib.Path) -> list[pathlib.Path] | None:
    """Job paths the working tree or the last commit touched, else None."""
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", "ci"],
            cwd=repo, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    files = [f for f in out.stdout.split() if f.endswith("build.json")]
    if not files:
        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD", "--", "ci"],
            cwd=repo, capture_output=True, text=True, timeout=30,
        )
        files = [f for f in out.stdout.split() if f.endswith("build.json")]
    return [repo / f for f in files] or None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="pica-pkg-repo checkout")
    ap.add_argument("--changed", action="store_true", help="only jobs changed by git")
    ap.add_argument("--mgr", help="only this backend, e.g. apk")
    ap.add_argument("--arch", default="x86_64", help="architecture to expand {arch} with")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    jobs = sorted(repo.glob("ci/*/*/build.json"))
    if args.changed:
        picked = changed_jobs(repo)
        if picked:
            jobs = [p for p in picked if p.exists()]
    if args.mgr:
        jobs = [p for p in jobs if p.parts[-3] == args.mgr]
    if not jobs:
        print("no jobs found", file=sys.stderr)
        return 0

    total = failed = 0
    for path in jobs:
        job = json.loads(path.read_text())
        urls = urls_of(job)
        if not urls:
            continue
        broken = []
        for tpl in urls:
            if "{" in tpl and "{arch}" not in tpl and "{" not in tpl.replace("{arch}", ""):
                continue
            target = expand(tpl, args.arch)
            total += 1
            try:
                req = urllib.request.Request(target, method="HEAD", headers=UA)
                code = urllib.request.urlopen(req, timeout=25).status
            except urllib.error.HTTPError as err:
                code = err.code
            except Exception as err:  # noqa: BLE001 - report whatever happened
                code = type(err).__name__
            if code != 200:
                failed += 1
                broken.append((target, code))
        rel = path.relative_to(repo)
        if broken:
            print(f"  FAIL {rel}")
            for target, code in broken:
                print(f"       {code}  {target}")
        else:
            print(f"  ok   {rel}  ({len(urls)} url)")

    print(f"\n  {total} url checked, {failed} broken")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())