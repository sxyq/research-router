---
name: github-local
description: Research public GitHub repositories with bundled multi-path discovery and source retrieval. Use for repository discovery, README, tree, source, dependency/configuration, test, Issue, Release, and recent commit evidence.
---

# Bundled GitHub research

Use the bundled GitHub route for public repository research. It uses Python standard library paths first and keeps external GitHub Skills optional. Rate limits, private repositories, and unavailable public endpoints must be reported as limitations.

## Acquisition order

Separate repository discovery from source retrieval:

1. For repository discovery, use bundled GitHub REST search first. If it errors or returns no candidates, try `gh` only when already installed, using its existing settings without changing them. If neither returns candidates, use a domain-constrained `site:github.com` query and treat its results as discovery candidates only.
2. For source files, reuse a route snapshot when the current route already has one.
3. Otherwise create one temporary shallow Git snapshot for the selected repository and read multiple files locally from that snapshot.
4. If Git is unavailable or the snapshot cannot be created, use the official repository archive.
5. If the archive is unavailable, fetch known file paths from `raw.githubusercontent.com`.
6. Use the REST Contents endpoint only for a small number of selected paths as the final fallback. Do not use it as the normal bulk source reader.

The REST adapter remains useful for repository metadata, default branch, size estimate, tree metadata, Issues, Releases, commits, and the selected-file fallback. Its `repo` command attempts to return README content through Contents; use `snapshot` plus `local-file` when source provenance must use one of the source methods below. REST requests are anonymous by default; if `GITHUB_TOKEN` or `GH_TOKEN` is already set, the adapter may use it. `gh` and those environment values are optional; never prompt for, copy, or persist credentials.

Snapshots live in a temporary directory owned by the current route. For a deep request, keep one snapshot per repository and perform repeated local reads from it. Remove temporary snapshots when the route ends, including partial or failed routes; do not place them in records or the Skill directory.

## Route use

1. Discover repositories with `python3 scripts/github_public.py search --query "..."` and keep the selected repository slug and URL.
2. For `light`, use the search result and `repo --repo owner/name` for summary fields and README. The repo command uses REST README Contents as a bounded light-read shortcut.
3. For `medium` and `deep`, reuse a route snapshot if present; otherwise run `snapshot --repo owner/name --ref DEFAULT_BRANCH --size-kb SIZE_KB` once when those values are already available from `repo`, record `root`, `ref`, and `retrieval_method`, then use `local-tree`, `local-find`, and `local-file` for repeated reads. If the metadata is not available, `snapshot --repo owner/name` performs one public metadata request. Medium focuses on README, manifests/configuration, selected source, and tests. Deep also broadens relevant source, CI, examples, Issues, Releases, and recent commit evidence.
4. Common source candidates include project configuration, package manifests, source entrypoints, tests, CI, and examples. Use the snapshot `ref` as the source revision. If a selected blob is absent from a bounded Git snapshot, `file --repo owner/name --snapshot ROOT --ref REF --path path/to/file` tries raw content and then limited REST Contents.
5. Use `issues` and `releases` for maintenance, defects, and release history. Use `commits --snapshot ROOT` for local Git history when available; REST recent commits are the fallback.

For a snapshot managed by the bundled adapter, use the `root` returned by `snapshot` as the `--snapshot` value:

```bash
python3 scripts/github_public.py snapshot --repo owner/name --ref main --size-kb 1234
# Substitute the `root` value returned above for this example path.
python3 scripts/github_public.py local-tree --snapshot /temporary/path/repo
python3 scripts/github_public.py local-find --snapshot /temporary/path/repo --pattern 'tests/*.py'
python3 scripts/github_public.py local-file --snapshot /temporary/path/repo --path path/to/file
python3 scripts/github_public.py cleanup --snapshot /temporary/path/repo
```

The snapshot command makes a shallow Git clone for repositories whose reported GitHub size is at most 512,000 KiB; it only downloads blobs up to 8 MB. If this fails or size is larger, it tries the official archive. The archive is capped at 64 MB compressed, 256 MB extracted, 20,000 files, and 8 MB per file. Raw files are capped at 8 MB. Local and REST file output is capped at 40,000 characters; REST responses are capped at 8 MB and tree output at 5,000 entries. If archive branch metadata is unavailable, the adapter may try `main` and `master`; record the selected `ref`.

The script and fallback readers retrieve source material and metadata. GitHub may mark a tree as truncated or enforce API/search limits. Continue through the next source path when it can recover the needed content; otherwise report the truncation or missing evidence. The Agent determines which files matter, understands the implementation, compares evidence, and forms the conclusion. Search snippets, repository metadata, and a tree listing alone do not support source-level claims. Keep each output's `retrieval_method` and add the unique methods used to the platform route's `retrieval_methods` field; also record fallback and missing evidence.

Do not require GitHub Skills to be installed. Existing `github-search`, `github-analyze`, and `last30days-cn` entries remain optional enhancements.
