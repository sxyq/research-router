---
name: github-local
description: Research public GitHub repositories with the bundled REST adapter. Use for repository discovery, README, tree, source, dependency/configuration, test, Issue, Release, and recent commit evidence.
---

# Bundled GitHub research

Use `scripts/github_public.py` for public GitHub retrieval. It uses the unauthenticated REST API and Python standard library; rate limits or private repositories may make a request unavailable.

1. Discover repositories with `python3 scripts/github_public.py search --query "..."`.
2. Read the selected repository overview and README with `repo --repo owner/name`.
3. Inspect `tree --repo owner/name`, then choose relevant files based on the user's requirements. Common evidence includes project configuration, package manifests, source entrypoints, tests, CI, and examples.
4. Read only selected paths with `file --repo owner/name --path path/to/file`.
5. Use `issues`, `releases`, and `commits` when they answer a question about maintenance, defects, release history, or recent changes.

The script retrieves source material and metadata. The Agent determines which files matter, understands the implementation, compares evidence, and forms the conclusion. Search snippets and repository metadata alone do not support source-level claims.

Do not require GitHub Skills to be installed. Existing `github-search`, `github-analyze`, and `last30days-cn` entries remain optional enhancements.
