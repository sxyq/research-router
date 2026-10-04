---
name: research-router
description: Route internet research for bug fixes, open-source or Skill discovery, academic questions, and public community discussions through on-demand Skills. Use when a task needs requirement-driven query expansion, platform selection, layered search depth, source verification, or a recorded final Skill path.
metadata:
  short-description: Route research by scene, depth, platform, and evidence
---

# Research Router

Use this Skill as the independent entrypoint for internet research. The Agent decides what kind of query the user has, how much query expansion is justified, and which platforms are relevant; the Router resolves registered Skills and records which leaf Skill actually ran.

## Fresh-install behavior

The repository includes the default public research path: GitHub repository/source retrieval, Academic and Google Scholar discovery with public metadata/HTML reading, Bilibili search, V2EX public reads, Discourse search, 52pojie public reading, and domain-constrained public discovery for registered sites without a bundled native endpoint. These default paths use repository files, Python standard library, and public network endpoints. External Skills and CLIs listed under `optional_enhancements` can add coverage, but their absence does not invalidate a bundled route.

YouTube rich metadata/subtitles, Twitter/X native search, authenticated pages, and desktop-only platforms can still require optional runtimes or an allowed session. Do not install packages, sign in, or read browser state automatically.

## Agent 与 Python 的职责边界

需求理解属于当前 Agent 的语义工作。Agent 读取当前请求和本轮对话中直接相关的上下文，理解用户真正要解决的问题，再完成：

```text
Understand
→ Decompose
→ Infer
→ Associate
→ Expand
→ Recombine
```

这一步由 Agent 负责：

- 构建 `target`、`goal`、`capabilities`、`context`、`constraints`、`evidence`、`time`、`explicit_platforms`；
- 解析“这个项目”“它”“那个工具”等上下文指代；
- 区分用户明确提出的内容、合理推导、查询扩展和未知项；
- 联想相关实体、名称变体、中英文表达和互补的查询方向；
- 判断 `direct` / `clarify`、主 `scene`、`depth`、平台范围和 platform-specific query rewrite。

不得用正则、关键词命中、固定模板或查询数量来代替这些语义判断。关键词可以出现在案例和示例中，但不能成为正式路由依据。不要输出或保存模型内部推理，只保存结构化需求、查询、平台选择和简短选择结论。

Python 脚本和 Registry 只做确定性工作：平台别名归一、Registry 读取、平台存在性验证、Tier/Skill/script/component/access 字段补全、结构校验、平台适配器调用和结果规范化。`scripts/route_plan.py` 接收 Agent 已生成的 JSON 计划；它不接收自然语言，也不猜测 `target`、`scene`、`depth` 或查询词。

## Skill update check

The official project is [sxyq/research-router](https://github.com/sxyq/research-router). Do not run the updater automatically during a research route. For read-only Skill audits, local Skill inventory, and rules reviews, read the currently installed files and preserve the audit's read-only boundary. Use the updater only when the user asks for a source update and the repository state has been reviewed:

```bash
python3 scripts/update-skill.py --apply
```

The script contacts the repository at most once every seven days. It stores only a local check state, preserves `records/`, `tuning/`, and Git metadata, and updates the files managed by this Skill from the official repository. A `cooldown` result is normal; continue with the installed version. When the result is `updated`, reread this `SKILL.md` and the selected registry entries before routing the request. If the user explicitly asks for an immediate update, add `--force-check`.

## Required order

1. Let the Agent build a requirement model before choosing a scene. Keep these slots when present:
   - `target`: the object being researched;
   - `goal`: the decision or answer the user needs;
   - `capabilities`: capabilities that must be covered;
   - `context`: versions, frameworks, environment, or use case;
   - `constraints`: cost, license, language, access, or other limits;
   - `evidence`: README, source, Issue, forum body, video metadata, paper body, or PDF;
   - `time`: recency or date range;
   - `explicit_platforms`: platforms named by the user.
   Missing slots stay empty. Do not compress the request into one keyword. Use the current conversation to resolve references before asking for clarification.
2. Choose one interaction mode:
   - `direct`: the target and goal are usable; start with the supplied conditions and record any remaining evidence gap.
   - `clarify`: ask one focused question only when a missing target, scope, or acceptance condition would change the route.
   A `direct` plan requires non-empty `requirement.target`, `requirement.goal`, at least one base query, at least one selected platform, and at least one platform-specific query per selected platform. A `clarify` plan may defer queries and platforms; any platform already present must still resolve through Registry and remain within `explicit_platforms` when that scope is set.
3. Classify the main scene:
   - `bug-fix`: find solutions, issue discussions, patches, tests, and implementation details.
   - `open-source`: discover projects, Skills, plugins, tools, and community adoption.
   - `academic`: discover papers, authors, venues, and evidence from the paper body or PDF.
   - `community`: find public discussions, practical reports, and experience-based evidence in forums.
4. Choose `light`, `medium`, or `deep` from platform breadth, parallel platform Agents, source depth, and execution scope. Query count does not choose depth. User platform limits override default breadth.
5. Generate a generous base query set from the requirement model through Agent reasoning, then rewrite it for each selected platform. Read [query-generation.md](references/query-generation.md). Never send the same unmodified query set to every platform.
6. Read `registry/platforms.index.json`, `registry/skills.index.json`, and `registry/search-components.index.json`, then read the selected platform entry and bundled Skill instructions. Use `scripts/route_plan.py` only after the Agent has produced the structured plan. Load an external Skill only when its files are already available and it adds needed coverage; its absence must leave the bundled route intact. Do not scan the local Skill collection and do not make MCP a required dependency.
   The platform quick index is below; read [the full platform index](references/platform-index.md) when a request names a catalog-only platform or needs adapter limits. Catalog-only rows can use their registered bundled public-discovery route; probe a runtime only when choosing an optional external enhancement.
   For `community`, prefer a platform-specific public-forum adapter. The 52pojie adapter reads public listings, RSS, the hot guide, and selected thread pages; it does not use login-only or attachment routes. For public API discovery, use `scripts/fast_search.py` and return compact JSON before selecting pages for reading.
7. Deduplicate overlapping candidates, keep at most two platform-specific Skills per platform, and preserve a bundled general Skill when it reduces repeated work. Use an external general Skill only when it is already available and improves the selected route.
8. Build one dispatch packet per selected platform. The Agent supplies the platform, goal, queries, evidence requirement, and stop condition. Registry resolution supplies the tier, bundled Skill order, script paths, search components, adapter type, access mode, depth routes, and optional enhancements. Missing optional enhancements must not mark the bundled platform route failed.
9. If YouTube or Twitter/X was selected, run `scripts/probe_runtime.py` for only those selected platform IDs. This reads local executable state; it does not prove search worked. Do not probe at Router initialization, inspect browser cookies, run login commands, or start OpenCLI.
10. Execute selected Skills. One Agent owns one platform; Skills within that platform run sequentially. `medium` and `deep` may run different platform Agents in parallel. The main Agent merges reports, removes duplicate sources, and reviews evidence.
11. Move the route through `planned` -> `running` -> `completed`, `partial`, or `failed`. Keep the requirement model, base `query_variants`, platform `queries`, `router_path`, `executed_leaf_skills`, `source_coverage`, `stop_reason`, and `route_evaluation` in the route record.
12. Write one experience record per executed Skill and per selected platform under `records/experience/`. Use `scripts/update-experience.py` to derive JSONL entries from the route record. Keep raw result bodies, credentials, and browser state outside the record.
13. Return a concise result with the answer, actual source scope, final Skill path, evidence gaps, route evaluation, and the next action if one is required. When the user later provides a score, write a matching file under `records/feedback/YYYY-MM-DD/`.

## Platform quick index

Use this table to map a platform to its bundled entry Skill and script. External Skills, CLIs, or MCPs appear in `optional_enhancements` and can add coverage when already available; they are not required by the default route. Bundled discovery scripts use public endpoints and need no API key. Exa is an optional no-key MCP component, not a platform; it still needs an existing Exa MCP configuration.

| Tier | Platform | Entry Skill(s) | Script or adapter |
| --- | --- | --- | --- |
| 1 | GitHub | `github-local` | `scripts/github_public.py`; selected-file implementation analysis is performed by the Agent |
| 1 | Academic | `academic-local` | `scripts/fast_search.py` + `academic-evidence/scripts/academic_public.py` |
| 1 | Google Scholar | `academic-local` | `scripts/fast_search.py --provider google-scholar` + bundled metadata/HTML reader |
| 2 | 52pojie / 吾爱破解 | `52pojie-research` | `references/local/52pojie-research/scripts/fetch.py` |
| 2 | Stack Overflow | `generic-platform-discovery` | `scripts/platform_discovery.py` uses the bundled Stack Exchange public search provider |
| 2 | Linux.do | `generic-platform-discovery` | Bundled public Discourse search endpoint |
| 2 | V2EX | `v2ex-public` | `scripts/v2ex_public.py`; AutoCLI and last30days-cn are optional |
| 2 | Discourse technical forums | `forum-search` | `scripts/discourse_search.py` |
| 2 | YouTube | `generic-platform-discovery` | Public URL discovery is bundled; `yt-dlp` is optional for metadata/subtitles |
| 2 | Twitter / X | `generic-platform-discovery` | Public URL discovery is bundled; native CLI/session is optional |
| 3 | Bilibili | `bilibili-public` | `scripts/bilibili_public.py`; AutoCLI/last30days-cn are optional |
| 3 | 中国抖音 | `generic-platform-discovery` | Bundled public site discovery; detail Skills are optional |
| 3 | TikTok | `generic-platform-discovery` | Bundled public site discovery; session features are optional |
| 3 | 小红书 | `generic-platform-discovery` | Bundled public site discovery; detail Skills are optional |
| 3 | 雪球 | `xueqiu-public` | `scripts/xueqiu_public.py` |

Other catalog platforms use the bundled `generic-platform-discovery` route for domain-constrained public candidate discovery. Their platform-native detail, account pages, and desktop actions remain optional. `registry/platform-domains.json` records the domains and any bundled native public provider.

## No-key quick search components

The component-to-platform mapping is maintained in `registry/search-components.index.json`. Use `scripts/fast_search.py` for compact public discovery without credentials:

```bash
python3 scripts/github_public.py search --query "skill router" --limit 5
python3 scripts/fast_search.py --provider stackoverflow --query "python async http" --limit 5
python3 scripts/fast_search.py --provider arxiv --query "agentic search" --limit 5
python3 scripts/fast_search.py --provider google-scholar --query "agentic search" --limit 5
python3 scripts/fast_search.py --provider discourse --base-url https://users.rust-lang.org --query "webview bridge" --limit 5
```

Supported public providers include Stack Exchange, Hacker News, Dev.to, Wikipedia, OpenAlex, Crossref, arXiv, Google Scholar, Discourse, RSS/Atom, and optional `ddgs`. GitHub source research uses `github_public.py`; results include repository metadata, README, tree, selected files, Issues, Releases, and commit metadata. Search results are discovery evidence until the Agent reads selected sources. Google Scholar may return snippets only.

For registered platforms without a bundled native endpoint, `scripts/platform_discovery.py --platform <id> --query "..."` uses Bing RSS with a public DuckDuckGo HTML fallback, constrains the query to Registry domains, and filters links by those domains. It finds public candidate URLs only; it does not claim native APIs or account access.

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
- the requirement model, user goal, and only the rewritten queries relevant to that platform;
- the ordered Skill list and local script path when one exists;
- required evidence depth and the stop condition;
- the expected return fields: `executed_skills`, source URLs, `source_coverage`, failures, and `stop_reason`.

The main Agent keeps the `router_path` and evaluates the complete route after all platform reports return. A catalog-only platform can use its registered bundled public-discovery route; native details may need an optional external runtime.

## Route-level evaluation

Evaluate the route outcome, not only whether a Skill was called. Record scores from 0 to 10 for problem coverage, evidence directness, recency, and source deduplication. Also record query count, Skill calls, Agent count, unconfirmed items, and the overall score. If a dimension cannot be supported by the collected sources, leave it unconfirmed and lower the route status to `partial`.

Read [route-evaluation.md](references/route-evaluation.md) before assigning these fields.

## Experience memory

Experience is stored separately from `SKILL.md` so route-specific observations do not enlarge the entrypoint. Use one JSONL file per Skill under `records/experience/skills/` and one per platform under `records/experience/platforms/`. Record useful query forms, access limits, source coverage, failures, fallback routes, and route scores. A single successful route is a sample; repeated outcomes are needed before changing shared routing rules.

## Depth defaults

Depth describes research breadth and evidence work. It is selected before query expansion and is never inferred from query count.

- `light`: one main platform Agent, with a fallback only for a clear gap. Still generate roughly 12–16 useful base variants.
- `medium`: two or three relevant platform Agents when the request allows it, with sequential Skills inside each platform. Generate roughly 16–24 useful base variants.
- `deep`: three or more relevant platform Agents when the request allows it, parallel dispatch, source/full-text/comment-chain verification, and sequential platform adapters. Generate roughly 20–30 variants or more when the requirement needs them.

An explicit platform scope always wins. A deep YouTube request remains YouTube-only and gains more queries, metadata, subtitles, and source reading rather than unrelated platforms.

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

- Registry entries describe bundled routes and optional external enhancements; they do not prove that an external Skill or runtime is installed or currently runnable.
- Search components describe public access paths; they do not prove that a remote endpoint will remain available or that discovery snippets support a detailed claim.
- Do not copy external Skills into this directory. Resolve an installed Skill by its canonical name/path, or report it unavailable and ask before installation.
- Agent-Reach is a reference for platform capabilities, not a second Router. Absorb only useful adapters: Bilibili public search, V2EX public API reads, Xueqiu public endpoints, and external-tool mappings for YouTube and Twitter/X. Do not copy its global trigger rules or run its all-channel diagnosis as a routine route step.
- Do not write route records, private credentials, browser cookies, or raw research caches into a project directory.
- The bundled quick-search script sends no API keys, cookies, or login data. Respect public endpoint rate limits and stop on authentication, access, or rate-limit responses.
- GitHub routes use the bundled `github-local` Skill at all depths. Increase the read scope from repository overview/README to tree, selected source/config/test files, Issues, Releases, and commits according to the Agent's depth plan.
- Academic routes use the bundled `academic-local` Skill at all depths. It combines public discovery, Crossref/arXiv metadata, and selected public HTML evidence. Use the existing PDF scripts when appropriate; `pypdf` is optional and is never installed automatically. `anysearch`, `paper-research-router`, and `literature-evidence-audit` are optional enhancements.
