# Providers, layouts, and the dependency decision

Detail for the cases where SKILL.md's shapes do not fit.

## `source` fields by provider

### `github`

```json
"source": {
  "provider": "github",
  "repo": "owner/repo",
  "release": {
    "tag": { "mode": "regex", "regex": "^v?[0-9]+(?:\\.[0-9]+)*$" },
    "allow_prerelease": false,
    "assets": [
      {
        "name": "theme",
        "role": "app",
        "regex": "^name-[0-9].*\\.apk$",
        "required": true,
        "target": { "platform": "all", "arch": "all" }
      }
    ]
  }
}
```

A `github` job builds its own URLs from the API, so `check_urls.py` has
nothing to HEAD — the fetcher resolves them at run time. Check the tag regex
against the real tag list, including whether tags carry a `v` prefix; a `^v`
pattern silently matches nothing on a repository tagged `0.1`.

Never pin a version inside an asset regex: `^name_0\.4\.3-1_` stops matching
the moment upstream releases again, and the job fails on a repository that is
still healthy.

`allow_prerelease` decides whether beta tags are followed. Set it when the
project ships only betas, and expect the package's version to move on its own.

### `http_template`

One URL per container, from a mirror or a feed directory. No existence check —
a 404 here is the failure mode that produces a package silently missing a
container, so run `check_urls.py`.

### `tarball`

For sources with no package at all. Fields:

| Field | Effect |
|---|---|
| `strip_components` | Leading path components to drop. `1` for the usual `name-ver-arch/` wrapper; `0` when the archive is one file at its top level |
| `include` | Paths to keep. A path under one of these prefixes is written, the rest skipped |
| `rename` | Name for the result. Applies to an archive of one file and to a bare download, and sets mode 755 |
| `dest_subdir` | Subdirectory of `root/` to unpack into |
| `arch_map` | Renames each matrix architecture for the URL only |

`arch_map` exists because a Go project calls x86_64 `amd64` and aarch64
`arm64`, so substituting the manifest's `arch` into its URL produces a 404. The
manifest's `arch` and the built filename keep the OpenWrt names.

One `arm64` asset commonly serves several OpenWrt architectures
(`aarch64_generic`, `aarch64_cortex-a53`, `aarch64_cortex-a72`); mapping all of
them to it is correct, and it is not the same as claiming a build exists for
each.

`root/` is deployed as it stands, so a per-architecture directory there would
reach the device as a directory at the filesystem root. Unpack into `root/`
itself, or into `usr/sbin` via `dest_subdir`.

## OpenWrt directory layout

The ipk era and the apk era lay packages out differently, and guessing a
directory produces a 404 that looks like a missing package.

| Era | Layout |
|---|---|
| 24.10 (ipk) | `packages/<arch>/packages/`, `packages/<arch>/luci/` |
| 25.12+ (apk) | `packages/<arch>/{base,packages,luci,routing,telephony}/` |

List a directory rather than assuming:

```bash
curl -sL "$BASE/$ARCH/$DIR/" | grep -oE '>[^<]+\.apk<'
```

Note where a package actually lives: `ucode-mod-socket` is in `base/`, not
`packages/`, and a dependency guessed into `packages/` 404s while the rest of
the package builds.

## Which architectures a matrix should list

Take them from the architectures that carry **every** container the job
downloads, then intersect with what the repository already builds:

```bash
cd pica-pkg-repo && python3 - <<'PY'
import json, glob, collections
c = collections.Counter()
for f in glob.glob('ci/*/*/build.json'):
    for m in json.load(open(f)).get('build', {}).get('matrix', []):
        c[m['arch']] += 1
print([a for a, n in c.most_common()])
PY
```

An architecture that lacks one container is not a matrix entry. Where an
upstream recipe says `@(aarch64||arm||x86_64)`, the missing ones are deliberate
— Docker is not built for mips — and padding the matrix produces 404s.

## Finding what a feed holds

Never guess a subdirectory or a version. `scripts/list_feed.py` reads the feed:

```bash
python3 scripts/list_feed.py arches                    # which architectures exist
python3 scripts/list_feed.py --match ip-full where     # which directory holds it
python3 scripts/list_feed.py --match qbittorrent matrix # do filenames agree
```

`where` is the one that catches the most mistakes. `ip-full` sits in `base/`
while `qbittorrent` sits in `packages/`, and both look like they belong in the
other. Guessing produces a 404 that only appears at build time.

`matrix` decides how many URL templates a job needs — see the next section for
why that number is not always one.

A mirror's directory index may be too short to contain entries: some mirrors
render the listing with JavaScript and hand a plain fetch the shell. Against
`mirrors.pku.edu.cn` the same `packages/x86_64/` directory returns 579 bytes
and zero filenames, where `downloads.immortalwrt.org` returns 912 KB and 4886.
That is a property of the mirror, not a missing package — use the upstream host
to list, and the mirror only as a download source.

## Translations: one per package, not per architecture

A `luci-i18n-<pkg>-<lang>` container is architecture-neutral — it holds a
catalogue, no code — but a feed keeps a separate copy under each architecture
directory and those copies are not in step. Three rebuilds of the same
translation can be current at once:

```
x86_64                25.257.46572~f0567b4
aarch64_generic       26.118.13608~2a84422
aarch64_cortex-a53    26.118.13608~2a84422
aarch64_cortex-a72    25.257.46572~f0567b4
mipsel_24kc           25.272.42575~a0c0140
```

That is a reason to name **one** URL, not one per architecture. The fetcher
tries every template against every matrix entry and keeps whatever it can get,
so a per-architecture list downloads all three into every package and apk then
installs three copies of the same catalogue. Verify they are the same artefact
before relying on it — for the qBittorrent translation, two architectures
holding the same version gave byte-identical size and differing hashes, the
difference being the signature timestamp.

```json
"app_i18n": "luci-i18n-qbittorrent-{lang}"
```

`{lang}` in the manifest key is the convention; the URL names a concrete
language. Ship only the languages asked for — the repository's other translated
packages each carry one.

## The dependency-bundling decision

| The dependency is… | Do |
|---|---|
| Called by the interface at runtime, and not on every install | Bundle it, as a separate container |
| Part of the base system every install already has (`luci-base`, a Lua runtime) | Declare it; bundling duplicates it per package |
| A second interface that happens to be installed too (`luci-compat` for a Lua interface) | Bundle it when this package's control declares it |

`docker` and `dockerd` are a pair worth remembering: the first is the CLI
applet, the second the daemon built for OpenWrt. An interface needs both, and a
recipe asking for both means both.

Containers stay separate files inside one package. A merged tree loses what the
package manager recorded, so neither half can be updated on its own and a
rollback cannot put back only what changed.

## Two backends from one job

`mgr` decides where inputs land and which directory the job lives in; `targets`
decides how many packages come out. Keep `mgr` as the input side and list both:

```json
"mgr": "opkg",
"targets": "opkg, pica"
```

Dependencies then need a backend qualifier, or the pica side reads them and
rejects the build:

```ini
base@opkg = bash
base@opkg = curl>=7.0
```

`check_pica_declares_no_dependencies` reads a bare `base` on a pica target and
fails. `<key>@<backend>` is invisible to the backend it does not name.

## Reading an apk 3.x (ADB) package

`tar` cannot read these, so `pica-pack` reports `Install size: 0` and the
validator cannot verify the package name. That is a known limit, not a
malformed package. Read the metadata with `apk adbdump`, or take the package
name from the feed's index.

## What a green build does not prove

A container that failed to download leaves the build green: the fetcher warns,
the validator passes, and `pica-pack` writes a package with one container
missing. Always read the archive:

```bash
tar -tzf out/<backend>/*.pkg.tar.gz | grep -v '/$'
```

Check that every declared container is there, that executables carry `+x`, and
that no downloaded archive was left behind under `pkgs/` or `root/` — a stray
multi-megabyte input ships to the device otherwise.