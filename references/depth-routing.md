# 查询深度

Depth 表达检索广度、平台 Agent 数量、证据层级和执行范围。先依据需求判断 depth，再生成 base query variants。query 数量只是执行记录，不能决定 depth。

| 深度 | 默认平台范围 | 执行方式 | Base query variants | 结果要求 |
| --- | --- | --- | ---: | --- |
| `light` | 1 个主要平台 | 1 个主要 Agent；只在明确缺口时使用 fallback | 12–16+ | 快速发现、关键来源和简短判断 |
| `medium` | 2–3 个相关平台 | 每个平台 1 个 Agent；不同平台可并行；同平台 Skill 按序执行 | 16–24+ | 跨来源比较、关键原始页面和主要限制 |
| `deep` | 3–6 个真正相关的平台 | 多平台 Agent 并行；同平台 adapter/Skill 按序执行 | 20–30+，需要时继续增加 | 源码、全文、评论链或视频证据核验，保留冲突与缺口 |

## 用户范围优先

用户明确指定平台时，平台范围优先于默认 breadth。`只查 YouTube` 的 deep route 仍然只有 YouTube；deep 体现在更多查询、更多结果、metadata/字幕读取和更深的来源核验。

## 提升条件

- 需要源码、实现、依赖、测试、Issue、提交或 Release 时，GitHub 路线至少为 `medium`；
- 需要论文论断、正文、PDF、方法、结果、限制或引文时，academic 路线至少为 `deep`；
- 需要多平台比较、最近讨论、评论链或多个独立来源时，至少为 `medium`；
- 用户明确说“深入”“完整”“全面”时，使用 `deep`，但仍遵守显式平台范围。

## 论坛与视频证据

- `light` 只读取论坛 RSS、版块列表、热门导读或视频搜索结果，适合快速发现；
- `medium` 读取选中帖子正文、视频 metadata 和可用字幕，确认版本、步骤和上下文；
- `deep` 在需要时继续读取多页回帖、完整字幕或源页面，并把论坛经验、视频内容、GitHub、官方资料和本地测量分开呈现。

## 执行关系

```text
requirement scope + evidence depth
  -> light / medium / deep
  -> platform breadth and Agent count
  -> base queries and platform-specific rewrite
  -> sequential Skills inside each platform
```

查询数量在三个深度都可以很多。不要用少量查询把深度压低，也不要为了达到某个数量擅自加入用户没有要求的平台。
