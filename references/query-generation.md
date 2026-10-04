# 需求驱动的查询词生成

查询生成分两层：由 Agent 先从完整 requirement model 产生通用 base query variants，再在平台确定后生成 platform-specific queries。Python 不从自然语言拼接查询，也不把一个标题词扩成一串固定近义词。

## 语义规划

Agent 先读取用户请求和直接相关的对话上下文，再按下面的顺序工作：

```text
Understand → Decompose → Infer → Associate → Expand → Recombine
```

明确内容直接进入需求模型；上下文能够解析的指代沿用上文对象；合理推导进入研究方向；不确定且会改变主要路线的内容才进入 `clarify`。相关实体和名称变体只在能覆盖用户目标时加入，不能无限扩展。

## Requirement model

先保留这些字段，缺失字段保持为空：

```text
target
goal
capabilities
context
constraints
evidence
time
explicit_platforms
```

字段用途：

- `target`：项目、工具、论文、错误、主题或研究对象；
- `goal`：希望得到的判断或解决方案；
- `capabilities`：必须覆盖的功能和任务；
- `context`：版本、框架、运行环境和使用场景；
- `constraints`：开源、免费、许可证、语言、无 Key 或访问范围；
- `evidence`：README、源码、Issue、论坛正文、评论、字幕、论文正文或 PDF；
- `time`：最近、指定日期或时间窗口；
- `explicit_platforms`：用户点名的平台范围。

## Base query variants

按互补方向生成查询，不做所有字段的笛卡尔积，也不套用固定模板。每个方向只保留能带来不同结果的表达：

1. 核心目标：`target + goal`；
2. 能力发现：`target + capability`；
3. 实现发现：`target + implementation / adapter / integration`；
4. 源码核验：`target + source code / repository / tests`；
5. 问题定位：`target + error / issue / workaround / version`；
6. 比较发现：`target + alternatives / comparison / benchmark`；
7. 用户经验：`target + experience / review / community feedback`；
8. 时间范围：`target + recent / latest / date range`；
9. 证据定位：`target + README / Issue / paper body / PDF`；
10. 中英文术语：同一目标分别使用中文和英文任务词；
11. 反例和限制：`target + limitations / failure modes / reproducibility`；
12. 官方来源：`target + documentation / release / primary source`。

基础任务也应生成约 12–16 个有意义的 variants；medium 约 16–24 个；deep 约 20–30 个，需求需要时继续增加。数量不会反过来决定 depth，也不应使用固定切片压缩 deep 查询。

## Platform-specific rewrite

平台确定后，不把 base queries 原样复制给所有平台。用同一 requirement 的平台语言重组查询：

### GitHub

优先使用：

```text
repository, skill, source, implementation, adapter, tests, issues, releases
```

示例：

```text
<target> repository implementation adapter tests
<target> issues release maintenance
<capability> open source skill source code
```

### Twitter / X

优先使用：

```text
项目名、开发者、自然语言评价、发布消息、实际体验、近期讨论
```

少用 README、source code、tests 这类 GitHub 术语，除非用户明确要求源码链接。

### YouTube

优先使用：

```text
tutorial, workflow, demo, review, comparison, talk, presentation, walkthrough
```

如果用户要求字幕或视频内证据，另行记录 metadata、字幕可用性和缺失情况。

### Reddit、V2EX 和 Discourse

优先使用：

```text
experience, problem, recommendation, discussion, comparison, 实际使用, 踩坑, 解决方案
```

V2EX 的公开 API 负责 hot、node、topic、replies、user 等读取；关键词 discovery 仍使用通用搜索或已验证的外部工具，不能把公开 API写成全文关键词搜索。

### Bilibili

优先使用：

```text
教程、演示、实测、评测、对比、工作流
```

本地适配器只做公开搜索发现；视频详情和字幕按 Registry 选择外部工具。

## Query packet

每个平台的 dispatch packet 至少保存：

```json
{
  "platform_id": "github",
  "queries": [
    "multi-platform research skill repository implementation",
    "agent search router source code tests"
  ],
  "evidence": ["README", "source", "issues"]
}
```

全局 `query_variants` 记录 base 层；平台对象的 `queries` 记录实际发送给该平台的重组结果。这样路线可以回放，也能识别不同平台是否误用了同一套查询。
