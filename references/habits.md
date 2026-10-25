# Working habits

What keeps a package right the first time. Each of these came from a mistake
that built green and was wrong anyway.

## Verify the name, not the rendering

A release page shows a filename it is guessing at. `26.156.15499~38397ed`
rendered for a file really called `26.156.15499.38397ed`, and the `~` form
404ed. Ask the expanded asset listing, which is the raw HTML rather than a
rendered guess.

A filename carrying `~` also defeats `curl`, which expands it as a glob even
under `-g`. Fetch it through Python with `urllib.parse.quote` on the name.

## Never guess a subdirectory

`ip-full` sits in `base/`, `qbittorrent` in `packages/`, `ucode-mod-socket` in
`base/`. From the names alone they look like the opposite. A wrong guess is a
404 that only appears at build time.

`scripts/list_feed.py --match NAME where` answers it in one call.

## The binary decides endianness, not the filename

Tailscale ships both `mips` and `mipsle` and both URLs answer. `mipsel_24kc` is
little-endian, so the correct one is `mipsle` — but picking `mips` would not
fail to download. It would install a big-endian binary on a little-endian
device and only break at run time.

Read the ELF header rather than reasoning from the name: `EI_DATA` is byte 5,
1 for little-endian and 2 for big-endian.

The same goes for architecture. A Go project calls `x86_64` `amd64` and aarch64
`arm64`, so substituting the matrix's arch into the URL 404s; `arch_map`
translates for the URL while the manifest keeps OpenWrt names.

## One URL for a translation, not one per architecture

A `luci-i18n-*` container holds a catalogue and no code, so it is
architecture-neutral. A feed still keeps a separate copy per architecture
directory and they drift apart — three rebuilds can be current at once. Naming
one URL per architecture downloads all of them into every package.

Verify the copies are the same artefact before relying on it: matching versions
in two architectures were the same 1508 bytes, differing only in signature
timestamp.

## Backends cannot be mixed

An `.apk` cannot be packed for the opkg backend — the packer rejects a
directory holding only `.apk`. `mgr` decides which format the containers must
have. When a feed has moved to apk-only, the answer is a new job on the apk
backend, not a new URL for the opkg one.

This decides which feed a job can read at all: `snapshots/packages` is apk-only
and has no ipk, while `24.10.0` still carries both.

## Dependencies split three ways

| The dependency is… | Do |
|---|---|
| Called at run time, and not already on every install | Bundle it as a separate container |
| A system package the device's own feed already carries | Declare it as optional — `base = x?`. Required, it moves the install to the feeds, see below |
| A kernel module or toolchain runtime | Declare nothing. `kmod-*` is built against a kernel version and travels with the image |

A missing third of that table is what makes a package look portable while
shipping a kernel module that is wrong on every other firmware.

## A required name can send the install to the feeds

The default feed policy is `ask`. It counts the names this package *requires* —
`base` and `app`, not `kmod` — against the device's feeds, and if any single one
of them is there it installs the dependency set from the feeds instead of from
the artifact's containers. Non-interactive does that without asking; interactive
asks a question whose default answer is yes.

A wrapped package's app name is in no feed — that is why it is wrapped — so one
required name that a feed carries is enough to lose the containers, and the
install then stops on a name the feed does not have. `luci-base`,
`luci-compat`, `ipset`, `curl` are in every feed; `base = luci-base` on a
package that wraps a third-party interface reads as a correct declaration and
is the reason it will not install.

The trailing `?` takes a name out of that count. Only required names are
counted, so `base = luci-lua-runtime?` keeps the install on the containers while
still naming the package: a device missing it is told which package is missing,
and one that has it is left alone. The cost is that a non-interactive install
does not add optional dependencies unless given `--with-optional`.

Marking everything optional is not the fix either. A required name that no feed
carries costs nothing — it is not counted — and it is what makes the precheck
refuse a device that cannot run the package.

## An arch-independent container is a part of every package

`pica-pack` writes one artifact per populated `pkgs/<mgr>/<platform>/<arch>/`
directory. That is the whole rule, and it is what a `target` of
`{platform: all, arch: all}` in a per-architecture job used to violate: the
fetcher wrote the container to `pkgs/opkg/all/all`, and that directory became an
artifact of its own.

For `leigod-acc` that produced two halves of one package — a 124 KB `all`
holding the interface and its translation, and a 5 MB per-architecture set
holding only the daemon — carrying the same name, version and manifest on both,
so a client took whichever it saw and got half an app.

The fetcher writes such a container into every matrix row now, so each
per-architecture artifact is whole. A job whose matrix really is `all/all` — the
theme packages, `ua-mask`, `istore` — has one row and still gets one
destination. Placing a container under `all/all` by hand in a per-arch job is
the same mistake one layer down.

## `luci = lua1` describes the interface, it does not install anything

The field records which LuCI generation the interface is written for. Nothing
reads it to resolve a dependency, so a Lua controller needs the Lua runtime the
same way it needs `curl`: declared.

On 24.10 and later `luci-base` ships no Lua at all — the 24.10.0 package is 106
files of JavaScript and ucode — and `luci.model.uci`, `luci.i18n`,
`luci.dispatcher` and `luci.jsonc` live in `luci-lua-runtime`, which pulls
`luci-base`, `luci-lib-nixio` and `luci-lib-jsonc` with it. A `luci = lua1`
package that declares no runtime opens a menu entry that answers nothing on a
stock device, while looking perfect on the Lua-LuCI one where it was tested.
`luci-compat` is the older name for the legacy bundle and depends on
`luci-lua-runtime`, so naming either brings the runtime.

Declare it optional, for the reason above: it is in every feed.

## A package in this source is not a dependency

A dependency name is resolved against three things only: the backend's installed
database, the backend's feeds, and the artifact's own `pkgs/`. A package living
in this source is in none of them — pica keeps its own ledger and never reads
another artifact's manifest — so declaring one makes the precheck refuse the
install as `missing`.

The report is the only place it shows: the declared name is looked up in the
backend and its feeds, comes back `missing` because a pica package is in
neither, and the install stops on a prerequisite the device cannot satisfy —
even though `pica -S` will install that other package happily on its own. It
reads like a typo in the manifest, which is why it is worth knowing before
writing one.

To ship what another package provides, bundle its container in
`pkgs/<backend>/`, or write the dependency as the system package the device's
feed carries. There is no fourth option and no syntax that makes one pica
package depend on another.

## Python is a runtime the feed owns

`python3-light` is not a Python. The interpreter is `python3-base` plus
`libpython3-<ver>`; the standard library is split into `python3-<module>`
packages, and `ssl` is `python3-openssl`. `python3-light` carries `ssl.pyc`
without `_ssl`, so `import ssl` fails until that module package is installed —
and a missing piece only surfaces at run time, never in the build.

On musl, PyPI's `manylinux` wheels cannot load and `musllinux` wheels barely
exist; only `py3-none-any` is portable. C extensions have to come from the
feed's own per-arch build, declared as a dependency.

So a Python application is wrappable when it is pure Python and every import is
declared (`base = python3-light`, `base = python3-urllib`, …). `requests` is not
a good candidate for self-packing: on 24.10.8/x86_64 a single
`base = python3-requests` resolves to 34 packages and about 24 MiB installed,
because `urllib3` pulls the whole stdlib metapackage.

Wrapping the feed's own container is a different thing and is fine. That is what
`node` does, and `python`, `python3-pip` and `python3-requests` follow it in both
sources: the native package stays the distributor's, installed by the backend
that owns it, so nothing is duplicated and no file changes hands. Self-packing
`requests`, `pip` or `python3` from PyPI is the shape that fights the
distribution for ownership; a feed wrapper is not.

## A green build proves less than it looks

A container that failed to download leaves the build green: the fetcher warns,
the validator passes, and the package ships with a container missing. Read the
archive after building.

The same is true of the validator — it checks that a job is legal, not that a
URL answers. Run `scripts/check_urls.py` separately.

## Pin a vendor build identifier

ImmortalWrt rebuilds change the filename: the interface moved from
`26.118.13608~2a84422` to `26.236.50544~cb5d434` between two listings. Following
a channel silently changes the package's identity between builds. Write the
version into the URL.

A release branch does not roll the way a snapshot does, so it is the safer
source when both carry the package.

## Renaming is a device-visible change

`pkgname` is this source's identity; `app` and `appname` name what reaches the
device. Renaming a package is cheap for the index and invisible to the device,
but a device that installed the old name will not see the new one as an upgrade.
Note it when renaming.

## One artifact, one index entry

An index keyed by package name holds one row per package, while a job builds one
artifact per matrix entry. A five-architecture package therefore once had five
files and one entry: four of them were named by nothing, and the survivor was
whichever architecture the matrix happened to end on. The build stayed green;
`verify_artifacts` reported it one line at a time as
`built artifact has no index entry`.

The merge keys on `(pkgmgr, pkgname, platform, arch)` now, which is the fix. If
that message appears again it means an artifact was dropped on the way into the
index, not that the key is too narrow — read the merge before widening anything.

The same rule explains why one package may legitimately carry several versions:
`bind-dig` was `9.20.26` on four architectures and `9.20.29` on
`aarch64_cortex-a53`, `nano` was `9.1` against `9.2`. One entry per artifact,
not per name — which is exactly what a second URL template per architecture
buys.

## A package can ship no container at all

`cattools` declares `targets = opkg, pica`, hands its runtime to opkg
(`base@opkg = bash`, `curl`, `unzip`, `jq`) and installs itself through
`scripts/install`. There is deliberately no `.ipk` inside it.

A check that demanded `pkgs/` from every native backend called that package
empty and blocked a release one step before publishing 148 of them. It now asks
the packer's question instead — containers, `root/`, or `scripts/`, at least one
— so a script-installed package passes on its own merits. What to carry into a
new package is the part that was always true: no container is not an empty
package, and a native backend needs no `.ipk` when the scripts install it.

`root/` is not a pica-backend feature either: pica lays that tree down for
every backend, so an `opkg` package can ship files no container owns while still
handing its dependencies to opkg.

## The suffix belongs to the packer version

Every backend has a suffix since 0.3.34 — `-opkg` included — and 0.3.34 is what
CI builds. Older packers wrote opkg with none, so one package has two possible
names depending on which `pica-pack` handled it:
`cattools-1.1-2-all.pkg.tar.gz` from a 0.3.0 build,
`cattools-1.1-2-all-opkg.pkg.tar.gz` from 0.3.34.

Take the published name from the build that produced the artifact, never from a
local `pica-pack` of unknown vintage. One packer upgrade renames every opkg
artifact in the source at once.

## Raise the client floor with the format you rely on

A source publishing one entry per architecture is only correct for clients that
filter by architecture. 0.3.33 did not — it compared versions and took the first
match — so a package with five entries could resolve to `mipsel_24kc` on an
`x86_64` device and only fail at the install-time architecture check.

Every manifest now carries `pica = 0.3.34`, the floor that keeps such a client
out: `pica too old: pkg requires >= 0.3.34, cli is 0.3.33`. A new package stays
at that floor. Lowering it reopens the misinstall the multi-entry index exists
to avoid, and the failure it produces is an architecture error halfway through
an install rather than a refusal up front.

A package that updates pica itself is the exception to "stay at the floor". Its
`pica` value gates the *installed* client, so setting it to the version the
package contains stops every older client from starting the upgrade. Set it to
the oldest version that can install the package.

That package is reached by `-Su` only when it came from the source: `-U` records
`source = local` and `-U <url>` records `url`, and the upgrade scan skips both.
The first copy is installed with `pica -S pica`.

## Do not run the CLI inside the source tree

`pica` creates its state directory before it does anything else. The default is
`/var/lib/pica`, which needs root, so pointing `PICA_STATE_DIR` at something
relative is tempting — and then the source tree grows
`state/inuse.<pid>.lock`, whose entire content is the PID. `LockGuard::drop`
removes that directory, and a killed process never runs it; a leftover lock
means an interrupted run and is safe to delete.

`state` belongs in `.gitignore`, but a lock file that was already committed
stays tracked — ignore rules do nothing to a path git already has. `git rm
--cached` it.

## A view is not a second list

`r/repo.json` is the index. `r/index.json` and `r/<mgr>/index.json` are written
from it in the same run, and `validate_index_layout.py` fails when one of them
stops agreeing with it. Editing one by hand creates two descriptions of the same
artifacts; when the check fires, regenerate rather than editing the other file
to match — the second edit only moves the disagreement.

## Write the reason into the commit, not the change

The change is in the diff. What the diff cannot say is why `mipsel` maps to
`mipsle` rather than `mips`, or why a translation gets one URL instead of five.
That is the part that stops the next edit from reintroducing it.
