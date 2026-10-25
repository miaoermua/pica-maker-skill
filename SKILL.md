---
name: picapkgmaker
description: Adds a package to a pica package source, producing a manifest and CI job that build and verify cleanly. This skill should be used when asked to add, package, wrap or self-package an upstream project into the pica package source — including self-contained tarballs and bare binaries, and wrapping official ipk/apk releases. It covers where the pica tools and the package source live on disk, how to search a feed or upstream recipe for a dependency, locating a source's dependencies and licence, choosing the backend and provider, mapping architectures, deciding which containers to bundle, the artifact naming rules, the published index layout, and the repository validator's hard rules.
agent_created: true
---

# Adding a package to the pica package source

Produce a package the validator accepts and that builds from a real upstream
source — verified, not assumed.

## Where things live

Three repositories, each with its own layout. Reach for these before guessing
a path.

**`pica` — the tools themselves.** Builds and installs packages.

```
crates/pica-pkg-core/src/repo.rs      package_filename(), the index schema
crates/pica-pkg-core/src/manifest.rs  what a manifest may declare
crates/pica-pkg-pack/src/build.rs     pica-pack's build, output layout
crates/pica-pkg-cli/src/commands/install/precheck.rs   dependency check
target/release/pica                   the installer
target/release/pica-pack              the packer
```

**`pica-nest` — the source this skill adds packages to.**

```
ci/<mgr>/<id>/build.json      the job
src/<mgr>/<id>/manifest       the package
.github/scripts/validate_repo.py   run before reporting done
.github/scripts/fetch_assets.py    the downloader, where providers are implemented
r/index.json                  which backends this source serves, and where
r/repo.json                   schema 2 — what a client fetches today
r/<mgr>/index.json            that backend's view, written from repo.json
.github/scripts/gen_repo_index.py  writes all of them; never hand-edit r/
```

`pica-pkg-repo` is an older clone of the same tree, sitting beside it with
identical contents and no workflow. A job written there is never built and
never published — confirm which clone has `.github/workflows/` before adding
one, and put the change in that one.

`<mgr>` is one of `opkg`, `apk`, `pica` and must match the job's own `mgr`.
The directory name and the `id` field must agree.

**`pica-maker-skill` — this file.** `scripts/`, `references/`, `assets/`.

## When the answer is in pica itself

This file covers the source. How a client resolves what the source publishes —
the index schema, the entry descriptor, sync and install order, the state
directory — is pica's own business, and inferring it from Rust signatures is how
a package ends up shaped for a client that no longer reads it that way.

Read the project's docs instead of guessing:

https://github.com/miaoermua/pica/tree/main/docs

`standard.md` holds the archive and index contract — including the `schema 1`
entry descriptor with `managers[].path`, which is what the `r/` layout above
serves. `developer.md` covers the build and install pipeline, `user.md` what a
user sees. They are drafts and can lag: where a document and `crates/` disagree,
the code is what ships.

## Establish the facts before writing anything

Most mistakes here come from trusting a rendered release page. Verify first.

```bash
# Exact asset names. The rendered page mangles these: `26.156.15499~38397ed`
# was really `26.156.15499.38397ed`, and the `~` form 404s.
curl -sL "https://github.com/OWNER/REPO/releases/expanded_assets/TAG" \
  | grep -oE '>[A-Za-z0-9_.+~-]+\.(ipk|apk|tar\.gz|zip)<' | tr -d '><' | sort -u

# Every URL must answer 200 — before writing build.json, not after.
curl -sI -o /dev/null -w '%{http_code}\n' "$URL"
```

A download that comes back empty or a few bytes usually means the filename
contains `~`, which curl expands as a glob even under `-g`. Fetch it through
Python with `urllib.parse.quote` on the name.

## How to search

Three questions come up repeatedly. Each has a tool rather than a guess.

**What does the packer accept?** Read the source, not the schema — the
validator's messages are the authoritative list and they name what was wrong:

```bash
grep -n 'bad(' .github/scripts/validate_repo.py
```

**What is actually in a feed?** `scripts/list_feed.py`. `where` finds which
subdirectory holds a package, `matrix` says whether its filenames agree across
architectures, `arches` lists what exists.

```bash
python3 scripts/list_feed.py --match ip-full where
python3 scripts/list_feed.py --match luci-i18n-qbittorrent-zh-cn matrix
```

**What does upstream require?** The recipe, not the package name:

```bash
curl -sL "https://raw.githubusercontent.com/OWNER/luci/master/applications/PKG/Makefile"
tar -xzOf pkg.ipk control.tar.gz | tar -xzOf - ./control | grep -E '^(Package|Depends|Architecture)'
```

`LUCI_DEPENDS` is the authoritative dependency list. Where the two disagree,
the built package's control wins.

**Is a URL still there?** HEAD every one before building:

```bash
python3 scripts/check_urls.py --changed
```

A mirror's directory index may return a page too short to hold entries — some
serve a JavaScript shell to a plain fetch. List against the upstream host and
download from the mirror, not the other way round.

## Find the dependencies, the recipe, and the licence

Do not guess a dependency list from the package name. Read it.

```bash
# From the upstream package itself.
tar -xzOf pkg.ipk control.tar.gz | tar -xzOf - ./control | grep -E '^(Package|Version|Depends|Architecture)'

# From the OpenWrt recipe, when there is one.
curl -sL "https://raw.githubusercontent.com/OWNER/luci/master/applications/PKG/Makefile"
```

`LUCI_DEPENDS` is the authoritative list, and it distinguishes what is required
from what is incidental: `+docker +dockerd` means the CLI applet and the
daemon are both needed, while `docker` alone is not a working setup. An
arch condition such as `@(aarch64||arm||x86_64)` is why a matrix must stop
short — the missing architectures are ones upstream does not build, not gaps
to fill.

Locate each dependency in the feed rather than assuming where it sits;
`scripts/list_feed.py --match NAME where` prints the subdirectory. `ip-full`
is in `base/` and `qbittorrent` in `packages/`, which is not guessable from the
name.

For a binary release, the licence travels with the archive. Check what is in it
rather than assuming:

```bash
tar -tzf archive.tar.gz | grep -i -E 'licen[sc]e|copying|notice'
```

Ship it. An Apache-2.0 or GPL package distributed without its licence text is
a distribution problem, not a formality.

For a LuCI interface, decide `luci = js2` or `lua1` by looking at the source,
not by which backend is in use — it is a property of the package:

```bash
# js2: htdocs/luci-static/resources/view/<name>/*.js, menu under menu.d/*.json
# lua1: luasrc/controller/*.lua
```

## Choose the backend

| Situation | Backend |
|---|---|
| Upstream ships an ipk or apk | `opkg` or `apk`, upstream package as a container |
| Upstream ships only a tarball or bare binary | `pica`, unpacked into `root/` |
| Interface needs a daemon | Both containers in one package |

`pica` carries no container and therefore cannot declare dependencies — any of
`base`/`kmod`/`app` on a `pica` target is rejected at build time. A `pica`
package must be self-sufficient.

For two backends, keep the job's `mgr` as the input side and set `targets` to
both; the workflow builds each backend under `build_output/<backend>/` and
merges the `index.json` files it finds there. `publish` is optional and inert:
`registry_db` points at `r/<mgr>/<id>/db.json`, a tree that no longer exists,
and `keep_release_history` is read by nothing. The templates omit `registry_db`
rather than repeat a dead path.

## The two provider shapes

`github` when the release is on GitHub and assets are matched by regex.
`http_template` for a mirror or a feed directory, one URL per container.
`tarball` when there is no package at all.

`tarball` needs a decision per source:

| Upstream layout | Settings |
|---|---|
| `name-ver-linux_amd64/frpc` | `strip_components: 1` + `include` |
| `name-ver-linux_amd64-musl` — one file, top level | `strip_components: 0` + `rename` |
| `cloudflared-linux-amd64` — bare binary | `rename` + `dest_subdir` |

`rename` applies to an archive of one file and to a bare download alike, and
`chmod 755`s the result. `arch_map` renames architectures for the URL only — a
Go project calls x86_64 `amd64` and aarch64 `arm64` — leaving the manifest's
`arch` and the package filename alone.

`include` also keeps a package small: an upstream archive that ships presets,
man pages and shell completions is dead weight on a device with no shell.

## Bundle what the dependency declaration asks for

A dependency the interface calls at runtime rides along in the same package as
a **separate container** — merged trees lose what the package manager records,
and separate containers stay independently updatable. A dependency every other
package already has stays declared rather than bundled, or it is duplicated
once per package.

A declared name is not free. The client's default feed policy counts the names
this package **requires** — `base` and `app`, not `kmod` — against the device's
feeds, and when any of them is there it installs the dependencies from the
feeds instead of from the artifact's own containers. A wrapped package's app
name is in no feed, that being why it is wrapped, so a single required name a
feed *does* carry is enough to lose the containers — and the install then stops
on a name the feed does not have, which is the package's own. Write those names
with a trailing `?` — `base = luci-lua-runtime?` — which takes them out of the
count and makes a missing one a warning rather than a failure.
`references/habits.md` has the policy in full.

Pin the version in `build.json` rather than following a channel: release
assets carry a vendor build identifier that changes when they rebuild, so
following means the package silently changes identity between builds.

For a package whose daemon lives in another source, prefer the official
release when it is current. Check what the feed actually carries before
assuming a package is stale:

```bash
curl -sL "$FEED/Packages.gz" | zcat | grep -A2 '^Package: NAME$'
```

## Naming

`pkgname` is this source's name; `app` is the upstream name the package
manager installs. They differ when upstream already publishes a package of the
same name — suffix with `-bin` for a bare binary, and with `@fork` when two
forks install the same upstream name.

`appname` is the command on the device and stays the upstream name; renaming
`pkgname` never moves it.

The artifact filename is assembled from these plus the matrix, and carries its
own rules. `references/naming.md` has the layout and real examples.

## Rules the validator enforces

- `ci/<mgr>/` must equal the job's `mgr`, and the manifest path must be
  `src/<mgr>/<id>/manifest`
- `include_dirs` accepts only `scripts`, `root`, `pkgs`
- `build.matrix` needs at least one entry
- the manifest declares `targets`, never `pkgmgr` — the packer writes that
- `targets` must include the job's own `mgr`

Run both before reporting done:

```bash
python3 .github/scripts/validate_repo.py    # built-in
scripts/check_urls.py                       # every URL in the changed jobs
```

## Verify by building

A validator pass proves the configuration is legal, not that the package
works.

```bash
python3 .github/scripts/fetch_assets.py <pkgdir> <pkgdir>/build.json
pica-pack build <pkgdir> --outdir out
tar -tzf out/<backend>/*.pkg.tar.gz
```

Then read what came out: every container present, executables carrying `+x`,
symlinks preserved, no stray archive left under `pkgs/` or `root/`. A container
that silently failed to download is the failure a green build still hides.

Narrow `build.matrix` to one architecture when a download is large, and point
`url_template` at a local file to re-test placement without re-downloading.

## Resources

`assets/` holds templates: `manifest-pica`, `manifest-luci`,
`build-pica.json`, `build-opkg.json`, `build-apk.json`. Copy, then fill in.

`scripts/check_urls.py` HEADs every URL in the changed jobs.

`scripts/list_feed.py` reads a package feed to answer what a directory
actually holds — which architectures exist, which subdirectory a package sits
in, and whether its filenames agree across architectures. Run `where` before
guessing a subdirectory and `matrix` before deciding how many URL templates a
job needs.

`references/naming.md` — the artifact filename, the layers beneath it, and the
version fields.

`references/habits.md` — what keeps a package right the first time. Each entry
there is a mistake that built green and was wrong anyway; read it before
departing from a pattern this skill describes.

`references/providers.md` — each provider's fields, the arch_map rules, the
OpenWrt directory layout per era, the translation-container rule, and the
dependency-bundling decision. Read it when a source's layout matches none of
the shapes above.