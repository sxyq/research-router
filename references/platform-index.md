# Research Router Platform Index

`registry/platforms.index.json` 是平台路由的机器可读事实源。`registry/platforms/<platform>.json` 保存每个平台的能力、Tier、入口 Skill、脚本、访问条件和三档 depth route；本文件只解释选择规则和容易混淆的边界。

## Tier

Tier 表示默认研究优先级，不代表允许/禁止，也不等同于运行可用性。用户明确指定平台时，直接使用该平台，并在结果中报告实际访问条件。

| Tier | 默认用途 | 平台 |
| --- | --- | --- |
| 1 | 核心来源、论文和主要实现证据 | GitHub、Academic、Google Scholar |
| 2 | 技术社区、公开讨论、视频和开发者讨论 | 52pojie、Stack Overflow、Linux.do、V2EX、Discourse、YouTube、Twitter/X，以及注册表中的同级平台 |
| 3 | 补充性媒体、社交、财经和外部社区 | Bilibili、Douyin、TikTok、Xiaohongshu、Reddit、Xueqiu、LinkedIn、Facebook、Instagram、Boss 等 |

Exa 是通用 search component，不属于平台 Tier。

## 当前重要路由

| 平台 | Tier | 首选入口 | 本地脚本或外部能力 | 边界 |
| --- | ---: | --- | --- | --- |
| GitHub | 1 | `github-search` -> `github-analyze` | `scripts/fast_search.py --provider github` | 搜索结果只做发现；源码结论继续读取目录、源码、依赖、测试、Issue 和 Release |
| Academic | 1 | `paper-research-router`、`literature-evidence-audit` | `fast_search.py` 的 OpenAlex、arXiv、Crossref | metadata/摘要不能替代论文正文或 PDF |
| Google Scholar | 1 | `paper-research-router` -> `literature-evidence-audit` | `fast_search.py --provider google-scholar` | 公共 HTML 仅用于发现，摘要可能是片段 |
| V2EX | 2 | `v2ex-public`，按需加 `autocli` | `scripts/v2ex_public.py` | hot、node、topic、replies、user；没有伪造的全文关键词 API |
| YouTube | 2 | `autocli` | 外部 `yt-dlp` | search、metadata、可用字幕；转录是额外步骤 |
| Twitter/X | 2 | `autocli` | 外部 `twitter-cli` 或 OpenCLI | 需要显式凭据或已允许的外部会话；不自动读取浏览器 Cookie |
| 52pojie | 2 | `52pojie-research` | `references/local/52pojie-research/scripts/fetch.py` | 公开列表、RSS、主题和可读回帖 |
| Discourse | 2 | `forum-search` | `scripts/discourse_search.py` | 需要具体论坛的公开 JSON 地址 |
| Bilibili | 3 | `bilibili-public`，按需加 `autocli` | `scripts/bilibili_public.py` | 本地脚本只做公开搜索；详情和字幕由外部能力提供 |
| Xueqiu | 3 | `xueqiu-public` | `scripts/xueqiu_public.py` | 股票搜索、行情、热帖、热股；当前接口可能需要公开会话 |

## Agent-Reach 能力映射

Agent-Reach 只作为能力参考，不作为第二个 Router：

- Bilibili：吸收公开搜索 API 的入口；`bili-cli` 或 OpenCLI 的详情、字幕继续作为外部能力；
- V2EX：吸收公开 API 的 hot、node、topic、replies、user 读取；关键词 discovery 继续使用通用搜索；
- Xueqiu：吸收股票搜索、行情、热帖和热股的 HTTP 端点；不读取浏览器凭据；
- YouTube：登记外部 `yt-dlp` 的 search、metadata、subtitle 能力；不默认启动转录；
- Twitter/X、Reddit、LinkedIn、Facebook、Instagram、Boss：只登记外部 CLI/MCP 能力和访问边界，缺少运行条件时保持未验证；
- Exa：登记为通用 search component，不新增平台入口。

## 选择规则

1. 先将用户平台名称映射到 `registry/aliases.json`；裸 `x` 不映射到 Twitter/X。
2. 读取对应平台 JSON，再读取所需 Skill 和 component；不要把目录中的所有平台都加载进当前任务。
3. 平台对象中的 `depth_routes` 决定入口 Skill 顺序；同一平台内顺序执行。
4. `medium` 和 `deep` 可以并行不同平台的 Agent；一个平台只分配一个 Agent。
5. 外部 CLI/MCP 缺失、未登录或未获授权时，保留路由计划并报告 `runtime unavailable`，不把静态登记当成执行成功。
