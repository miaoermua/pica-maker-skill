# Working habits

What keeps a package right the first time. Each entry came from a mistake that
built green, or nearly did, and was wrong anyway.

## Failures seen in CI, and their cause

| Report | Cause | Fix |
|---|---|---|
| `… installs as 'X', which the manifest does not declare` | a downloaded container — often an **optional** asset — has no `app`/`base` line | declare it; optional assets as `app = X?` |
| `…/fastfetch-musl-aarch64.tar.gz: HTTP 404` | the matrix lists an arch upstream does not build for musl | drop the arch; check the asset list per arch and libc |
| `X is not in feed immortalwrt` (one arch) | the feed release skipped that arch for this package | drop the arch, or use a feed that has it |
| `neither the tag nor the matched assets carry pkgver …; upstream moved on` | a pinned github package, upstream released | merge the bump PR, or `nest bump <pkg> --apply` |
| `feed has X 1.2-r1, the manifest pins 1.1` | a feed job with a pinned pkgver | remove `pkgver`; feed jobs follow the feed |
| `matches nothing for <arch>` | the asset regex captures an arch name upstream does not publish | fix `arch_map`, or drop the arch |
| `rebuilt under a name already published` (warning) | `scripts/`/`root/`/manifest changed, version did not | bump `pkgrel` |

A failed package is not published and is retried by the daily upstream
workflow (`nest outdated`) until it builds.

## A probe that cannot connect is not a pass

`plan --probe` reports `unreachable` for timeouts, rate limits and proxy errors,
and only `missing` for a real 404. Behind a proxy that answers `502` for every
GitHub download, a 404 looks exactly like the proxy noise — that is how a
fastfetch arch that never existed survived a local check and failed in CI.
Re-check every `unreachable` URL directly (the API's asset list, or `curl -I`)
before calling a package done.

## The binary decides libc, endianness and arch — not the filename

OpenWrt is musl. fastfetch publishes `fastfetch-musl-amd64` and, for aarch64,
only `fastfetch-linux-aarch64` — a glibc build that downloads, packs and
installs, then does not start. Look for `musl` in the name, or check the
interpreter of a dynamic binary (`file`, or `readelf -l | grep interpreter`:
`ld-musl-*` is right, `ld-linux-*` is not). A static Go binary has none and is
fine.

Tailscale ships both `mips` and `mipsle` and both URLs answer; `mipsel_24kc` is
little-endian, so the right one is `mipsle`. Read the ELF header rather than the
name: byte 5 (`EI_DATA`) is 1 for little-endian, 2 for big-endian.

A Go project calls `x86_64` `amd64` and aarch64 `arm64`; `arch_map` translates
for the URL while the matrix keeps OpenWrt names.

## Every container is declared, optional ones included

The build reads each container's own `Package:` and stops on a name the
manifest does not declare: a container nobody names cannot be uninstalled and
is invisible to the precheck. `luci-theme-argon` marked its settings page
`optional` in build.json and declared nothing; it failed the first build. The
`?` suffix declares a container that may be missing: `app = luci-app-argon-config?`.

## Feeds rebuild architectures independently

ImmortalWrt 25.12.2 carried adguardhome `0.107.79` on x86_64 and `0.107.76`
on aarch64, and no `qbittorrent` at all on `aarch64_generic`. A feed job
resolves every arch on its own and publishes the version each actually carries
— no per-arch version table to maintain. What still needs a decision is an arch
that lacks a name: the matrix lists only arches that carry every required
package. `scripts/feed_lookup.py` shows it before the build does.

## A feed index is not the file name

apk `index.json` keys a package by the name it provides: `node` maps to the
file `node127-22.23.2-r1.apk`. The resolver matches it through the directory
listing and accepts both spellings. Guessing `node-22.23.2-r1.apk` is a 404.

Subdirectories are never guessed either: `ip-full` sits in `base/`,
`qbittorrent` in `packages/`. The resolver searches `feed_repos` in order.

## Release directories hold still; snapshots and branches do not

A release directory (`releases/25.12.2/`) never changes, so a feed job on it is
reproducible, and moving it is one edit in `ci/config.json` that rebuilds
exactly the packages on that feed. A snapshot or a branch feed (`snapshots/`,
fantastic's `archive/24.10`) rebuilds in place and deletes old files: nothing in
Git changes, so a push never rebuilds those packages — `nest outdated` in the
daily workflow does. Prefer a release directory when both carry the package.

Feed versions in `ci/config.json` are moved by a person. `nest feeds` reports a
newer point release; nothing applies it automatically, because one edit changes
every package on that feed.

## Backends cannot be mixed

An `.apk` cannot be packed for opkg; `<mgr>` decides the container format. When
a feed moved to apk-only (25.12, snapshots), the package needs an `apk/` job,
not a new URL for the `opkg/` one.

## Dependencies split three ways

| The dependency is… | Do |
|---|---|
| Called at run time, and not already on every install | Bundle it as a separate container |
| A system package the device's own feed already carries | Declare it optional — `base = x?` |
| A kernel module or toolchain runtime | Declare nothing that pins a kernel |

## A required name can send the install to the feeds

The client's feed policy counts the names this package *requires* — `base` and
`app`, not `kmod` — against the device's feeds; if any one is there it installs
the dependency set from the feeds instead of from the artifact's containers. A
wrapped package's own app name is in no feed, so the install then stops on a
name the feed does not have. `luci-base`, `luci-compat`, `ipset`, `curl` are in
every feed.

The trailing `?` takes a name out of that count while still naming it. A
required name no feed carries costs nothing and is what makes the precheck
refuse a device that cannot run the package — do not mark everything optional.

## `luci = lua1` describes the interface, it installs nothing

On 24.10 and later `luci-base` ships no Lua; `luci.model.uci`,
`luci.dispatcher` and friends live in `luci-lua-runtime` (`luci-compat` pulls
it). A `lua1` interface that declares no runtime opens a menu entry that
answers nothing on a stock device. Declare it, optional.

## A package in this source is not a dependency

A dependency is resolved against the backend's database, its feeds, and the
artifact's own `pkgs/` — never against another pica package. Bundle the
container, or depend on the system package the feed carries.

## Python is a runtime the feed owns

`python3-light` carries `ssl.pyc` without `_ssl`; the stdlib is split into
`python3-<module>` packages. On musl only `py3-none-any` wheels load. Wrapping
the feed's own `python3`/`node` containers is fine; self-packing `requests` or
`pip` from PyPI fights the distribution for file ownership.

## Ship only what the scripts use

`root/` is deployed as it stands. `cattools` carried a 68 KB copy of its script
under `root/usr/lib/pica/cattools/` that nothing referenced — the install
script reads the downloaded copy under `usr/lib/pica/src/`. Every file under
`root/` must be reached by something.

## A package can ship no container at all

`cattools` is `targets = opkg, pica`, hands its runtime to opkg (`base@opkg =
bash`) and installs itself through `scripts/install`. No container is not an
empty package; `scripts/` or `root/` is enough.

## Retired fields are refused, not ignored

The source manifest no longer carries `visibility` (now `source_availability`,
one of `open|partial|closed` — `mix` was never valid), `platform`/`arch` (the
matrix writes them per artifact), `source`, `pkgmgr`. `nest validate` names
each one.

## Renaming is a device-visible change

A device that installed the old `pkgname` does not see the new one as an
upgrade. Note it when renaming.

## Raise the client floor with the format you rely on

Every manifest carries `pica = 0.4.4`, the floor whose client reads the
per-backend index and filters by arch. A new package stays at that floor. A
package that updates pica itself sets the oldest version that can install it.

## Testing the client on Windows

`pica` targets OpenWrt. On Windows `file://` source URLs do not parse, and the
fetch-tool check looks for a file named exactly `curl` on `PATH`. Serve `r/`
over `http://127.0.0.1` and put a copy of `curl.exe` named `curl` on `PATH`;
set `PICA_ETC_DIR`/`PICA_STATE_DIR` outside the source tree. A killed run leaves
`state/inuse.<pid>.lock`; it is safe to delete and must never be committed.

## The index is generated

`r/index.json` is hand-written and decides each backend index's path;
`r/<mgr>/index.json` is written by CI. Never edit a backend index: the next
publish rewrites it from what was actually released.

## Write the reason into the commit, not the change

The diff shows that `mipsel_24kc` maps to `mipsle`, or that a matrix lost an
arch. Only the message can say why, and that is what stops the next edit from
putting it back.
