# 去重和调用边界

## 规范化

先用 `registry/aliases.json` 把平台名称归一，再用 Skill 的稳定 `id` 去重。仓库 URL、Skill 名称和本地 canonical path 分开保存。

## 命中处理

- 同一个 Skill 被多个查询表达命中，只执行一次，并合并命中原因。
- 同一个平台多个 Skill 命中时，按能力缺口和历史评分排序后依次执行。
- 同一平台最多保留两个专项 Skill。
- 综合多平台 Skill 可跨平台复用，不计入专项上限。
- 同一底层实现的不同文档包装（例如 AutoCLI 与 Qiaomu OpenCLI）视为重复候选，浅度只保留一个。

## Agent 边界

- 一个 Agent 负责一个平台。
- 同一 Agent 内的多个 Skill 串行执行，避免互相覆盖登录态或重复抓取。
- `light` 不启动子代理，由主对话直接执行；`medium` 使用默认 2 个、最多 4 个子代理；`deep` 按任务需要扩展子代理。所有并行结果必须由主 Agent 统一完成汇总。
- Router 不调用另一个 Router；只加载最终需要的叶子 Skill。
