# 需求驱动的查询词生成

查询词来自用户需求的不同语义切面，不从单个标题随机扩写。

## 生成顺序

1. 写出一句目标句：用户想解决什么问题，最终要得到什么判断。
2. 提取能力词：例如“跨平台 Skill、按需加载、源码分析、评论证据、PDF 正文”。
3. 提取限制词：平台、语言、时间、登录要求、Skill-only、许可证、社区认可度。
4. 加入同义表达和中英文平台术语。
5. 加入证据词：`README`、`source code`、`adapter`、`tests`、`issues`、`releases`、`full text`、`PDF`。
6. 删除只描述项目名称、不能表达用户目标的查询词。

## 三类查询模板

### 开源项目或 Skill

- `<问题目标> + agent skill`
- `<能力组合> + multi-platform + skill`
- `<平台集合> + search adapter + agent`
- `<目标工具> + README + source code + tests`
- `<目标工具> + alternatives + maintenance + community`

### 修 Bug

- `<完整错误文本> + <库/版本>`
- `<错误现象> + <API/框架> + fix`
- `<仓库> + issue + <错误文本>`
- `<仓库> + commit + regression test`

### 论文

- `<研究问题> + survey + benchmark`
- `<方法/任务> + recent papers + venue`
- `<论断> + primary paper + full text`
- `<方法> + ablation + reproducibility`

## GitHub 查询要求

GitHub 项目发现可用 3–5 组互补查询；候选确认后再读取 README、树、依赖、入口源码、测试、Issue 和 Release。标题命中不等于需求命中。
