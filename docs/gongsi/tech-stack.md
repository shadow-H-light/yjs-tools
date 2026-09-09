# 公司查询 · 技术栈

C3 锁定：不新选栈，复用选刊已落地的 B。

## 沿用

| 层 | 选择 | 公司模块怎么用 |
| --- | --- | --- |
| 核心 | Python + FastAPI | `src/yjs_tools/company/` 检索、同步、导入 |
| 启动 | 现有 `xuankan serve` | 同一 Uvicorn 进程挂新路由 |
| 数据 | 同一 SQLite | 新表 + 迁移，不新建默认库文件 |
| 网页 | 现有 Vite + React | `web/src` 增加公司页，共用 `styles.css` |
| 契约 | `/api/companies*` | 与 `/api/journals*` 并列 |
| 插件 | 不做 | 与选刊一致，明确后置 |

监听仍是 `127.0.0.1:8765`。

## 目录增量

```text
src/yjs_tools/
  company/           同步、检索、导入、岗位/校招、财务、高校
  api/app.py         /api/companies 及 jobs、rounds
  cli.py             gongsi 子命令组
  db/schema.sql      companies、jobs、rounds、finance、disputes、universities
web/src/
  App.tsx            顶栏模块切换；公司页共用 styles.css
docs/gongsi/
examples/            companies-sample.csv、jobs-sample.csv
```

Wikidata 请求带与选刊同风格的 User-Agent；失败重试策略照抄 OpenAlex ingest。

## 对外接口（v0.1 草案）

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/companies` | `q` `by=auto\|name\|industry\|code\|major\|job` `ownership` `city` `season` |
| GET | `/api/companies/{id}` | 详情（岗位、届别、财务、高校） |
| POST | `/api/companies/ingest` | Wikidata 同步（含所有制粗分） |
| POST | `/api/companies/imports` | 公司/岗位/纠纷/高校表，`kind=` |
| GET | `/api/companies/compare` | `ids=1,2,3` |
| GET | `/api/companies/export` | CSV |

## 变更记录

| 日期 | 变更 |
| --- | --- |
| 2026-09-09 | 初稿。复用 FastAPI + SQLite + 薄控制台。 |
| 2026-09-09 | 检索参数增加专业/岗位；导入 kind 区分校招与纠纷表。 |
