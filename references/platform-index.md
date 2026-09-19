# Research Router Platform Index

This index is the source for platform routing in this repository. `router-registered` entries have a platform JSON file and can be selected by the Router. `upstream-catalog-only` entries come from an external Skill's declared coverage; they are discovery records until the external Skill or CLI is available in the running environment.

## Tier meaning

| Tier | Use | Current examples |
| --- | --- | --- |
| 1 | Core source or primary implementation evidence | GitHub, academic, Google Scholar |
| 2 | Technical communities and specialist public discussions | 52pojie, Stack Overflow, Linux.do, V2EX |
| 3 | Supplemental discovery, media, social, finance, or desktop sources | Bilibili, Douyin, TikTok, Xiaohongshu |

The tier describes research priority and evidence strength. It does not prove that a platform is reachable in the current session.

## Router-registered platforms

| Tier | Platform (`platform_id`) | Entry Skills | Script or adapter | Status and access scope |
| --- | --- | --- | --- | --- |
| 1 | GitHub (`github`) | `github-search` -> `github-analyze`; deep may add `last30days-cn` | `scripts/fast_search.py --provider github`; source analysis remains external | Public repositories. Source-level claims require tree, source, dependencies, tests, Issues, and Releases. |
| 1 | Academic (`academic`) | `autocli`, `anysearch`, `paper-research-router`, `literature-evidence-audit` | `scripts/fast_search.py --provider openalex|arxiv|crossref`; PDF evidence remains external/local | Paper discovery and primary PDF/body evidence. |
| 1 | Google Scholar (`google-scholar`) | `paper-research-router` -> `literature-evidence-audit` | `scripts/fast_search.py --provider google-scholar`; `academic-evidence/scripts/extract_paper_brief.py` for selected local PDFs | Public HTML discovery without a key. Results include title, author, year, citations, versions, PDF candidate, and snippet-only text. Enrich selected papers before evidence claims. |
| 2 | 吾爱破解 (`52pojie`) | `52pojie-research` | `references/local/52pojie-research/scripts/fetch.py` | Local public HTML/RSS/thread reader. No login, captcha, member pages, redirects, or attachments. |
| 2 | Stack Overflow (`stackoverflow`) | `autocli`, `anysearch`; `github-analyze` only for a repository-linked bug | `scripts/fast_search.py --provider stackoverflow`; repository-linked bugs may continue to GitHub | Public questions, answers, and code patterns. |
| 2 | Linux.do (`linux-do`) | `autocli` | External CLI; Discourse adapter is a candidate after endpoint verification | Public or browser-backed community content; login state can affect access. |
| 2 | V2EX (`v2ex`) | `autocli`; deep may add `last30days-cn` | Optional `scripts/fast_search.py --provider ddgs`; no local V2EX adapter | Topics, nodes, replies, and recent community discussion. |
| 2 | Discourse 技术论坛 (`discourse`) | `forum-search` | `scripts/discourse_search.py` | Local read-only JSON adapter. Requires a public Discourse endpoint and a selected forum base URL. |
| 3 | Bilibili (`bilibili`) | `autocli`; deep may add `last30days-cn` | Optional `scripts/fast_search.py --provider ddgs` for public discovery; detail remains external | Search, hot lists, metadata, and subtitles when available. |
| 3 | 中国抖音 (`douyin`) | `douyin-skills`; deep may add `last30days-cn` | Optional `scripts/fast_search.py --provider ddgs` for public discovery; detail remains external | Public video and topic discovery. Explicit user request required for light routing. |
| 3 | TikTok (`tiktok`) | `autocli` | Optional `scripts/fast_search.py --provider ddgs` for public discovery; detail remains external | Public video, profile, and engagement metadata. |
| 3 | 小红书 (`xiaohongshu`) | `autocli`, `xiaohongshu-skills`; deep may add `last30days-cn` | Optional `scripts/fast_search.py --provider ddgs` for public discovery; detail remains external | Notes, details, comments, and content data when available. |

The repository now has two kinds of local retrieval: platform readers (`52pojie-research` and `forum-search`) and the compact public API script (`scripts/fast_search.py`). Other rows still point to external Skills, browser sessions, or catalog-only adapters and must retain that limitation in the final result.

## Search component mapping

The complete component registry is [registry/search-components.index.json](../registry/search-components.index.json). Every component in the default path has `requires_api_key: false`; optional packages and public instances remain runtime candidates.

| Component | Platform mapping | Local entry | Output and evidence |
| --- | --- | --- | --- |
| `fast-search` | GitHub, Stack Overflow, Academic, Discourse, Hacker News, Dev.to, Wikipedia | `scripts/fast_search.py` | Compact JSON; `discovery` evidence |
| `ddgs` | Video, social, Google and catalog-only web platforms | Optional provider in `scripts/fast_search.py` | Title, URL, excerpt; discovery only |
| `github-search-api` | GitHub | `fast_search.py --provider github` | Repository candidates; source reading follows |
| `stackexchange-api` | Stack Overflow | `fast_search.py --provider stackoverflow` | Questions and answer metadata |
| `hn-algolia` | Hacker News | `fast_search.py --provider hacker-news` | Stories and comments |
| `devto-api` | Dev.to | `fast_search.py --provider dev-to` | Tag-oriented article discovery |
| `wikipedia-api` | Wikipedia | `fast_search.py --provider wikipedia` | Page candidates and snippets |
| `openalex-api` | Academic | `fast_search.py --provider openalex` | Work metadata and citation counts |
| `arxiv-api` | Academic | `fast_search.py --provider arxiv` | Preprint metadata and abstracts |
| `crossref-api` | Academic | `fast_search.py --provider crossref` | DOI and publication metadata |
| `google-scholar-html` | Google Scholar | `fast_search.py --provider google-scholar` | Candidate title, authors, year, citation/version counts, PDF candidate, and snippet-only text |
| `discourse-json` | Rust, Kubernetes, Docker, NixOS, Home Assistant and verified Discourse sites | `scripts/discourse_search.py` | Topics, posts and replies |
| `52pojie-public` | 52pojie | `references/local/52pojie-research/scripts/fetch.py` | Public listings, RSS and threads |
| `rss-atom` | 52pojie, BBC, YouTube, Medium, Substack and academic feeds | `fast_search.py --provider rss` | Feed entries; discovery only |
| `trafilatura` | Selected web pages after Top-K selection | Optional package | Clean正文; source reading |
| `readability-lxml` | Selected web pages when primary extraction fails | Optional package | HTML article body; source reading |

The component index also records SearXNG and Semantic Scholar as candidates. They remain optional because public SearXNG instances and no-key Semantic Scholar requests can vary in availability.

## Academic staged retrieval

The academic route is shared by `academic` and `google-scholar`:

```text
discovery -> selected papers -> paper-brief -> explicit full-audit
```

`discovery` finds candidates. `paper-brief` supplements the abstract and extracts a section outline and author-stated contributions. `full-audit` reads the primary PDF or body only when the user asks for detailed methods, results, limitations, or quotations.

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
