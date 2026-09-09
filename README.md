# yjs-tools

研究生阶段常用工具集：把选导师、选学校、选期刊、看就业、查公司这些散落的信息，收拢到一个地方。

## 做什么

面向读研与科研决策，而不是通用办公套件。当前规划覆盖：

| 模块 | 用途 |
| --- | --- |
| 导师查询 | 检索导师研究方向、成果与招生相关信息 |
| 学校查询 | 了解院校、学院与培养相关情况 |
| 就业分析 | 梳理毕业去向、行业分布与岗位趋势 |
| 期刊选择 | 国际刊筛选与方向匹配（选刊神器，不负责投稿） |
| 公司查询 | 查看企业背景，服务实习与就业选择 |

后续会按模块逐步落地，优先把查询与对比做清楚。

## 谁适合用

- 准备考研或正在申请的同学
- 在读研究生（选题、投稿、实习与就业）
- 需要快速对照导师、院校与去向信息的人

## 开发状态

首个模块**选刊神器**已能在本机同步 OpenAlex 国际刊、按刊名/ISSN 检索，并用本地 CSV 导入分区与影响因子。

规划在 [docs](./docs/README.md)。

## 本地开始

需要 Python 3.11+。本机服务默认只监听 `127.0.0.1:8765`。

```bash
git clone git@github.com:shadow-H-light/yjs-tools.git
cd yjs-tools
python -m pip install uv
uv sync --extra dev
uv run xuankan ingest --limit 200
uv run xuankan import examples/metrics-sample-2025.csv --year 2025 --source sample
uv run xuankan search Nature --jcr 1
uv run xuankan serve
```

网页控制台开发（另开一个终端）：

```bash
cd web
npm install
npm run dev
```

生产可先 `npm run build`，再只开 `xuankan serve`，由 FastAPI 托管构建结果。

## 许可

未指定许可证。默认保留所有权利。
