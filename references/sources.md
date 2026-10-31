# Sources, layouts, and the dependency decision

Detail for every `source.type` in `packages/<mgr>/<id>/build.json`, and the
decisions that sit next to them. The schema is `ci/schema/build.schema.json`;
`nest validate` is what actually enforces it.

## Common fields

```json
{
  "$schema": "../../../ci/schema/build.schema.json",
  "matrix": ["x86_64", "aarch64_generic", "aarch64_cortex-a53", "aarch64_cortex-a72", "mipsel_24kc"],
  "upstream": "github:owner/repo",
  "source": { "type": "…" }
}
```

| Field | |
|---|---|
| `matrix` | OpenWrt arches, keys of `ci/config.json` `platforms`; `["all"]` for an arch-independent package. One artifact per arch per target |
| `upstream` | url / archive only, with a pinned pkgver: where `nest bump` looks for releases |
| `source.arch_map` | matrix arch → the name upstream uses (`x86_64` → `amd64`). Same direction for every source type |

Each matrix arch is staged on its own, with its own version and its own `root/`,
so per-arch differences need no special fields.

## `feed`

```json
"source": {
  "type": "feed",
  "feed": "immortalwrt",
  "packages": ["adguardhome", "luci-app-adguardhome"],
  "optional": ["luci-i18n-adguardhome-zh-cn"],
  "version_from": "adguardhome"
}
```

- `feed` names an entry of `ci/config.json` `feeds`; the `<mgr>` URL is used.
  The release in that URL (`24.10.0`, `25.12.2`) is the version knob for every
  package on that feed.
- Names are resolved per arch through the feed's own index — opkg `Packages(.gz)`,
  apk `index.json` plus the directory listing — searching `feed_repos`
  (`base`, `packages`, `luci`, …) in order. No subdirectory is ever written.
- opkg indexes carry size and SHA-256; downloads are checked against them.
- `version_from` picks the package whose version becomes pkgver (default: the
  first of `packages`). Pick the daemon, not the LuCI app: the app's version is a
  LuCI build string that says nothing about what the package runs.
- A name missing on one arch fails that package. Drop the arch from the matrix
  or move to a feed that has it — `scripts/feed_lookup.py` shows which.
- apk ABI packages: `index.json` lists `node` while the file is
  `node127-22.23.2-r1.apk`. Both names resolve; `node` follows ABI bumps,
  `node127` pins the ABI.

Feed layout differs by era, which the resolver hides but which still decides
which `<mgr>` a feed can serve:

| Era | Index | Container |
|---|---|---|
| 24.10 and earlier | `Packages(.gz)` per subdirectory | `.ipk` → `opkg` |
| 25.12 and snapshots | `index.json` + `packages.adb` | `.apk` (ADB) → `apk` |

A mirror's directory listing may be a JavaScript shell with no entries;
configure the upstream host (`downloads.immortalwrt.org`) as the feed.

## `github`

```json
"source": {
  "type": "github",
  "repo": "SunBK201/UA3F",
  "tag_regex": "^v?[0-9]+(?:\\.[0-9]+)*$",
  "arch_map": { "aarch64_generic": "aarch64" },
  "assets": [
    { "match": "^ua3f_[0-9].*-r?[0-9]+[_-]([A-Za-z0-9_+.-]+)\\.ipk$" },
    { "match": "^luci-app-ua3f_.*_all\\.ipk$", "optional": true },
    { "match": "^EasyTier-v{version}-(.*)-22\\.03\\.7\\.zip$", "unzip": "^(?:easytier|luci-app-easytier).*\\.ipk$" }
  ]
}
```

- Release selection: `tag` (exact; `v{version}` uses the pinned pkgver), or
  `tag_regex` (newest matching stable release), or neither (newest stable).
  `prerelease: true` lets betas in. `tag` and `tag_regex` exclude each other.
- `match` is anchored at the start; `{version}` is substituted escaped.
  **One capture group = the arch**, mapped back through `arch_map`; an asset for
  an arch outside the matrix is skipped with a note. No group = the asset goes
  into every arch's package (a LuCI app beside per-arch daemons).
- `optional: true` — missing is a note, not a failure. The container still has
  to be declared in the manifest when present (`app = name?`).
- `unzip` — the asset is a zip; members whose basename matches are extracted.
- Without `pkgver` the tag becomes the version. With one, the tag or an asset
  name must carry it, or the plan fails with "upstream moved on".
- Check a tag regex against the real tag list: `^v` matches nothing on a
  repository tagged `0.1`. Never pin a version inside `match` by hand — write
  `{version}`, so `nest bump` can move it.

## `url`

```json
"source": { "type": "url", "urls": ["https://istore.istoreos.com/repo/all/store/luci-app-store_{version}-r1_all.ipk"] }
```

Containers at fixed addresses outside every configured feed. `{arch}`,
`{platform}`, `{version}` are substituted. Needs a pinned pkgver. Anything a
feed carries belongs in a `feed` job instead.

## `archive`

```json
"source": {
  "type": "archive",
  "url": "https://pkgs.tailscale.com/stable/tailscale_{version}_{arch}.tgz",
  "arch_map": { "x86_64": "amd64", "aarch64_generic": "arm64", "mipsel_24kc": "mipsle" },
  "strip": 1,
  "include": ["tailscaled", "tailscale"],
  "dest": "usr/sbin"
}
```

| Field | Effect |
|---|---|
| `strip` | Leading path components dropped (`name-ver-arch/` → 1) |
| `include` | Path prefixes kept; everything else (man pages, completions) skipped |
| `rename` | Name for the single resulting file, made executable — bare binary downloads |
| `dest` | Directory under `root/` |

| Upstream layout | Settings |
|---|---|
| `name-ver-linux_amd64/frpc` | `strip: 1` + `include` |
| one file at the archive's top level | `rename` |
| `cloudflared-linux-amd64`, a bare binary | `rename` + `dest` |

Each arch is unpacked into its own staged `root/`, so a `pica` package can be
multi-arch. Needs a pinned pkgver and, for `nest bump`, `upstream`. Ship the
licence file when the archive has one (`include` it).

## Which arches a matrix lists

The arches that carry **every** required container, intersected with what
OpenWrt runs:

- feed: `scripts/feed_lookup.py` per name; a feed may skip an arch for one
  package (ImmortalWrt 25.12.2 has no `qbittorrent` for `aarch64_generic`).
- a recipe's `@(aarch64||arm||x86_64)` is deliberate — Docker is not built for
  mips; padding the matrix produces failures, not packages.
- github/archive: an asset for the arch **and the right libc**. `linux-aarch64`
  next to `musl-amd64` means the aarch64 build is glibc and does not run on
  OpenWrt — fastfetch ships musl for amd64 only.

One `arm64` binary may serve `aarch64_generic`, `aarch64_cortex-a53` and
`aarch64_cortex-a72`; mapping all three to it is correct.

## Translations

A `luci-i18n-<pkg>-<lang>` container is code-free, but feeds rebuild it per
arch out of step. With a `feed` job each arch resolves its own copy — one file
per package, matching the interface built beside it. Ship only the languages
asked for; this source carries `zh-cn`. `app_i18n = luci-i18n-<pkg>-{lang}`
declares them.

## The dependency-bundling decision

| The dependency is… | Do |
|---|---|
| Called by the interface at run time, and not on every install | Bundle it, as a separate container |
| Part of the base system every install already has (`luci-base`, a Lua runtime) | Declare it optional: `base = luci-lua-runtime?` |
| A kernel module or toolchain runtime | Declare nothing that ties it to one kernel |
| A second interface that happens to be installed too (`luci-compat`) | Declare it optional rather than bundling it |

`docker` and `dockerd` are a pair: the CLI and the daemon. An interface needs
both. Containers stay separate files inside one package so each stays
updatable on its own.

## Two backends from one job

`<mgr>` decides where inputs land; `targets` decides how many packages come out:

```ini
targets = opkg, pica
base@opkg = bash
base@opkg = curl>=7.0
```

A bare `base` is read by the pica side and refused. `<key>@<backend>` is
invisible to the backend it does not name.

## Reading an apk 3.x (ADB) container

Not a tarball: `tar` reads nothing, and `pica-pack` reports such containers as
"not counted", so the index `size` excludes them (0 for an apk-only package).
That is a missing feature, not a malformed package.

The container is `ADBd` and one raw-deflate stream:

```python
import zlib
raw = open('x.apk', 'rb').read()
body = zlib.decompressobj(-15).decompress(raw[4:])   # wbits -15, offset 4
```

Inflated, it opens with an `ADB.pckg` segment whose first record is the name,
then a length byte, then the version:

```
adguardhome \x0b 0.107.76-r1
```

`ci/nest/containers.py` reads it this way and believes a name only when the
character set, the length byte and the version shape all agree. Capitals occur
(`UAmask`) and LuCI versions carry `~hash`. The arch is not read from ADB; it
is left unverified rather than guessed.

## What a green build does not prove

`nest build` downloads with size/hash checks, reads container metadata, and
refuses undeclared containers, wrong arches and missing LuCI apps. It cannot
see:

- an ADB container's arch, or anything about a container it could not read;
- a glibc binary in a musl package, or a big-endian one on `mipsel`;
- a dependency the device lacks.

Read the archive:

```bash
tar -tzvf out/<backend>/*.pkg.tar.gz | grep -v '/$'
```
