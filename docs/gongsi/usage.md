# 公司查询 · 使用说明

本机查企业与校招，不投递。和选刊神器共用 `http://127.0.0.1:8765`，顶栏切换「公司查询」。

编制、薪资、校招人数、纠纷只来自你导入的表或 Wikidata 公开字段。央企**不会**自动写成有编制。

## 启动

与选刊相同：

```bash
uv run xuankan serve
```

打开页面后点 **公司查询**。

## 日常流程

1. 同步公开档案：网页「同步 Wikidata」，或

   ```bash
   uv run xuankan gongsi ingest --limit 400
   uv run xuankan gongsi ingest --query 华为 --limit 8
   ```

2. 导入自己的表（央企名录、编制、薪资摘录、校招简章）：

   ```bash
   uv run xuankan gongsi import examples/companies-sample.csv --kind companies --year 2026
   uv run xuankan gongsi import examples/jobs-sample.csv --kind jobs --year 2026
   ```

   `kind`：`companies`（公司/编制/央企/薪资）、`jobs`（岗位与秋招春招）、`disputes`（纠纷）、`universities`（密切高校）。

3. 检索：智能 / 名称 / 行业 / 专业 / 岗位 / 代码。例如专业搜「光学工程」。

   ```bash
   uv run xuankan gongsi search 光学工程 --by major
   uv run xuankan gongsi search 华为 --by name
   ```

4. 勾选 2–4 家对比，或 `uv run xuankan gongsi compare 1,2`
5. 导出 CSV，或删除导入批次：`uv run xuankan gongsi import-delete 1`

样例表里的薪资和招录人数**仅作演示**，不是官方 offer。

## 导入表头

公司表常用列：`公司名称` / `qid` / `类型` / `央企` / `编制` / `薪资` / `行业` / `员工数` / `官网` / `地点`。

岗位表常用列：`公司名称` / `岗位` / `专业` / `地点` / `季节` / `开始` / `结束` / `人数` / `年份`。

岗位行必须先能匹配到已有公司（名称、QID 或股票代码）。纠纷与高校表同样。

## 排错

- **连不上 Wikidata**：检查网络后重试，或把 `--limit` 调小。校园网 HTTPS 检查可能导致证书报错，本机 Windows 默认会绕过该校验。
- **岗位导入未匹配**：先导入或同步公司，再导岗位；公司名要能对上。
- **编制显示暂无**：正常。只有导入表写了编制才会显示。
- **数据库正被占用**：关掉另一个 `xuankan serve`。
- **8765 没有页面**：先构建 `web`（见选刊使用说明）。

`uv run xuankan gongsi --help` 可看全部子命令。
