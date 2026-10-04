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
| GitHub | 1 | `github-local` | `scripts/github_public.py` | 仓库搜索、README、树、选定源码、依赖/配置、测试、Issues、Releases、commits；Agent 解释源码 |
| Academic | 1 | `academic-local` | `fast_search.py` + `academic_public.py` + `academic-evidence/` | OpenAlex、Crossref、arXiv、Scholar 发现和 metadata；公开 HTML 正文按需读取 |
| Google Scholar | 1 | `academic-local` | `fast_search.py --provider google-scholar` + `academic_public.py` | Scholar 只做候选发现；转向公开 HTML 或主论文来源 |
| Stack Overflow | 2 | `generic-platform-discovery` | `fast_search.py` 的 Stack Exchange API | 公开问题搜索；回答正文经选定页面读取 |
| Linux.do | 2 | `generic-platform-discovery` | `fast_search.py` 的 Discourse JSON provider | 使用已登记的公开论坛 endpoint |
| V2EX | 2 | `v2ex-public` | `scripts/v2ex_public.py` | hot、node、topic、replies、user；没有全文关键词 endpoint |
| YouTube | 2 | `generic-platform-discovery` | `scripts/platform_discovery.py` | bundled 路径发现公开候选 URL；`yt-dlp` 是 metadata/字幕可选增强 |
| Twitter/X | 2 | `generic-platform-discovery` | `scripts/platform_discovery.py` | bundled 路径发现公开候选 URL；CLI/session 是原生检索可选增强，不读取浏览器 Cookie |
| 52pojie | 2 | `52pojie-research` | `references/local/52pojie-research/scripts/fetch.py` | 公开列表、RSS、主题和可读回帖 |
| Discourse | 2 | `forum-search` | `scripts/discourse_search.py` | 需要具体论坛的公开 JSON 地址 |
| Bilibili | 3 | `bilibili-public` | `scripts/bilibili_public.py` | bundled 公共搜索；详情和字幕是可选外部能力 |
| Xueqiu | 3 | `xueqiu-public` | `scripts/xueqiu_public.py` | 股票搜索、行情、热帖、热股；当前接口可能需要公开会话 |
| Catalog public sites | 按 Registry | `generic-platform-discovery` | `scripts/platform_discovery.py` | 按 `registry/platform-domains.json` 限定站点域名，仅发现公开候选 |

## Agent-Reach 能力映射

Agent-Reach 只作为能力参考，不作为第二个 Router：

- Bilibili：仓库内置公开搜索；`bili-cli` 或 OpenCLI 的详情、字幕作为可选能力；
- V2EX：仓库内置公开 API 的 hot、node、topic、replies、user 读取；关键词发现通过 bundled generic public discovery；
- Xueqiu：吸收股票搜索、行情、热帖和热股的 HTTP 端点；不读取浏览器凭据；
- YouTube：登记外部 `yt-dlp` 的 search、metadata、subtitle 能力；不默认启动转录；
- Twitter/X、Reddit、LinkedIn、Facebook、Instagram、Boss：只登记外部 CLI/MCP 能力和访问边界，缺少运行条件时保持未验证；
- Exa：登记为通用 search component，不新增平台入口。

## 选择规则

1. Agent 先根据语义选择平台；随后由 `registry/aliases.json` 将 Agent 提供的平台名称归一到 canonical id。别名只做名称归一，不把“源码”“教程”“评价”等语义映射成平台；裸 `x` 不映射到 Twitter/X。
2. 读取对应平台 JSON，再读取所需 Skill 和 component；不要把目录中的所有平台都加载进当前任务。
3. `scripts/route_plan.py` 从平台对象补全 `tier`、bundled `scripts`、`search_components`、`adapter_type`、`access_mode`、`depth_routes` 和 `optional_enhancements`。默认 `depth_routes` 只引用 `availability: bundled` 的 Skill。
4. `medium` 和 `deep` 可以并行不同平台的 Agent；一个平台只分配一个 Agent。
5. 可选 CLI/MCP/Skill 缺失时继续跑 bundled 路线并如实报告增强项不可用；不把外部缺失导致的降级算作 bundled adapter 失败。

泛站点公开发现采用 `site:domain query` 查询，不声称调用 Reddit、LinkedIn、Facebook、Instagram 等平台的原生 API。候选 URL 仍需逐条读取；需要账号或客户端会话的内容不属于 bundled 能力。
