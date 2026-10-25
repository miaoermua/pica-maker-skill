# Artifact naming and the layers beneath it

What `pica-pack` writes, and the three names that get confused with it.

## The filename

`package_filename()` in `pica-pkg-core/src/repo.rs` builds it. Fields are
concatenated in order; nothing else is added.

```
<pkgname>-<pkgver>-<pkgrel>-<platform>-<arch>[-<suffix>].pkg.tar.gz
```

| Part | Source | Note |
|---|---|---|
| `pkgname` | manifest | this source's own name for the package |
| `pkgver` | manifest | |
| `pkgrel` | manifest | defaults to `1` if omitted |
| `platform` | job matrix | **omitted entirely when it is `all`** |
| `arch` | job matrix | |
| `-<suffix>` | backend | `opkg` → `-opkg`, `apk` → `-apk`, `pica` → `-pica`; every backend has one |
| `.pkg.tar.gz` | constant | `PKG_EXTENSION` |

Real output from this source:

```
qbittorrent-5.2.3-2-amd64-x86_64-apk.pkg.tar.gz
tailscale-bin-1.104.2-1-amd64-x86_64-pica.pkg.tar.gz
uugamebooster@xiaodoudou-2.0-1-all-apk.pkg.tar.gz
cattools-1.1-2-all-opkg.pkg.tar.gz
```

The opkg suffix is recent. `filename_suffix()` returns `None` for an unknown
backend because naming it the way opkg used to be named would let two backends
write the same file; before 0.3.34 that same rule let opkg write no suffix at
all, so `cattools-1.1-2-all.pkg.tar.gz` was correct then and is wrong now.
Take the name from the build that produced the artifact, never from a local
`pica-pack` binary of unknown vintage — one packer upgrade renames every opkg
artifact in the source at once.

When `platform` is `all` the stem drops that segment and only `arch` remains,
so a package that is `all` for both shows just `-all`. That is not a separate
rule — `arch` is doing the work and happens to also be `all`.

## Artifacts land under the backend, not beside it

```
out/<backend>/       --outdir default layout
```

`output_subdir()` returns the backend name verbatim. The comment on it records
why: deciding the backend from a file extension is what let a `pica` build pick
up `.apk` inputs, so the layout states the backend rather than implying it.

## Three names that are not the filename

The manifest carries several identities and only one of them is the file's
name. There is an assertion in the tests for exactly this confusion:

```rust
assert_eq!(pkg.app_key(), "demo",
  "appname must come from the manifest, not pkgname");
```

| Field | What it names | Example |
|---|---|---|
| `pkgname` | the package in this source's index | `uugamebooster@xiaodoudou` |
| `appname` | the command on the device | `tailscale` |
| `app` | an upstream container inside the package | `luci-app-uugamebooster` |

A fork uses the split deliberately: the upstream name goes in `app` so the
package manager installs what the project publishes, while `pkgname` carries
the maintainer so a future upstream build can sit beside it.

Renaming is cheap for the index and expensive for installed devices — the
filename and `pkgname` change together, but an installed device keeps looking
for the old name on upgrade.

## Version fields

`pkgrel` may be folded into `pkgver`:

```ini
pkgver = 1.0.0-2     # revision 2
pkgver = 1.0.0       # revision 1, pkgrel omitted
```

`resolve_version()` splits on the first `-`. A `pkgver` that carries a hyphen
for another reason — a vendor build like `26.236.50544~cb5d434` is safe, but
`1.0.0-rc1` would parse as revision `rc1`.
