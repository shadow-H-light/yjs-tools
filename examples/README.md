# 样例导入表

`metrics-sample-2025.csv` 只用来验收选刊导入器。里面的分区和影响因子是**示意数字**，不是 JCR / 中科院官方值。

```bash
uv run xuankan import examples/metrics-sample-2025.csv --year 2025 --source sample
uv run xuankan search Nature --jcr 1
uv run xuankan import-delete 1
```

`companies-sample.csv` 与 `jobs-sample.csv` 只用来验收公司查询。薪资和招录人数是示意数字。

```bash
uv run xuankan gongsi import examples/companies-sample.csv --kind companies --year 2026
uv run xuankan gongsi import examples/jobs-sample.csv --kind jobs --year 2026
uv run xuankan gongsi search 光学工程 --by major
```

列说明见 [docs/xuan-kan/data.md](../docs/xuan-kan/data.md) 与 [docs/gongsi/data.md](../docs/gongsi/data.md)。
