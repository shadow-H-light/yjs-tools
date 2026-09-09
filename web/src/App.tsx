import { FormEvent, useEffect, useMemo, useState } from "react";

type Topic = {
  topic_name: string;
  field_name: string | null;
};

type Official = {
  year: number;
  jcr_quartile: number | null;
  impact_factor: number | null;
  impact_factor_5: number | null;
  cas_quartile: number | null;
  warning: boolean;
  filename: string | null;
  source: string | null;
  review_days: number | null;
};

type Journal = {
  id: number;
  display_name: string;
  issn_l: string | null;
  publisher: string | null;
  homepage: string | null;
  is_oa: boolean;
  is_chinese?: boolean;
  alternate_titles?: string[];
  works_count: number;
  cited_by_count: number;
  citedness_2yr: number | null;
  topics: Topic[];
  matched_topics: Topic[];
  official: Official | null;
  match_score?: number;
};

type Stats = {
  journals: number;
  topics: number;
  chinese_journals?: number;
  last_ingest_at: string | null;
  import_batches: number;
  metric_years: number[];
  has_official_metrics: boolean;
};

type Batch = {
  id: number;
  filename: string;
  year: number;
  source: string;
  matched: number;
  unmatched: number;
};

type SearchBy = "auto" | "name" | "topic" | "issn";
type Region = "all" | "cn" | "intl";
type IngestScope = "all" | "intl" | "cn";
type SortKey =
  | "relevance"
  | "cited"
  | "citedness"
  | "impact_factor"
  | "review_days"
  | "name";
type SortDir = "asc" | "desc";

const PAGE_SIZE = 10;
const FETCH_LIMIT = 100;
const DEFAULT_DIR: Record<SortKey, SortDir> = {
  relevance: "desc",
  cited: "desc",
  citedness: "desc",
  impact_factor: "desc",
  review_days: "asc",
  name: "asc",
};

function compareNullable(
  a: number | null | undefined,
  b: number | null | undefined,
  dir: SortDir,
): number {
  const aMissing = a == null;
  const bMissing = b == null;
  if (aMissing && bMissing) return 0;
  if (aMissing) return 1;
  if (bMissing) return -1;
  return dir === "asc" ? a - b : b - a;
}

function sortJournals(list: Journal[], sort: SortKey, dir: SortDir): Journal[] {
  const copy = [...list];
  copy.sort((left, right) => {
    if (sort === "name") {
      const cmp = (left.display_name || "").localeCompare(
        right.display_name || "",
        "zh-CN",
      );
      return dir === "asc" ? cmp : -cmp;
    }
    if (sort === "relevance") {
      return compareNullable(left.match_score ?? 0, right.match_score ?? 0, dir);
    }
    if (sort === "cited") {
      return compareNullable(left.cited_by_count, right.cited_by_count, dir);
    }
    if (sort === "citedness") {
      return compareNullable(left.citedness_2yr, right.citedness_2yr, dir);
    }
    if (sort === "impact_factor") {
      return compareNullable(
        left.official?.impact_factor,
        right.official?.impact_factor,
        dir,
      );
    }
    return compareNullable(
      left.official?.review_days,
      right.official?.review_days,
      dir,
    );
  });
  return copy;
}

const PLACEHOLDERS: Record<SearchBy, string> = {
  auto: "刊名、主题或 ISSN，例如 传感器 / sensor / Nature",
  name: "刊名或别名，例如 Nature、光学学报",
  topic: "研究方向，例如 传感器、computer vision",
  issn: "ISSN，例如 0028-0836",
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) message = String(body.detail);
    } catch {
      /* keep status text */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export default function App() {
  const [query, setQuery] = useState("");
  const [by, setBy] = useState<SearchBy>("auto");
  const [region, setRegion] = useState<Region>("all");
  const [jcr, setJcr] = useState("");
  const [cas, setCas] = useState("");
  const [allResults, setAllResults] = useState<Journal[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [matchMode, setMatchMode] = useState<string>("browse");
  const [expanded, setExpanded] = useState<string[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [importYear, setImportYear] = useState("2025");
  const [selected, setSelected] = useState<number[]>([]);
  const [compared, setCompared] = useState<Journal[] | null>(null);
  const [ingestScope, setIngestScope] = useState<IngestScope>("all");
  const [sort, setSort] = useState<SortKey>("relevance");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [page, setPage] = useState(0);
  const [activity, setActivity] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  async function refreshMeta() {
    const [nextStats, nextBatches] = await Promise.all([
      api<Stats>("/api/stats"),
      api<{ results: Batch[] }>("/api/imports"),
    ]);
    setStats(nextStats);
    setBatches(nextBatches.results);
  }

  function searchUrl(q: string) {
    const params = new URLSearchParams({
      q,
      limit: String(FETCH_LIMIT),
      offset: "0",
      by,
      region,
      sort: "relevance",
    });
    if (jcr) params.set("jcr", jcr);
    if (cas) params.set("cas", cas);
    return `/api/journals?${params}`;
  }

  async function runSearch(q: string) {
    setError(null);
    const data = await api<{
      results: Journal[];
      hint: string | null;
      match_mode: string;
      expanded_terms?: string[];
      total?: number;
      filled?: number;
    }>(searchUrl(q));
    setAllResults(data.results);
    setHint(data.hint);
    setMatchMode(data.match_mode);
    setExpanded(data.expanded_terms ?? []);
    setPage(0);
  }

  useEffect(() => {
    refreshMeta()
      .then(() => runSearch(""))
      .catch((err: Error) => setError(err.message));
  }, []);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setActivity("正在检索。若本机没有该主题，会向 OpenAlex 补刊，可能需要十几秒。");
    try {
      await runSearch(query);
    } catch (err) {
      setError(err instanceof Error ? err.message : "检索失败");
    } finally {
      setBusy(false);
      setActivity(null);
    }
  }

  async function onIngest() {
    setBusy(true);
    setError(null);
    setStatus(null);
    setActivity("正在从 OpenAlex 同步期刊，可能需要十几秒，请勿关闭页面。");
    try {
      const result = await api<{
        inserted: number;
        updated: number;
        total: number;
        stats: Stats;
      }>(`/api/ingest?limit=160&scope=${ingestScope}`, { method: "POST" });
      setStatus(
        `同步完成：新增 ${result.inserted}，更新 ${result.updated}，合计 ${result.total}。库中现有 ${result.stats.journals} 种。`,
      );
      await refreshMeta();
      await runSearch(query);
    } catch (err) {
      setError(err instanceof Error ? err.message : "同步失败");
    } finally {
      setBusy(false);
      setActivity(null);
    }
  }

  async function onImport(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("请先选择 CSV 文件");
      return;
    }
    setBusy(true);
    setError(null);
    setActivity("正在导入分区表…");
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("year", importYear);
      body.append("source", "csv");
      const result = await api<{ matched: number; unmatched: number }>(
        "/api/imports",
        { method: "POST", body },
      );
      setFile(null);
      setStatus(
        `导入完成：匹配 ${result.matched} 种，未匹配 ${result.unmatched} 条 ISSN。`,
      );
      await refreshMeta();
      await runSearch(query);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setBusy(false);
      setActivity(null);
    }
  }

  async function onDeleteBatch(id: number) {
    setBusy(true);
    setError(null);
    try {
      await api(`/api/imports/${id}`, { method: "DELETE" });
      await refreshMeta();
      await runSearch(query);
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    } finally {
      setBusy(false);
    }
  }

  function toggleSelect(id: number) {
    setSelected((current) => {
      if (current.includes(id)) {
        return current.filter((item) => item !== id);
      }
      if (current.length >= 4) {
        return current;
      }
      return [...current, id];
    });
  }

  async function onCompare() {
    if (selected.length < 2) {
      setError("请勾选 2–4 本期刊再对比");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const data = await api<{ results: Journal[] }>(
        `/api/compare?ids=${selected.join(",")}`,
      );
      setCompared(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "对比失败");
    } finally {
      setBusy(false);
    }
  }

  function downloadCsv(path: string) {
    const link = document.createElement("a");
    link.href = path;
    link.download = "xuankan.csv";
    link.click();
  }

  const sortedResults = useMemo(
    () => sortJournals(allResults, sort, sortDir),
    [allResults, sort, sortDir],
  );
  const total = sortedResults.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE) || 1);
  const currentPage = Math.min(page, pageCount - 1);
  const results = sortedResults.slice(
    currentPage * PAGE_SIZE,
    (currentPage + 1) * PAGE_SIZE,
  );
  const modeLabel = useMemo(() => {
    if (matchMode === "topic") return "主题匹配";
    if (matchMode === "name") return "刊名匹配";
    if (matchMode === "issn") return "ISSN";
    if (matchMode === "mixed") return "刊名 + 主题";
    return "浏览";
  }, [matchMode]);

  return (
    <main>
      <header>
        <p className="eyebrow">本机选刊 · 不投稿</p>
        <h1>
          选刊神器 <span className="version">v0.1</span>
        </h1>
      </header>

      <section className="search-card">
        <form className="search-bar" onSubmit={onSearch}>
          <select
            className="search-by"
            value={by}
            onChange={(e) => setBy(e.target.value as SearchBy)}
            aria-label="搜索类型"
          >
            <option value="auto">智能</option>
            <option value="name">刊名</option>
            <option value="topic">主题</option>
            <option value="issn">ISSN</option>
          </select>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={PLACEHOLDERS[by]}
            aria-label="检索词"
          />
          <button type="submit" disabled={busy}>
            检索
          </button>
        </form>
        <div className="filters">
          <select
            value={region}
            onChange={(e) => setRegion(e.target.value as Region)}
            aria-label="收录范围"
          >
            <option value="all">全部期刊</option>
            <option value="intl">国际刊</option>
            <option value="cn">中文刊</option>
          </select>
          <select
            value={jcr}
            onChange={(e) => setJcr(e.target.value)}
            disabled={!stats?.has_official_metrics}
            aria-label="JCR 分区"
          >
            <option value="">JCR 不限</option>
            <option value="1">JCR Q1</option>
            <option value="2">JCR Q2</option>
            <option value="3">JCR Q3</option>
            <option value="4">JCR Q4</option>
          </select>
          <select
            value={cas}
            onChange={(e) => setCas(e.target.value)}
            disabled={!stats?.has_official_metrics}
            aria-label="中科院分区"
          >
            <option value="">中科院不限</option>
            <option value="1">中科院 1 区</option>
            <option value="2">中科院 2 区</option>
            <option value="3">中科院 3 区</option>
            <option value="4">中科院 4 区</option>
          </select>
        </div>
      </section>

      <section className="toolbar">
        <form className="toolbar-group" onSubmit={(e) => { e.preventDefault(); onIngest(); }}>
          <select
            value={ingestScope}
            onChange={(e) => setIngestScope(e.target.value as IngestScope)}
            aria-label="同步范围"
          >
            <option value="all">国际 + 中文</option>
            <option value="intl">仅国际刊</option>
            <option value="cn">仅中文刊</option>
          </select>
          <button type="submit" className="secondary" disabled={busy}>
            {busy && activity?.includes("同步") ? "同步中…" : "同步 OpenAlex"}
          </button>
        </form>
        <form className="toolbar-group import-form" onSubmit={onImport}>
          <div className="field-help">
            <label htmlFor="metrics-file">导入分区/影响因子表</label>
            <p>
              选择你自己的 CSV（需有 ISSN 列）。这里不会同步期刊，只把 JCR / 中科院 / IF
              写到已入库的刊上。
            </p>
            <input
              id="metrics-file"
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file && <span className="file-name">{file.name}</span>}
          </div>
          <input
            type="number"
            min={1990}
            max={2100}
            value={importYear}
            onChange={(e) => setImportYear(e.target.value)}
            aria-label="导入年份"
            title="指标对应年份"
          />
          <button type="submit" className="secondary" disabled={busy}>
            导入 CSV
          </button>
        </form>
        <div className="toolbar-group">
          <button
            type="button"
            className="secondary"
            onClick={onCompare}
            disabled={busy || selected.length < 2}
          >
            对比已选（{selected.length}）
          </button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              const params = new URLSearchParams();
              if (selected.length >= 2) {
                params.set("ids", selected.join(","));
              } else {
                params.set("q", query);
                params.set("limit", String(PAGE_SIZE));
                params.set("by", by);
                params.set("region", region);
                params.set("sort", sort);
                if (jcr) params.set("jcr", jcr);
                if (cas) params.set("cas", cas);
              }
              downloadCsv(`/api/export?${params.toString()}`);
            }}
            disabled={busy}
          >
            导出 CSV
          </button>
        </div>
      </section>

      {activity && <p className="status working">{activity}</p>}
      {status && !activity && <p className="status ok">{status}</p>}
      {stats && (
        <p className="meta">
          本机 {stats.journals} 种期刊
          {typeof stats.chinese_journals === "number"
            ? `（中文刊 ${stats.chinese_journals}）`
            : ""}
          {" · "}导入批次 {stats.import_batches}
          {stats.last_ingest_at
            ? ` · 同步 ${new Date(stats.last_ingest_at).toLocaleString("zh-CN")}`
            : " · 尚未同步"}
          {query ? ` · ${modeLabel}` : ""}
        </p>
      )}
      {batches.length > 0 && (
        <ul className="batches">
          {batches.map((batch) => (
            <li key={batch.id}>
              {batch.year} · {batch.filename} · 匹配 {batch.matched}
              <button
                type="button"
                className="link"
                onClick={() => onDeleteBatch(batch.id)}
                disabled={busy}
              >
                删除
              </button>
            </li>
          ))}
        </ul>
      )}
      {hint && <p className="hint banner">{hint}</p>}
      {expanded.length > 0 && query && (
        <p className="hint">检索词扩展：{expanded.slice(0, 6).join(" · ")}</p>
      )}
      {error && <p className="error">{error}</p>}
      {compared && compared.length > 0 && (
        <section className="compare">
          <h2>对比</h2>
          <table>
            <thead>
              <tr>
                <th>项目</th>
                {compared.map((journal) => (
                  <th key={journal.id}>{journal.display_name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>ISSN</th>
                {compared.map((journal) => (
                  <td key={journal.id}>{journal.issn_l || "暂无"}</td>
                ))}
              </tr>
              <tr>
                <th>JCR</th>
                {compared.map((journal) => (
                  <td key={journal.id}>
                    {journal.official?.jcr_quartile
                      ? `Q${journal.official.jcr_quartile}`
                      : "暂无"}
                  </td>
                ))}
              </tr>
              <tr>
                <th>影响因子</th>
                {compared.map((journal) => (
                  <td key={journal.id}>
                    {journal.official?.impact_factor ?? "暂无"}
                  </td>
                ))}
              </tr>
              <tr>
                <th>中科院</th>
                {compared.map((journal) => (
                  <td key={journal.id}>
                    {journal.official?.cas_quartile
                      ? `${journal.official.cas_quartile} 区`
                      : "暂无"}
                  </td>
                ))}
              </tr>
              <tr>
                <th>审稿时长</th>
                {compared.map((journal) => (
                  <td key={journal.id}>
                    {journal.official?.review_days != null
                      ? `${journal.official.review_days} 天`
                      : "暂无"}
                  </td>
                ))}
              </tr>
              <tr>
                <th>被引</th>
                {compared.map((journal) => (
                  <td key={journal.id}>
                    {journal.cited_by_count.toLocaleString()}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </section>
      )}
      {!error && allResults.length === 0 && (
        <p className="empty">
          {query
            ? `没有命中「${query}」。本机库里可能还没有 Sensors / IEEE Sensors 等刊；检索时会尝试从 OpenAlex 补刊，请稍候或先点「同步 OpenAlex」。`
            : "还没有可展示的期刊。请先点「同步 OpenAlex」。"}
        </p>
      )}

      {allResults.length > 0 && (
        <div className="results-bar">
          <p>
            共 {total} 种
            {total > PAGE_SIZE
              ? ` · 第 ${currentPage + 1} / ${pageCount} 页`
              : ""}
          </p>
          <div className="sort-controls">
            <label>
              排序
              <select
                value={sort}
                onChange={(e) => {
                  const next = e.target.value as SortKey;
                  setSort(next);
                  setSortDir(DEFAULT_DIR[next]);
                  setPage(0);
                }}
                aria-label="结果排序"
              >
                <option value="relevance">相关度</option>
                <option value="cited">被引量</option>
                <option value="citedness">开放引用（OpenAlex）</option>
                <option value="impact_factor">影响因子（需导入）</option>
                <option value="review_days">审稿周期</option>
                <option value="name">刊名</option>
              </select>
            </label>
            <div className="sort-dir" role="group" aria-label="正序或倒序">
              <button
                type="button"
                className={sortDir === "desc" ? "secondary active" : "secondary"}
                onClick={() => {
                  setSortDir("desc");
                  setPage(0);
                }}
              >
                倒序
              </button>
              <button
                type="button"
                className={sortDir === "asc" ? "secondary active" : "secondary"}
                onClick={() => {
                  setSortDir("asc");
                  setPage(0);
                }}
              >
                正序
              </button>
            </div>
          </div>
        </div>
      )}
      {allResults.length > 0 && sort === "impact_factor" && (
        <p className="hint">
          影响因子排序只用你导入的 JCR IF。卡片上的「两年篇均被引」是 OpenAlex 开放引用，不是影响因子；请选「开放引用（OpenAlex）」.
        </p>
      )}

      {results.map((journal) => (
        <article key={journal.id}>
          <h2>
            <label>
              <input
                type="checkbox"
                checked={selected.includes(journal.id)}
                onChange={() => toggleSelect(journal.id)}
              />{" "}
              {journal.homepage ? (
                <a href={journal.homepage} target="_blank" rel="noreferrer">
                  {journal.display_name}
                </a>
              ) : (
                journal.display_name
              )}
            </label>
          </h2>
          <div className="facts">
            {journal.is_chinese && <span className="badge">中文刊</span>}
            <span>ISSN {journal.issn_l || "暂无"}</span>
            <span>{journal.publisher || "出版社未知"}</span>
            <span>被引 {journal.cited_by_count.toLocaleString()}</span>
            <span>
              两年篇均被引{" "}
              {journal.citedness_2yr == null
                ? "暂无"
                : `${journal.citedness_2yr.toFixed(1)}（OpenAlex，非 IF）`}
            </span>
            {journal.is_oa && <span>OA</span>}
            <span>
              审稿{" "}
              {journal.official?.review_days != null
                ? `${journal.official.review_days} 天`
                : "暂无"}
            </span>
          </div>
          {journal.alternate_titles && journal.alternate_titles.length > 0 && (
            <p className="aka">
              别名 {journal.alternate_titles.slice(0, 3).join(" · ")}
            </p>
          )}
          {journal.official ? (
            <div className="facts official">
              {journal.official.jcr_quartile != null && (
                <span>JCR Q{journal.official.jcr_quartile}</span>
              )}
              {journal.official.impact_factor != null && (
                <span>JCR IF {journal.official.impact_factor}</span>
              )}
              {journal.official.cas_quartile != null && (
                <span>中科院 {journal.official.cas_quartile} 区</span>
              )}
              {journal.official.warning && <span>预警</span>}
              <span>
                {journal.official.year} 导入
                {journal.official.filename ? ` · ${journal.official.filename}` : ""}
              </span>
            </div>
          ) : (
            <p className="hint">官方分区/IF 未导入</p>
          )}
          {journal.matched_topics && journal.matched_topics.length > 0 && (
            <p className="matched">
              命中主题：
              {journal.matched_topics
                .map((topic) => topic.topic_name)
                .join("、")}
            </p>
          )}
          {journal.topics.length > 0 && (
            <ul className="topics">
              {journal.topics.slice(0, 6).map((topic) => (
                <li key={topic.topic_name}>
                  {topic.field_name
                    ? `${topic.field_name} / ${topic.topic_name}`
                    : topic.topic_name}
                </li>
              ))}
            </ul>
          )}
        </article>
      ))}

      {total > PAGE_SIZE && (
        <nav className="pager" aria-label="分页">
          <button
            type="button"
            className="secondary"
            disabled={currentPage <= 0}
            onClick={() => setPage(currentPage - 1)}
          >
            上一页
          </button>
          <span>
            {currentPage + 1} / {pageCount}
          </span>
          <button
            type="button"
            className="secondary"
            disabled={currentPage + 1 >= pageCount}
            onClick={() => setPage(currentPage + 1)}
          >
            下一页
          </button>
        </nav>
      )}
    </main>
  );
}
