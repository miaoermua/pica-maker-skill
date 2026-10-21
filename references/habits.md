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
| Already its own package here | Declare it — bundling installs it twice |
| A kernel module or toolchain runtime | Declare nothing. `kmod-*` is built against a kernel version and travels with the image |

A missing third of that table is what makes a package look portable while
shipping a kernel module that is wrong on every other firmware.

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

## Write the reason into the commit, not the change

The change is in the diff. What the diff cannot say is why `mipsel` maps to
`mipsle` rather than `mips`, or why a translation gets one URL instead of five.
That is the part that stops the next edit from reintroducing it.
