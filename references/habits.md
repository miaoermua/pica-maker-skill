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
| A system package the device's own feed already carries | Declare it — bundling installs it twice |
| A kernel module or toolchain runtime | Declare nothing. `kmod-*` is built against a kernel version and travels with the image |

A missing third of that table is what makes a package look portable while
shipping a kernel module that is wrong on every other firmware.

## A package in this source is not a dependency

A dependency name is resolved against three things only: the backend's installed
database, the backend's feeds, and the artifact's own `pkgs/`. A package living
in this source is in none of them — pica keeps its own ledger and never reads
another artifact's manifest — so declaring one makes the precheck refuse the
install as `missing`.

`pica` 0.4.1 names that case: `pkg-x exist in the Pica sources, but pica does
not resolve Pica packages as dependencies`. Older clients only say `missing`,
which reads like a typo in the manifest.

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
