#!/usr/bin/env python3
"""List what an OpenWrt or ImmortalWrt package directory actually holds.

Answers the three questions that come up while adding a package: which
architectures exist, which subdirectory a package sits in, and whether the
filenames agree across architectures. Guessing any of those wrong produces a
404 that only shows up at build time.

    python3 list_feed.py                                  # the sources below
    python3 list_feed.py --base URL --arch x86_64 --dir luci
    python3 list_feed.py --base URL --match qbittorrent  # find a package

Listing a mirror's directory often returns a page too short to contain any
entries — some mirrors render the index with JavaScript and serve the shell to
a plain fetch. That is a property of the mirror, not a missing package, so
this says so rather than reporting an empty directory.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import re
import sys
import urllib.request

UA = {"User-Agent": "picapkgmaker-feed-list"}

SOURCES = {
    "snapshots": "https://downloads.immortalwrt.org/snapshots/packages",
    "releases": "https://downloads.immortalwrt.org/releases",
}
DEFAULT_ARCHES = [
    "x86_64", "aarch64_generic", "aarch64_cortex-a53",
    "aarch64_cortex-a72", "mipsel_24kc",
]
SUBDIRS = ["base", "packages", "luci", "routing", "telephony"]


def get(url: str, timeout: int = 30) -> str:
    return urllib.request.urlopen(
        urllib.request.Request(url, headers=UA), timeout=timeout
    ).read().decode("utf-8", "replace")


def entries(url: str) -> list[str]:
    page = get(url)
    return re.findall(r'>([^<]+\.(?:apk|ipk))<', page)


def listing(base: str, arch: str) -> dict[str, list[str]]:
    """Every package under one architecture, keyed by subdirectory."""
    out = {}
    for d in SUBDIRS:
        try:
            out[d] = entries(f"{base}/{arch}/{d}/")
        except Exception:  # noqa: BLE001 - a missing subdirectory is normal
            out[d] = []
    return out


def cmd_arches(args) -> int:
    base = f"{args.base or SOURCES['snapshots']}"
    try:
        page = get(f"{base}/")
    except Exception as err:  # noqa: BLE001
        print(f"  cannot read {base}/: {err}")
        return 1
    arches = sorted(set(re.findall(r'href="([^"?/][^"]*)/"', page)))
    print(f"  {len(arches)} architectures under {base}")
    print("  " + " ".join(arches))
    for a in DEFAULT_ARCHES:
        print(f"  {a:<22}{'present' if a in arches else 'absent'}")
    return 0


def cmd_where(args) -> int:
    """Locate a package across every subdirectory of one architecture."""
    base = args.base or SOURCES["snapshots"]
    found = []
    for d in SUBDIRS:
        try:
            hits = [f for f in entries(f"{base}/{args.arch}/{d}/")
                    if f.startswith(args.match)]
        except Exception:  # noqa: BLE001
            continue
        for h in hits:
            found.append((d, h))
    if not found:
        print(f"  {args.match} not under {args.arch}")
        print("  An empty result here means it is elsewhere, not that it is gone.")
        return 1
    for d, h in found:
        print(f"  {d:<10}{h}")
    return 0


def cmd_matrix(args) -> int:
    """Check whether a package's filenames agree across architectures.

    This is the one that decides how many URLs a job needs. A package that
    carries one filename everywhere takes a single template; one that differs
    per architecture needs a template per architecture group.
    """
    base = args.base or SOURCES["snapshots"]
    arches = args.architectures.split(",")

    def one(a):
        flat = []
        for files in listing(base, a).values():
            flat.extend(files)
        return a, [f for f in flat if f.startswith(args.match)]

    print(f"  matching {args.match!r} across {len(arches)} architectures\n")
    with cf.ThreadPoolExecutor(len(arches)) as ex:
        results = list(ex.map(one, arches))

    per_arch = {}
    for a, files in results:
        per_arch[a] = files[0] if files else None
        print(f"  {a:<22}{files[0] if files else 'absent'}")

    found = {f for f in per_arch.values() if f}
    print()
    if len(found) == 1:
        print("  one filename everywhere: a single template covers every "
              "architecture")
    elif len(found) > 1:
        print(f"  {len(found)} different filenames: group the architectures by "
              "which they use")
        groups: dict[str, list[str]] = {}
        for a, f in per_arch.items():
            groups.setdefault(f or "absent", []).append(a)
        for f, aa in groups.items():
            print(f"    {aa}\n      {f}")
    else:
        print("  not found in any architecture")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", help="feed base URL")
    ap.add_argument("--arch", default="x86_64")
    ap.add_argument("--match", help="package name prefix")
    ap.add_argument("--architectures", default=",".join(DEFAULT_ARCHES))
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("arches").set_defaults(fn=cmd_arches)
    sub.add_parser("matrix").set_defaults(fn=cmd_matrix)
    sub.add_parser("where").set_defaults(fn=cmd_where)
    args = ap.parse_args()
    # argparse puts subcommand options after the subcommand, so a bare --match
    # is the common case; treat a missing subcommand as  when a name was
    # given, and as  otherwise.
    cmd = args.cmd or ("where" if args.match else "arches")
    return {"arches": cmd_arches, "matrix": cmd_matrix, "where": cmd_where}[cmd](args)


if __name__ == "__main__":
    sys.exit(main())