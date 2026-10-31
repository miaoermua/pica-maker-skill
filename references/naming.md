# Artifact naming and the layers beneath it

What `pica-pack` writes, and the three names that get confused with it.

## The filename

`package_filename()` in `pica-pkg-core/src/repo.rs` builds it; the client
rejects an index entry whose `filename` differs from it.

```
<pkgname>-<pkgver>-<pkgrel>-[<platform>-]<arch>-<suffix>.pkg.tar.gz
```

| Part | Source | Note |
|---|---|---|
| `pkgname` | manifest | this source's own name for the package |
| `pkgver` | manifest, or upstream when the manifest omits it | normalised, see below |
| `pkgrel` | manifest | `1` when omitted |
| `platform` | `ci/config.json` `platforms[arch]` | **omitted entirely when `all`** |
| `arch` | build.json `matrix` | |
| `suffix` | backend | `opkg`, `apk`, `pica` |

Real output from this source:

```
ttyd-1.7.3-1-amd64-x86_64-opkg.pkg.tar.gz
adguardhome-0.107.79-1-amd64-x86_64-apk.pkg.tar.gz
adguardhome-0.107.76-1-arm64-aarch64_cortex-a53-apk.pkg.tar.gz
tailscale-bin-1.104.2-1-mipsel-mipsel_24kc-pica.pkg.tar.gz
cattools-1.1-2-all-opkg.pkg.tar.gz
uugamebooster@xiaodoudou-2.0-1-all-apk.pkg.tar.gz
```

The two adguardhome lines are one package: the feed rebuilt x86_64 ahead of
aarch64, and each arch publishes the version it actually carries.

The filename is also the GitHub release asset name, so it may only use
`A-Z a-z 0-9 . _ @ + -`. GitHub rewrites anything else on upload — `~` becomes
`.` — and the index would then name a file that does not exist.

## A published name is immutable

`pica-pack` stamps `builddate` into every artifact, so rebuilding an unchanged
package gives the same name with different bytes. `nest index` keeps the
published entry and asset in that case and warns; overwriting it would hand
every device holding the previous index a file whose SHA-256 does not match.
To republish under the same version, bump `pkgrel`.

## Three names that are not the filename

| Field | What it names | Example |
|---|---|---|
| `pkgname` | the package in this source's index | `uugamebooster@xiaodoudou` |
| `appname` | what the user types; the command on the device | `tailscale` |
| `app` | an upstream container inside the package | `luci-app-uugamebooster` |

`pkgname` takes `-bin` for a bare binary and `@maintainer` for a fork when
upstream already publishes the plain name. `appname` stays the upstream name
and never carries `@` or `luci-app-`.

Renaming is cheap for the index and expensive for installed devices: a device
that installed the old `pkgname` does not see the new one as an upgrade.

## Version fields

- `pkgrel` may be folded into `pkgver` (`1.0.0-2`): `pica-pack` splits on the
  first `-` when `pkgrel` is absent. So `1.0.0-rc1` without `pkgrel` parses as
  revision `rc1`; `nest validate` refuses a `-` without an explicit `pkgrel`.
- `pkgver` never contains `~`.
- A version taken from upstream is normalised once, in `ci/nest/util.py`
  `publishable_version()`:

| Upstream | Published | Why |
|---|---|---|
| `0.107.76-r1` (feed) | `0.107.76` | the feed revision is not this source's pkgrel |
| `26.236.50544~cb5d434` | `26.236.50544.cb5d434` | GitHub rewrites `~` |
| `1:2.3-r1` | `2.3` | epoch dropped |
| `v3.1.1` (tag) | `3.1.1` | |
| `3.9.7-beta2` (tag) | `3.9.7_beta2` | a `-` would split into pkgrel |

Versions are compared by value, not spelling, so `1.8-9`, `1.8.9` and
`v1.8.9` are one version to every check in the tool.
