# Research Router

一个独立的 Codex Skill，用于把联网查询按“场景 → 交互模式 → 查询深度 → 平台 → 子 Skill”组织起来。

它面向三类查询：

- **bug-fix**：查找报错解决方案、Issue、修复提交、源码和回归测试。
- **open-source**：发现和比较开源项目、Skill、插件及其实际实现。
- **academic**：发现论文、作者和会议，并在需要时核验论文正文或 PDF 证据。

## 设计原则

1. 先识别查询场景，再选择查询深度。
2. 查询深度由需求派生词数量、证据要求和并行程度决定；平台数量由用户需求决定。
3. `light` 优先使用一个综合多平台 Skill；`medium` 按平台分配 Agent；`deep` 并行多个平台 Agent。
4. 一个 Agent 负责一个平台。同一平台命中多个 Skill 时，由该 Agent 按顺序执行。
5. Router 只按需加载叶子 Skill，不扫描全部本地 Skill，不要求 MCP 作为直接依赖。
6. GitHub 的源码结论需要继续读取目录、源码、依赖、测试、Issue 和 Release；论文证据需要核对正文或 PDF。
7. 每次路由记录实际执行到的最终子 Skill；用户评分与 Router 评分、子 Skill 评分分别保存。

## 快速安装

将本仓库安装为 Codex Skill：

```bash
npx skills add sxyq/research-router --skill research-router
```

本地手动使用：

```bash
git clone https://github.com/sxyq/research-router.git "${CODEX_HOME:-$HOME/.codex}/skills/research-router"
```

安装后，在 Codex 中可以直接使用：

```text
使用 $research-router 先判断这个查询属于修 Bug、开源项目发现还是论文查询，再按合适深度执行，并记录最终调用的子 Skill。
```

## 目录结构

```text
research-router/
├── SKILL.md                         # Codex 入口规则
├── agents/openai.yaml               # Codex 显示信息与默认提示
├── registry/                        # 内置平台和 Skill 注册表
│   ├── aliases.json                 # 平台别名归一化
│   ├── platforms.index.json         # 平台、场景和通用 Skill 索引
│   ├── skills.index.json            # Skill 总索引
│   ├── platforms/*.json             # 平台能力和三档路由
│   └── skills/*.json                # Skill 来源、能力和边界
├── references/                      # 按需读取的详细路由规则
├── schemas/                         # 路由、反馈、平台和 Skill 的 JSON Schema
├── records/                         # 本地运行记录，不提交到公开仓库
│   ├── routes/                      # 每次路由一个 JSON
│   ├── feedback/                    # 用户评分和意见
│   └── summaries/                   # 评分汇总
├── tuning/                          # 本地调优建议和已采用策略
├── scripts/                         # 确定性校验和统计脚本
└── tests/                           # 固定路由案例，不访问真实平台
```

## 默认路由

| 平台或场景 | `light` | `medium` | `deep` |
| --- | --- | --- | --- |
| B站 | `autocli` | `autocli` | `autocli` + `last30days-cn` |
| 中国抖音 | 默认跳过，点名后启用 | `douyin-skills` | `douyin-skills` + `last30days-cn` |
| TikTok | `autocli` | `autocli` | `autocli` |
| 小红书 | `autocli` | `autocli` + `xiaohongshu-skills` | 三者按序执行 |
| Linux.do | `autocli` | `autocli` | `autocli` |
| V2EX | `autocli` | `autocli` | `autocli` + `last30days-cn` |
| GitHub | `github-search` | `github-search` → `github-analyze` | 上述两项 + `last30days-cn` |
| 论文与学术 | `autocli` | `anysearch` + `paper-research-router` | 再加 `literature-evidence-audit` |

`qiaomu-smart-search` 与 AutoCLI/OpenCLI 属于重叠入口，当前不放入默认活动路由。需要切换候选时，先更新注册表并保留评分依据。

## 两种交互模式

- `direct`：用户要求直接开始，按现有条件执行，缺失信息在结果中标记。
- `clarify`：一次只问一个会改变路由的问题，直到目标、范围、平台、证据和输出条件明确。

## 记录和调优

路由完成后，把记录写入：

```text
records/routes/YYYY-MM-DD/<timestamp>-<route-id>.json
```

记录至少包含：

- 查询摘要和必要上下文
- 场景、交互模式和深度
- 需求驱动的查询词
- 命中的平台与 Skill
- 每个平台的 Agent 和 Skill 执行顺序
- 最终叶子 Skill 路径
- 证据状态、失败归因和来源链接

用户评分写入：

```text
records/feedback/YYYY-MM-DD/<timestamp>-<route-id>-feedback.json
```

Router 与子 Skill 分开评分。只有相似任务重复出现同一问题时，才生成 `tuning/proposals/` 中的调优建议；单次评分只作为样本。

## 校验

```bash
python3 scripts/validate-registry.py
python3 scripts/validate-route-record.py path/to/route.json
python3 scripts/summarize-feedback.py
python3 "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" .
```

固定路由案例位于 `tests/routing-cases/basic-cases.json`。这些案例只检查预期路由，不调用网络平台。

## 隐私边界

公开仓库不包含：

- 浏览器 Cookie、Token 或账号数据
- 原始查询结果和大段上下文
- 本地运行记录与评分记录
- Trellis 文件或项目源码
- MCP 配置

运行记录和调优文件通过 `.gitignore` 保留在本机 Skill 目录，供后续调整路由时使用。

## 状态

这是一个可运行的第一版 Skill 结构。第三方 Skill 的仓库存在和文档能力已经写入注册表；具体登录态、依赖和平台运行成功仍需在调用时单独验证。
