# 选刊神器 · 技术栈

D3 已锁定：**方案 B，但按本地小工具收瘦**（见 [shape.md](./shape.md)）。下面保留当初 A/B 对比，避免以后重辩。

## 已选定（B · 本地版）

| 层 | 选择 | 为什么 |
| --- | --- | --- |
| 核心 | Python + FastAPI | 摄入、导入器、检索都在本机一个进程里 |
| 启动 | `uv` + 一条 CLI（如 `xuankan serve`） | 少装 Docker，少配环境 |
| 数据 | SQLite 文件（用户目录或仓库 `data/`） | 备份就是复制文件；零运维 |
| 向量 | 可选 `sqlite-vec`；没有模型就降级 | 不强迫下载大模型才能用 |
| 网页 | Vite + React 薄控制台，生产构建后由 FastAPI 托管 | 只要一个端口；不是独立站点 |
| 契约 | FastAPI OpenAPI | 网页和以后的插件共用 |
| 插件 | 二期，Zotero 或浏览器扩展 | 只调 `127.0.0.1`，不内置库 |

监听默认 `127.0.0.1:8765`。不要做成公网服务，除非以后单独立项。

### 目录（按这个搭 M0）

```text
src/yjs_tools/           Python 包：CLI、API、选刊逻辑
  cli.py                 xuankan serve / ingest / import
  api/                   FastAPI 路由
  journal/               检索、打分、导入解析
  db/                    SQLite schema、迁移
web/                     Vite + React，只调本机 API
plugins/                 二期：zotero / browser
data/                    本地库与导入文件（gitignore）
docs/                    规划文档
```

不搞 Turborepo、不拆 `apps/api` 独立部署、不上 Next.js。

---

## 当初两套方案的对比（存档）

都能做出同一套选刊能力。分叉在语言数量和以后好不好加分析。

### 相同点

- 都要有检索 UI、期刊库、CSV 导入器、刊名 + 主题匹配
- 数据红线相同（见 [data.md](./data.md)）
- 选刊只是 yjs-tools 第一个模块

### 差异

| 维度 | 方案 A · Next.js 全栈 | 方案 B · FastAPI + 前端 |
| --- | --- | --- |
| 语言 | 基本只有 TypeScript | Python + TypeScript |
| 进程 | 页面和 API 同进程 | API 独立，前端只是客户端 |
| 摄入 / 分析 | Node 够用，分析要后补 Python | 清洗、embedding、就业分析更顺 |
| 插件 | 要从 Route Handler 再抽 API | API 天生能给插件用 |
| 当时默认库 | PostgreSQL | 原文也是 PostgreSQL |

本地小工具这个前提出现后，A 的「网站交付」优势变弱，B 的「API 给插件用」对上了；库从 PostgreSQL 改成 SQLite，两种方案本来都该改。

### 方案 A 仍成立的地方

查询 UI 迭代快、类型前后端不断档。若以后只做网页、不做插件，A 仍更省。

### 方案 B 仍成立的地方

摄入、本地模型、就业分析、以及「一个本机服务、多个壳」——网页和插件都是壳。

---

## 变更记录

| 日期 | 变更 |
| --- | --- |
| 2026-09-09 | 初稿。对比 A/B，D3 未锁定。 |
| 2026-09-09 | 锁定 B。按本地小工具改为 FastAPI + SQLite + 薄 Vite；插件二期。 |
