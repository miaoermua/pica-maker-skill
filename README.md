# pica-maker-skill

让 Agent 帮助创建、更新、维护 [pica-nest](https://github.com/miaoermua/pica-nest) 软件源里的 Pica 软件包。

| 文件 | 内容 |
|---|---|
| `SKILL.md` | 入口：仓库布局、`python3 -m ci.nest` 工作流、选后端与 source 类型、版本与声明规则 |
| `references/sources.md` | `feed` / `github` / `url` / `archive` 各字段、架构映射、feed 布局、依赖打包决策、ADB 容器 |
| `references/naming.md` | 产物文件名、版本规范化、文件名不可变 |
| `references/habits.md` | 踩过的坑：CI 常见报错与原因、libc/字节序、feed 各架构不同步等 |
| `scripts/feed_lookup.py` | 用 pica-nest 自己的解析器按架构查询 feed 包（版本、子目录、真实文件名） |

模板不在本仓库：用 pica-nest 的 `python3 -m ci.nest new <mgr>/<id> --source <type>`，它复制 `ci/templates/`。

适用于 pica-nest 的 `packages/<mgr>/<id>/` 布局（2026-10 重建后）。旧的 `src/` + `ci/` 布局、`.github/scripts/*.py` 与 `http_template`/`tarball` provider 已不再适用。
