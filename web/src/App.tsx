import { FormEvent, useEffect, useState } from "react";

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
};

type Journal = {
  id: number;
  display_name: string;
  issn_l: string | null;
  publisher: string | null;
  homepage: string | null;
  is_oa: boolean;
  works_count: number;
  cited_by_count: number;
  citedness_2yr: number | null;
  topics: Topic[];
  matched_topics: Topic[];
  official: Official | null;
};

type Stats = {
  journals: number;
  topics: number;
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
  const [jcr, setJcr] = useState("");
  const [cas, setCas] = useState("");
  const [results, setResults] = useState<Journal[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [importYear, setImportYear] = useState("2025");

  async function refreshMeta() {
    const [nextStats, nextBatches] = await Promise.all([
      api<Stats>("/api/stats"),
      api<{ results: Batch[] }>("/api/imports"),
    ]);
    setStats(nextStats);
    setBatches(nextBatches.results);
  }

  function searchUrl(q: string) {
    const params = new URLSearchParams({ q, limit: "20" });
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
    }>(searchUrl(q));
    setResults(data.results);
    setHint(data.hint);
  }

  useEffect(() => {
    refreshMeta()
      .then(() => runSearch(""))
      .catch((err: Error) => setError(err.message));
  }, []);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await runSearch(query);
    } catch (err) {
      setError(err instanceof Error ? err.message : "检索失败");
    } finally {
      setBusy(false);
    }
  }

  async function onIngest() {
    setBusy(true);
    setError(null);
    try {
      await api("/api/ingest?limit=120", { method: "POST" });
      await refreshMeta();
      await runSearch(query);
    } catch (err) {
      setError(err instanceof Error ? err.message : "同步失败");
    } finally {
      setBusy(false);
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
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("year", importYear);
      body.append("source", "csv");
      await api("/api/imports", { method: "POST", body });
      setFile(null);
      await refreshMeta();
      await runSearch(query);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setBusy(false);
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

  return (
    <main>
      <header>
        <h1>选刊神器</h1>
        <p>
          本机国际刊检索。影响因子和分区只来自你导入的表，未导入就不显示。不负责投稿。
        </p>
      </header>

      <form className="row" onSubmit={onSearch}>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="研究方向、刊名或 ISSN，例如 计算机视觉 / Nature"
        />
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
        <button type="submit" disabled={busy}>
          检索
        </button>
        <button
          type="button"
          className="secondary"
          onClick={onIngest}
          disabled={busy}
        >
          同步 OpenAlex
        </button>
      </form>

      <form className="row import-row" onSubmit={onImport}>
        <input
          type="file"
          accept=".csv,text/csv"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <input
          type="number"
          min={1990}
          max={2100}
          value={importYear}
          onChange={(e) => setImportYear(e.target.value)}
          aria-label="导入年份"
        />
        <button type="submit" className="secondary" disabled={busy}>
          导入分区/IF
        </button>
      </form>

      {stats && (
        <p className="meta">
          本机 {stats.journals} 种期刊 · 导入批次 {stats.import_batches}
          {stats.last_ingest_at ? ` · 同步 ${stats.last_ingest_at}` : " · 尚未同步"}
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
      {hint && <p className="hint">{hint}</p>}
      {error && <p className="error">{error}</p>}
      {!error && results.length === 0 && (
        <p className="empty">没有结果。先同步 OpenAlex，或导入分区表后再筛选。</p>
      )}

      {results.map((journal) => (
        <article key={journal.id}>
          <h2>
            {journal.homepage ? (
              <a href={journal.homepage} target="_blank" rel="noreferrer">
                {journal.display_name}
              </a>
            ) : (
              journal.display_name
            )}
          </h2>
          <div className="facts">
            <span>ISSN {journal.issn_l || "暂无"}</span>
            <span>{journal.publisher || "出版社未知"}</span>
            <span>被引 {journal.cited_by_count.toLocaleString()}</span>
            <span>
              开放引用{" "}
              {journal.citedness_2yr == null
                ? "暂无"
                : `${journal.citedness_2yr.toFixed(1)} · OpenAlex`}
            </span>
            {journal.is_oa && <span>OA</span>}
          </div>
          {journal.official ? (
            <div className="facts official">
              {journal.official.jcr_quartile != null && (
                <span>JCR Q{journal.official.jcr_quartile}</span>
              )}
              {journal.official.impact_factor != null && (
                <span>IF {journal.official.impact_factor}</span>
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
    </main>
  );
}
