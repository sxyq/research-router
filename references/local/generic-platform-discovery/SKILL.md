---
name: generic-platform-discovery
description: Find public candidate pages on registered platforms that lack a bundled native search API, using domain-constrained web discovery without login or API keys.
---

# Bundled generic public discovery

Use `scripts/platform_discovery.py --platform PLATFORM_ID --query "..."` for platforms registered in `registry/platform-domains.json`. The script applies `site:` constraints to Agent-generated queries and calls a public no-key HTML search endpoint. It returns candidate URLs and short excerpts with `evidence_level: discovery`.

This is bounded web discovery, not a claim of native platform search. Search engines may block or rate-limit requests; report `unavailable` or partial results as returned. After discovery, read only selected public URLs. Private, login-only, restricted, or hidden content remains inaccessible.

Use the platform's bundled native adapter when one is registered, such as GitHub, Academic, Stack Overflow, Hacker News, Wikipedia, Linux.do/Discourse, Bilibili, V2EX, 52pojie, or Xueqiu. `AutoCLI` and platform-specific Skills are optional enhancements only.
