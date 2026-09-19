---
name: research-router
description: Route internet research for bug fixes, open-source or Skill discovery, academic questions, and public community discussions through on-demand Skills. Use when a task needs requirement-driven query expansion, platform selection, layered search depth, source verification, or a recorded final Skill path.
metadata:
  short-description: Route research by scene, depth, platform, and evidence
---

# Research Router

Use this Skill as the independent entrypoint for internet research. It decides what kind of query the user has, how much query expansion is justified, which platform Skills are needed, and which leaf Skill actually ran.

## Skill update check

The official project is [sxyq/research-router](https://github.com/sxyq/research-router). At the beginning of an invocation, before reading the registry, let the Agent run the bundled updater:

```bash
python3 scripts/update-skill.py --apply
```

The script contacts the repository at most once every seven days. It stores only a local check state, preserves `records/`, `tuning/`, and Git metadata, and updates the files managed by this Skill from the official repository. A `cooldown` result is normal; continue with the installed version. When the result is `updated`, reread this `SKILL.md` and the selected registry entries before routing the request. If the user explicitly asks for an immediate update, add `--force-check`.

## Required order

1. Classify the scene before judging depth:
   - `bug-fix`: find solutions, issue discussions, patches, tests, and implementation details.
   - `open-source`: discover projects, Skills, plugins, tools, and community adoption.
   - `academic`: discover papers, authors, venues, and evidence from the paper body or PDF.
   - `community`: find public discussions, practical reports, and experience-based evidence in forums.
2. Select one interaction mode:
   - `direct`: do not ask requirement questions; use the conditions already supplied and start.
   - `clarify`: ask one focused question at a time, update the requirement model, and continue until the target, scope, evidence, and acceptance condition are clear.
3. Convert the requirement into several meaning-preserving query variants. Query variants must come from the user's goal, capability, constraints, platform terms, and evidence requirement. Do not generate random synonyms or rely on one title keyword.
4. Read `registry/platforms.index.json`, `registry/skills.index.json`, and `registry/search-components.index.json`, then read the selected registered platform/Skill entries. Load only the selected external Skill's `SKILL.md` and its directly relevant references. Do not scan the local Skill collection and do not make MCP a required dependency.
   The platform quick index is below; read [the full platform index](references/platform-index.md) when the request names a catalog-only platform or needs the adapter limits. Catalog-only rows record upstream coverage and require a runtime availability check before selection.
   For `community`, prefer a platform-specific public-forum adapter. The 52pojie adapter reads public listings, RSS, the hot guide, and selected thread pages; it does not use login-only or attachment routes. For public API discovery, use `scripts/fast_search.py` and return compact JSON before selecting pages for reading.
5. Select `light`, `medium`, or `deep` from query count, evidence depth, and parallel work. Platform count comes from the requirement and does not determine depth.
6. Deduplicate overlapping candidates, keep at most two platform-specific Skills per platform, and preserve a general multi-platform Skill when it reduces repeated work.
7. Build a dispatch packet for every selected platform. The packet includes the platform tier, user goal, platform-specific query variants, evidence requirement, depth, Skill order, script or adapter path, and the stop condition.
8. Execute the selected Skills. One Agent owns one platform; if that platform has multiple Skills, that Agent runs them sequentially. `medium` and `deep` may run platform Agents in parallel. The main Agent merges their reports, removes duplicate sources, and reviews evidence.
9. Move the route through `planned` -> `running` -> `completed`, `partial`, or `failed`. Keep `router_path`, `executed_leaf_skills`, `source_coverage`, `stop_reason`, and `route_evaluation` in the route record.
10. Write one experience record per executed Skill and per selected platform under `records/experience/`. Use `scripts/update-experience.py` to derive JSONL entries from the route record. Keep raw result bodies, credentials, and browser state outside the record.
11. Return a concise result with the answer, actual source scope, final Skill path, evidence gaps, route evaluation, and the next action if one is required. When the user later provides a score, write a matching file under `records/feedback/YYYY-MM-DD/`.

## Platform quick index

Use this table to map a platform to its entry Skill and script or adapter. `external` means the route is supplied by an installed third-party Skill or CLI. The local quick-search script only uses public endpoints and does not require an API key.

| Tier | Platform | Entry Skill(s) | Script or adapter |
| --- | --- | --- | --- |
| 1 | GitHub | `github-search` -> `github-analyze` | `scripts/fast_search.py --provider github`; source analysis remains external |
| 1 | Academic | `autocli`, `anysearch`, `paper-research-router`, `literature-evidence-audit` | `scripts/fast_search.py --provider openalex|arxiv|crossref`; PDF evidence remains external/local |
| 1 | Google Scholar | `paper-research-router` -> `literature-evidence-audit` | `scripts/fast_search.py --provider google-scholar`; selected local PDFs use `academic-evidence/scripts/extract_paper_brief.py` |
| 2 | 52pojie / 吾爱破解 | `52pojie-research` | `references/local/52pojie-research/scripts/fetch.py` |
| 2 | Stack Overflow | `autocli`, `anysearch`; optional `github-analyze` | `scripts/fast_search.py --provider stackoverflow`; repository-linked bugs may continue to GitHub |
| 2 | Linux.do | `autocli` | `external` CLI; use the Discourse adapter only after endpoint verification |
| 2 | V2EX | `autocli`; deep may add `last30days-cn` | `scripts/fast_search.py --provider ddgs` is optional discovery; no local V2EX adapter |
| 2 | Discourse technical forums | `forum-search` | `scripts/discourse_search.py` |
| 3 | Bilibili | `autocli`; deep may add `last30days-cn` | `scripts/fast_search.py --provider ddgs` only for public discovery; detail remains external |
| 3 | 中国抖音 | `douyin-skills`; deep may add `last30days-cn` | `scripts/fast_search.py --provider ddgs` only for public discovery; detail remains external |
| 3 | TikTok | `autocli` | `scripts/fast_search.py --provider ddgs` only for public discovery; detail remains external |
| 3 | 小红书 | `autocli`, `xiaohongshu-skills`; deep may add `last30days-cn` | `scripts/fast_search.py --provider ddgs` only for public discovery; detail remains external |

The full index also records the additional Hacker News, Dev.to, Lobsters, Reddit, 知乎, YouTube, 微博, 豆瓣, 微信读书, 雪球, BOSS 直聘, Twitter/X, and desktop-app entries declared by AutoCLI. They remain catalog-only until their external runtime is available. Discourse is a registered local protocol route; the selected forum base URL must still be supplied and verified.

## No-key quick search components

The component-to-platform mapping is maintained in `registry/search-components.index.json`. Use `scripts/fast_search.py` for compact public discovery without credentials:

```bash
python3 scripts/fast_search.py --provider github --query "skill router" --limit 5
python3 scripts/fast_search.py --provider stackoverflow --query "python async http" --limit 5
python3 scripts/fast_search.py --provider arxiv --query "agentic search" --limit 5
python3 scripts/fast_search.py --provider google-scholar --query "agentic search" --limit 5
python3 scripts/fast_search.py --provider discourse --base-url https://users.rust-lang.org --query "webview bridge" --limit 5
```

Supported public providers are GitHub, Stack Exchange, Hacker News, Dev.to, Wikipedia, OpenAlex, Crossref, arXiv, Google Scholar, Discourse, RSS/Atom, and optional `ddgs`. Results contain titles, URLs, short excerpts, dates, source identifiers, and `evidence_level: discovery`; they do not contain raw pages. Google Scholar also returns authors, citation/version counts, and a PDF candidate when exposed. Its result text is snippet-only.

`ddgs`, SearXNG, Semantic Scholar, and content-extraction packages are registered as optional no-key candidates. Their availability, rate limits, or package installation must be confirmed at runtime. Paid or credentialed services are outside this default path.

For academic requests, keep the retrieval stages separate:

```text
discovery -> selected papers -> paper-brief -> explicit full-audit
```

Use `paper-brief` for an abstract, section outline, and author-stated contributions. Use `academic-evidence/scripts/extract_paper_brief.py` for a local PDF. Run the full evidence route only when the user asks for detailed methods, results, limitations, or quotations. This sequence applies to the general `academic` route as well as Google Scholar.

## Route lifecycle and platform dispatch

The platform index is the dispatch table for the entry Skill. It is used to create one bounded task per selected platform.

```text
user request
  -> requirement model and query variants
  -> registered platform and Skill match
  -> one dispatch packet per platform
  -> platform Agents run their Skill order
  -> main Agent merges sources and failures
  -> route evaluation and experience records
  -> answer with scope and stop reason
```

Each platform Agent receives:

- `platform_id`, tier, access scope, and selected adapter;
- the user goal and only the query variants relevant to that platform;
- the ordered Skill list and local script path when one exists;
- required evidence depth and the stop condition;
- the expected return fields: `executed_skills`, source URLs, `source_coverage`, failures, and `stop_reason`.

The main Agent keeps the `router_path` and evaluates the complete route after all platform reports return. A catalog-only platform can enter this flow only after its external Skill or CLI is available.

## Route-level evaluation

Evaluate the route outcome, not only whether a Skill was called. Record scores from 0 to 10 for problem coverage, evidence directness, recency, and source deduplication. Also record query count, Skill calls, Agent count, unconfirmed items, and the overall score. If a dimension cannot be supported by the collected sources, leave it unconfirmed and lower the route status to `partial`.

Read [route-evaluation.md](references/route-evaluation.md) before assigning these fields.

## Experience memory

Experience is stored separately from `SKILL.md` so route-specific observations do not enlarge the entrypoint. Use one JSONL file per Skill under `records/experience/skills/` and one per platform under `records/experience/platforms/`. Record useful query forms, access limits, source coverage, failures, fallback routes, and route scores. A single successful route is a sample; repeated outcomes are needed before changing shared routing rules.

## Depth defaults

- `light`: about 2–4 requirement-derived query variants; one Agent may use one multi-platform Skill. Add a specialist only for an explicit capability gap.
- `medium`: about 5–10 variants; use one Agent per requested platform and the highest-ranked applicable Skill or sequential specialist supplement.
- `deep`: 11 or more variants, or a request for source-level/full-text evidence; use parallel platform Agents and run each platform's matched Skills sequentially. Do not use a fixed budget as a reason to omit a required source check.

Read the relevant reference before applying details:

- [scene-routing.md](references/scene-routing.md)
- [depth-routing.md](references/depth-routing.md)
- [interaction-modes.md](references/interaction-modes.md)
- [query-generation.md](references/query-generation.md)
- [evidence-requirements.md](references/evidence-requirements.md)
- [deduplication.md](references/deduplication.md)
- [scoring-policy.md](references/scoring-policy.md)
- [failure-attribution.md](references/failure-attribution.md)
- [search-components.md](references/search-components.md) when using the no-key public search adapters

## Boundaries

- Registry entries describe known routes and catalog-only external Skills; they do not prove that a third-party Skill is installed or currently runnable.
- Search components describe public access paths; they do not prove that a remote endpoint will remain available or that discovery snippets support a detailed claim.
- Do not copy external Skills into this directory. Resolve an installed Skill by its canonical name/path, or report it unavailable and ask before installation.
- Do not write route records, private credentials, browser cookies, or raw research caches into a project directory.
- The bundled quick-search script sends no API keys, cookies, or login data. Respect public endpoint rate limits and stop on authentication, access, or rate-limit responses.
- GitHub discovery can use `github-search`; a source-level request must continue to `github-analyze` and inspect README, tree, source, dependencies, tests, Issues, and Releases.
- Academic discovery can use `autocli`, `anysearch`, or `fast_search.py --provider google-scholar`; a selected-paper brief may use `literature-evidence-audit` in `paper-brief` mode, while detailed claims must continue to the primary paper body or PDF.
