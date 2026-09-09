# 选刊神器 · 使用说明

v0.1 本机国际刊筛选。只匹配、不投稿。分区和影响因子来自你导入的表，不是本工具测算。

默认地址：`http://127.0.0.1:8765`。

## 同学安装（第一次）

需要 Python 3.11+。没有 `uv` 时先装一次：

```bash
git clone git@github.com:shadow-H-light/yjs-tools.git
cd yjs-tools
python -m pip install uv
uv sync
cd web
npm install
npm run build
cd ..
uv run xuankan serve
```

浏览器打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。

之后每次只要一条命令：

```bash
uv run xuankan serve
```

开发网页时另开终端：`cd web && npm run dev`，页面在 `http://127.0.0.1:5173`，接口仍走 8765。

## 日常流程

1. `uv run xuankan ingest --limit 200` — 从 OpenAlex 同步有 ISSN 的国际刊。
2. `uv run xuankan import 你的表.csv --year 2025` — 导入分区 / IF / 可选审稿时长。
3. 网页检索，或 CLI：`uv run xuankan search 计算机视觉 --jcr 1`
4. 勾选 2–4 本刊对比，或 `uv run xuankan compare 1,2`
5. 导出：网页「导出 CSV」，或 `uv run xuankan export --query Nature --out xuankan-export.csv`

样例表（数字仅作演示，不是官方 JCR/中科院）：

```bash
uv run xuankan import examples/metrics-sample-2025.csv --year 2025 --source sample
```

CSV 建议 UTF-8。列名可用：`issn`、`year`、`jcr_quartile`、`impact_factor`、`cas_quartile`、`warning`、`review_days`（或中文别名，见样例表头）。

查看版本：`uv run xuankan --version`。

## 排错

| 现象 | 怎么办 |
| --- | --- |
| 同步失败 / 连不上 OpenAlex | 检查能否访问 `api.openalex.org`，稍后重试，或把 `--limit` 调小 |
| CSV 提示缺少 ISSN | 表头要有 `issn` 或「刊号」 |
| CSV 乱码或编码无法识别 | Excel「另存为」UTF-8 CSV 后再导入 |
| 数据库正被占用 | 关掉另一个 `xuankan serve`，或结束占用 `data/xuankan.sqlite` 的进程 |
| 打开 8765 没有页面 | 先 `cd web && npm install && npm run build`，或用 `npm run dev` |
| 筛选里没有 JCR / 中科院 | 还没导入官方指标 CSV；未导入时故意不显示假数字 |
| 审稿显示「暂无」 | CSV 里该刊没有 `review_days`，属正常 |

本工具不爬 Clarivate、LetPub、知网。官方分区请用你有权使用的表导入。
