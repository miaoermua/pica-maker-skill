#!/usr/bin/env python3
"""Look a package up in the feeds of a pica-nest checkout, per architecture.

Answers what has to be known before writing a `feed` job, using the same
resolver and the same ci/config.json the build uses: which architectures carry
the name, at which version, in which subdirectory, under which file.

    python3 scripts/feed_lookup.py --nest ../pica-nest --mgr apk qbittorrent luci-app-qbittorrent
    python3 scripts/feed_lookup.py --nest ../pica-nest --mgr opkg --feed openwrt btop
    python3 scripts/feed_lookup.py --nest ../pica-nest --mgr apk --arch x86_64 node node127

A name missing on one architecture is a matrix decision, not a typo: drop that
arch from the job, or pick a feed that has it.
"""

import argparse
import os
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="+", help="feed package names")
    parser.add_argument("--nest", default=os.environ.get("PICA_NEST", "."), help="pica-nest checkout (default: . or $PICA_NEST)")
    parser.add_argument("--mgr", required=True, choices=("opkg", "apk"))
    parser.add_argument("--feed", default="immortalwrt", help="feed name from ci/config.json")
    parser.add_argument("--arch", action="append", help="limit to these arches (repeatable); default: every arch in platforms")
    args = parser.parse_args()

    nest = os.path.abspath(args.nest)
    if not os.path.isfile(os.path.join(nest, "ci", "config.json")):
        parser.error(f"{nest} is not a pica-nest checkout (no ci/config.json); pass --nest")
    sys.path.insert(0, nest)
    from ci.nest import config as config_module, feeds, net  # noqa: E402

    config = config_module.load(os.path.join(nest, "ci", "config.json"))
    if args.feed not in config.feeds or args.mgr not in config.feeds[args.feed]:
        parser.error(f"feed {args.feed!r} has no {args.mgr} URL in ci/config.json; known: {sorted(config.feeds)}")
    arches = args.arch or [arch for arch in config.platforms if arch != "all"]
    print(f"feed {args.feed}/{args.mgr}: {config.feed_base(args.feed, args.mgr, '{arch}')}")

    missing = {name: [] for name in args.names}
    for arch in arches:
        try:
            found = feeds.resolve(config, args.feed, args.mgr, arch, args.names)
        except net.FetchError as err:
            print(f"  {arch:<20} cannot read the feed: {err.reason} ({err.status})")
            continue
        for name in args.names:
            entry = found[name]
            if entry is None:
                missing[name].append(arch)
                print(f"  {arch:<20} {name:<32} -")
            else:
                print(f"  {arch:<20} {name:<32} {entry.version:<28} {entry.repo}/{entry.filename}")
    for name, arches_without in missing.items():
        if arches_without:
            print(f"note: {name} is not in {args.feed}/{args.mgr} for {', '.join(arches_without)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
