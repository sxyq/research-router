# 小众技术论坛接入

## 定位

Linux.do、Rust Users Forum、Kubernetes Discuss、Docker Community、NixOS Discourse 和 Home Assistant Community 等社区，部分使用 Discourse。它们可以共享一个公开 JSON 适配器，但每个站点仍然是独立来源，不能把协议支持当成所有站点都已验证。

当前统一适配器是 `forum-search`，实现脚本为 `scripts/discourse_search.py`。它只访问公开端点，不保存 Cookie、账号信息或原始结果缓存。

所有小众论坛适配器都遵循只读原则：只执行搜索、打开公开主题和读取公开回复，不执行发帖、回复、点赞、关注、登录绕过或限流规避。

完整平台清单、站点地址、优先级和适配方式见 `registry/small-forums.index.json`。清单中的每个平台都已登记；`planned` 表示目录已纳入路由，专用访问脚本仍需补齐。

## 支持的查询

```text
关键词 -> /search.json?q=...
分类 -> category 参数
标签 -> tags 参数
时间 -> after / before 参数（由脚本转成查询条件）
帖子 -> /t/<topic-id>.json
```

常用调用：

```bash
python3 scripts/discourse_search.py \
  --base-url https://users.rust-lang.org \
  --query "webview bridge" \
  --limit 10
```

读取指定主题：

```bash
python3 scripts/discourse_search.py \
  --base-url https://users.rust-lang.org \
  --topic-id 101005
```

## 站点边界

| 类型 | 处理方式 |
| --- | --- |
| 公开 Discourse 社区 | 使用 `forum-search`，核对返回的主题、帖子、作者和时间 |
| 需要登录或触发限流的论坛 | 标记 `unavailable` 或 `partial`，不绕过登录和限流 |
| Lobsters、Hacker News、X、NodeSeek、HostLoc | 不使用本适配器，分别走专用适配器或网页搜索 |
| 只有搜索摘要 | 只能作为发现证据，打开原帖后才可作为原始帖子证据 |

## 调研执行

1. 先把用户目标映射到主题、能力、版本/时间、分类和证据需求，完成平台与适配器的语义匹配。
2. 由已选适配器生成站内查询表达；关键词只是执行输入，不决定路由深度。
3. 对候选主题读取详情和回复，记录主题 URL、作者、发布时间和匹配原因。
4. 去除同一主题的重复命中，区分原帖、回复和引用内容。
5. 将限流、登录、站点不可用和结果不足分别记录，不能把失败当作没有相关内容。

真实探测表明，Rust Users、Kubernetes Discuss、Docker Community、NixOS 和 Home Assistant 的公开搜索端点可以返回 JSON；OpenWrt 在探测时返回 `429`，所以仍需按站点记录可用性。

## 当前清单的接入分层

| 接入方式 | 平台 | 当前行为 |
| --- | --- | --- |
| `discourse` | Rust Users、Kubernetes Discuss、Docker Community、NixOS、Home Assistant | 使用统一公开 JSON 查询脚本 |
| `native-public` | Lobsters、Hacker News | 保留独立公开接口适配目标，不套用 Discourse 参数 |
| `specialist-planned` | Hugging Face、Swift、Android、Flutter、OpenWrt、Arch、Gentoo、NodeSeek、HostLoc、Ruby China、GoCN、52破解 | 已进入清单，等待对应站点适配方式落地 |
| `site-required` | 独立开发者社区 | 用户需提供具体社区 URL，再选择 Discourse 或专用方式 |

## 三档查询深度

具体执行规则见 [depth-routing.md](depth-routing.md)。在小众论坛场景中，深度首先表示是否以及如何分配子代理，其次表示读取和核对范围，不表示对站点执行写操作：

- `light`：不启动子代理，由主对话处理一个站点的语义匹配、搜索，必要时读取一个主题。
- `medium`：默认启动 2 个子代理，根据任务需要增加到最多 4 个，分别执行主搜索、主题读取或独立来源复核。
- `deep`：按任务需要启动子代理，不设固定数量上限，按站点或证据角色并行处理，再统一去重和核对来源。

## 脚本与深度的关系

脚本保存访问和提取逻辑，深度规则决定是否以及如何并发执行：

- `light` 由主对话调用搜索，必要时追加一次主题读取。
- `medium` 由默认 2 个、最多 4 个子代理分别承担搜索和读取/复核。
- `deep` 为每个需要独立处理的站点或证据角色分配子代理，不设固定数量上限，统一整理重复主题、时间、作者和来源状态。

脚本始终保持只读，不能因为进入 `deep` 就增加登录、互动或绕过站点限制的动作。
