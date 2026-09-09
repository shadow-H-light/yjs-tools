# yjs-tools

研究生阶段常用工具集。当前可用模块是**选刊神器 v0.1**：本机筛选国际刊，不负责投稿。

## 选刊神器 v0.1

本机同步 OpenAlex 国际刊，按刊名 / ISSN / 研究方向检索，用本地 CSV 导入分区与影响因子，对比 2–4 本刊并导出。数字只来自你导入的表。

规划在 [docs](./docs/README.md)，安装与排错见 [使用说明](./docs/xuan-kan/usage.md)。

### 同学安装

需要 Python 3.11+。本机服务默认只监听 `127.0.0.1:8765`。

```bash
git clone git@github.com:shadow-H-light/yjs-tools.git
cd yjs-tools
python -m pip install uv
uv sync
cd web && npm install && npm run build && cd ..
uv run xuankan serve
```

打开 [http://127.0.0.1:8765](http://127.0.0.1:8765)。之后启动只要最后一条。

```bash
uv run xuankan ingest --limit 200
uv run xuankan import examples/metrics-sample-2025.csv --year 2025 --source sample
uv run xuankan search 计算机视觉 --jcr 1
uv run xuankan compare 1,2
uv run xuankan export --query Nature --out xuankan-export.csv
```

样例 CSV 里的分区和 IF **仅作演示**，不是官方 JCR / 中科院数据。

### 排错

- **连不上 OpenAlex**：检查网络后重试，或把 `--limit` 调小。
- **CSV 缺 ISSN 列**：表头需要 `issn` 或「刊号」。
- **CSV 编码无法识别**：另存为 UTF-8 后再导入。
- **数据库正被占用**：关掉另一个 `xuankan serve`。
- **8765 没有页面**：先构建 `web`（见上），或另开 `cd web && npm run dev`。

`uv run xuankan --version` 应显示 `0.1.0`。

## 后续模块

| 模块 | 用途 |
| --- | --- |
| 导师查询 | 检索导师研究方向、成果与招生相关信息 |
| 学校查询 | 了解院校、学院与培养相关情况 |
| 就业分析 | 梳理毕业去向、行业分布与岗位趋势 |
| 公司查询 | 查看企业背景，服务实习与就业选择 |

## 许可

未指定许可证。默认保留所有权利。
