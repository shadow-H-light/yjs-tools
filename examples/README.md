# 样例导入表

`metrics-sample-2025.csv` 只用来验收导入器。里面的分区和影响因子是**示意数字**，不是 JCR / 中科院官方值。

```bash
uv run xuankan import examples/metrics-sample-2025.csv --year 2025 --source sample
uv run xuankan search Nature --jcr 1
uv run xuankan import-delete 1
```

列说明见 [docs/xuan-kan/data.md](../docs/xuan-kan/data.md)。
