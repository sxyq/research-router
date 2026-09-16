# Research Router Platform Index

This index is the source for platform routing in this repository. `router-registered` entries have a platform JSON file and can be selected by the Router. `upstream-catalog-only` entries come from an external Skill's declared coverage; they are discovery records until the external Skill or CLI is available in the running environment.

## Tier meaning

| Tier | Use | Current examples |
| --- | --- | --- |
| 1 | Core source or primary implementation evidence | GitHub, academic |
| 2 | Technical communities and specialist public discussions | 52pojie, Stack Overflow, Linux.do, V2EX |
| 3 | Supplemental discovery, media, social, finance, or desktop sources | Bilibili, Douyin, TikTok, Xiaohongshu |

The tier describes research priority and evidence strength. It does not prove that a platform is reachable in the current session.

## Router-registered platforms

| Tier | Platform (`platform_id`) | Entry Skills | Script or adapter | Status and access scope |
| --- | --- | --- | --- | --- |
| 1 | GitHub (`github`) | `github-search` -> `github-analyze`; deep may add `last30days-cn` | External Skills; no local Router script | Public repositories. Source-level claims require tree, source, dependencies, tests, Issues, and Releases. |
| 1 | Academic (`academic`) | `autocli`, `anysearch`, `paper-research-router`, `literature-evidence-audit` | External or installed Skills; no local Router script | Paper discovery and primary PDF/body evidence. |
| 2 | 吾爱破解 (`52pojie`) | `52pojie-research` | `references/local/52pojie-research/scripts/fetch.py` | Local public HTML/RSS/thread reader. No login, captcha, member pages, redirects, or attachments. |
| 2 | Stack Overflow (`stackoverflow`) | `autocli`, `anysearch`; `github-analyze` only for a repository-linked bug | External Skills/CLI; no local Router script | Public questions, answers, and code patterns. |
| 2 | Linux.do (`linux-do`) | `autocli` | External CLI; no local Router script | Public or browser-backed community content; login state can affect access. |
| 2 | V2EX (`v2ex`) | `autocli`; deep may add `last30days-cn` | External CLI; no local Router script | Topics, nodes, replies, and recent community discussion. |
| 3 | Bilibili (`bilibili`) | `autocli`; deep may add `last30days-cn` | External CLI; no local Router script | Search, hot lists, metadata, and subtitles when available. |
| 3 | 中国抖音 (`douyin`) | `douyin-skills`; deep may add `last30days-cn` | External Skill; no local Router script | Public video and topic discovery. Explicit user request required for light routing. |
| 3 | TikTok (`tiktok`) | `autocli` | External CLI; no local Router script | Public video, profile, and engagement metadata. |
| 3 | 小红书 (`xiaohongshu`) | `autocli`, `xiaohongshu-skills`; deep may add `last30days-cn` | External Skills/CLI; no local Router script | Notes, details, comments, and content data when available. |

The local 52pojie child Skill is the only registered platform route with a bundled retrieval script in this repository. Other rows point to external Skills or CLIs and must retain that limitation in the final result.

## Upstream AutoCLI catalog

The AutoCLI Skill README explicitly lists the following additional platforms. They are recorded here so platform discovery does not lose the coverage of the child Skill. They are not active Router platform entries in this repository, and no local script path is assigned to them.

| Tier | Platform (`platform_id`) | Entry Skill | Script or adapter | Status |
| --- | --- | --- | --- | --- |
| 2 | Hacker News (`hacker-news`) | `autocli` | External `autocli` CLI; use `autocli --help` for the installed command | Upstream catalog only; public mode |
| 2 | Dev.to (`dev-to`) | `autocli` | External `autocli` CLI | Upstream catalog only; public mode |
| 2 | Lobsters (`lobsters`) | `autocli` | External `autocli` CLI | Upstream catalog only; public mode |
| 2 | Reddit (`reddit`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 2 | 知乎 (`zhihu`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 2 | Wikipedia (`wikipedia`) | `autocli` | External `autocli` CLI | Upstream catalog only; public mode |
| 2 | BBC (`bbc`) | `autocli` | External `autocli` CLI | Upstream catalog only; public mode |
| 3 | Twitter/X (`twitter-x`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | YouTube (`youtube`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | 微博 (`weibo`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | 豆瓣 (`douban`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | 微信读书 (`weread`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | 雪球 (`xueqiu`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | BOSS 直聘 (`boss-zhipin`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | Facebook (`facebook`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | Instagram (`instagram`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | 即刻 (`jike`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | Google (`google`) | `autocli` | External `autocli` CLI; browser may be required for some commands | Upstream catalog only; public/browser mode |
| 3 | Bloomberg (`bloomberg`) | `autocli` | External `autocli` CLI | Upstream catalog only; public/browser mode |
| 3 | Medium (`medium`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | Substack (`substack`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | LinkedIn (`linkedin`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | Yahoo Finance (`yahoo-finance`) | `autocli` | External `autocli` CLI with browser session | Upstream catalog only; browser mode |
| 3 | Cursor (`cursor`) | `autocli` | External `autocli` desktop command | Upstream catalog only; desktop mode |
| 3 | Notion (`notion`) | `autocli` | External `autocli` desktop command | Upstream catalog only; desktop mode |
| 3 | ChatGPT (`chatgpt`) | `autocli` | External `autocli` desktop command | Upstream catalog only; desktop mode |
| 3 | Discord (`discord`) | `autocli` | External `autocli` desktop command | Upstream catalog only; desktop mode |
| 3 | Codex (`codex`) | `autocli` | External `autocli` desktop command | Upstream catalog only; desktop mode |

AutoCLI also advertises more sites without stable platform names in its README. Those unnamed sites are not fabricated into this registry. The README's `Arxiv` entry is normalized to the registered `academic` platform.

## Selection rules

1. Match a user-requested platform against the registered table first.
2. For a catalog-only platform, verify that the named external Skill or CLI is installed and usable before selecting it.
3. Never use an upstream catalog row as proof of current access, successful execution, or evidence quality.
4. Keep the local `52pojie-research` script limited to public forum retrieval and cite the exact page URL for forum-derived claims.
