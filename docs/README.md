# 项目文档

规划与决策写在这里。代码落地后，实现以仓库为准，这里只保留「为什么这样做」。

## 选刊神器

v0.1 已落地。已拍板：国际刊 + OpenAlex 中文刊、只筛选不投稿、本机 FastAPI、本地小工具。插件后置。

| 文档 | 内容 |
| --- | --- |
| [概述与已拍板事项](./xuan-kan/overview.md) | D1–D4 |
| [产品形态](./xuan-kan/shape.md) | 本机服务 + 网页客户端 |
| [数据策略](./xuan-kan/data.md) | 本机 SQLite、导入器、关键词匹配 |
| [技术栈](./xuan-kan/tech-stack.md) | 选定的 B（本地版） |
| [开发计划](./xuan-kan/roadmap.md) | M0–M5；插件二期后置 |
| [使用说明](./xuan-kan/usage.md) | v0.1 安装、启动、排错 |

## 公司查询

v0.1 已落地。套选刊的本机形态、三层数据和 UI；不爬商业征信；插件不做。

| 文档 | 内容 |
| --- | --- |
| [概述与已拍板事项](./gongsi/overview.md) | C1–C5 |
| [产品形态](./gongsi/shape.md) | 同进程、顶栏切换、同一套样式 |
| [数据策略](./gongsi/data.md) | Wikidata 同步 + 名单导入 |
| [技术栈](./gongsi/tech-stack.md) | 复用 FastAPI + SQLite + Vite |
| [开发计划](./gongsi/roadmap.md) | G0–G8 |
| [使用说明](./gongsi/usage.md) | 同步、导入、检索、排错 |
