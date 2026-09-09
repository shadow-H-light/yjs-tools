import { FormEvent, useEffect, useState } from "react";

type Job = {
  title: string;
  major: string | null;
  city: string | null;
  year: number | null;
};

type Round = {
  year: number;
  season: string;
  start_date: string | null;
  end_date: string | null;
  headcount: number | null;
};

type Finance = {
  year: number;
  revenue: number | null;
  net_income: number | null;
  source: string | null;
};

type Dispute = {
  year: number | null;
  case_type: string | null;
  summary: string | null;
  url: string | null;
};

type Uni = {
  university: string;
  relation: string | null;
  works_count: number | null;
  source: string | null;
};

type Company = {
  id: number;
  wikidata_id: string;
  display_name: string;
  homepage: string | null;
  ticker: string | null;
  credit_code: string | null;
  hq_city: string | null;
  ownership: string;
  ownership_label: string;
  is_central_soe: boolean;
  bianzhi: string | null;
  size_band: string | null;
  size_label: string | null;
  foreign_origin: string | null;
  employees: number | null;
  salary_note: string | null;
  industries: string[];
  jobs: Job[];
  rounds: Round[];
  finance: Finance[];
  disputes: Dispute[];
  universities: Uni[];
  matched: string[];
};

type Stats = {
  companies: number;
  jobs: number;
  import_batches: number;
  last_ingest_at: string | null;
};

type Batch = {
  id: number;
  filename: string;
  year: number;
  kind: string;
  matched: number;
  unmatched: number;
};

type SearchBy = "auto" | "name" | "industry" | "code" | "major" | "job";

const PAGE_SIZES = [10, 20, 50] as const;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body.detail) message = String(body.detail);
    } catch {
      /* keep */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export default function CompanyView() {
  const [query, setQuery] = useState("");
  const [by, setBy] = useState<SearchBy>("auto");
  const [ownership, setOwnership] = useState("");
  const [city, setCity] = useState("");
  const [season, setSeason] = useState("");
  const [central, setCentral] = useState("");
  const [size, setSize] = useState("");
  const [results, setResults] = useState<Company[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [activity, setActivity] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [importKind, setImportKind] = useState("companies");
  const [importYear, setImportYear] = useState("2026");
  const [selected, setSelected] = useState<number[]>([]);
  const [compared, setCompared] = useState<Company[] | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);

  async function refreshMeta() {
    const [nextStats, nextBatches] = await Promise.all([
      api<Stats>("/api/companies/stats"),
      api<{ results: Batch[] }>("/api/companies/imports"),
    ]);
    setStats(nextStats);
    setBatches(nextBatches.results);
  }

  async function runSearch(q: string, nextPage = page, nextSize = pageSize) {
    const params = new URLSearchParams({
      q,
      limit: String(nextSize),
      offset: String(nextPage * nextSize),
      by,
    });
    if (ownership) params.set("ownership", ownership);
    if (city) params.set("city", city);
    if (season) params.set("season", season);
    if (central) params.set("central", "true");
    if (size) params.set("size", size);
    const data = await api<{
      results: Company[];
      hint: string | null;
      total?: number;
      count?: number;
    }>(`/api/companies?${params}`);
    setResults(data.results);
    setTotal(data.total ?? data.count ?? data.results.length);
    setHint(data.hint);
  }

  useEffect(() => {
    refreshMeta()
      .then(() => runSearch("", 0, pageSize))
      .catch((err: Error) => setError(err.message));
  }, []);

  async function onSearch(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setPage(0);
    try {
      await runSearch(query, 0, pageSize);
    } catch (err) {
      setError(err instanceof Error ? err.message : "检索失败");
    } finally {
      setBusy(false);
    }
  }

  async function onIngest() {
    setBusy(true);
    setError(null);
    setActivity("正在从 Wikidata 同步企业，可能需要几分钟。");
    try {
      const result = await api<{
        inserted: number;
        updated: number;
        total: number;
        stats: Stats;
      }>("/api/companies/ingest?limit=400", { method: "POST" });
      setStatus(
        `同步完成：新增 ${result.inserted}，更新 ${result.updated}。库中 ${result.stats.companies} 家。`,
      );
      await refreshMeta();
      setPage(0);
      await runSearch(query, 0, pageSize);
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
      setError("请先选择文件");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      body.append("year", importYear);
      body.append("kind", importKind);
      const result = await api<{ matched: number; unmatched: number }>(
        "/api/companies/imports",
        { method: "POST", body },
      );
      setFile(null);
      setStatus(`导入完成：匹配 ${result.matched}，未匹配 ${result.unmatched}。`);
      await refreshMeta();
      setPage(0);
      await runSearch(query, 0, pageSize);
    } catch (err) {
      setError(err instanceof Error ? err.message : "导入失败");
    } finally {
      setBusy(false);
    }
  }

  function toggleSelect(id: number) {
    setSelected((current) => {
      if (current.includes(id)) return current.filter((item) => item !== id);
      if (current.length >= 4) return current;
      return [...current, id];
    });
  }

  async function onCompare() {
    if (selected.length < 2) {
      setError("请勾选 2–4 家公司再对比");
      return;
    }
    setBusy(true);
    try {
      const data = await api<{ results: Company[] }>(
        `/api/companies/compare?ids=${selected.join(",")}`,
      );
      setCompared(data.results);
    } catch (err) {
      setError(err instanceof Error ? err.message : "对比失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className="eyebrow">本机查公司 · 不投递</p>
      <section className="search-card">
        <form className="search-bar" onSubmit={onSearch}>
          <select
            className="search-by"
            value={by}
            onChange={(e) => setBy(e.target.value as SearchBy)}
            aria-label="搜索类型"
          >
            <option value="auto">智能</option>
            <option value="name">名称</option>
            <option value="industry">行业</option>
            <option value="major">专业</option>
            <option value="job">岗位</option>
            <option value="code">代码</option>
          </select>
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="公司名、专业、岗位或 QID，例如 华为 / 光学工程"
            aria-label="检索词"
          />
          <button type="submit" disabled={busy}>
            检索
          </button>
        </form>
        <div className="filters">
          <select
            value={ownership}
            onChange={(e) => setOwnership(e.target.value)}
            aria-label="所有制"
          >
            <option value="">类型不限</option>
            <option value="soe">国企</option>
            <option value="private">私企</option>
            <option value="foreign">外企</option>
          </select>
          <select
            value={central}
            onChange={(e) => setCentral(e.target.value)}
            aria-label="是否央企"
          >
            <option value="">央企不限</option>
            <option value="1">仅央企</option>
          </select>
          <select
            value={size}
            onChange={(e) => setSize(e.target.value)}
            aria-label="规模"
          >
            <option value="">规模不限</option>
            <option value="large">大厂</option>
            <option value="medium">中厂</option>
            <option value="small">小厂</option>
          </select>
          <select
            value={season}
            onChange={(e) => setSeason(e.target.value)}
            aria-label="校招季节"
          >
            <option value="">届别不限</option>
            <option value="秋招">秋招</option>
            <option value="春招">春招</option>
            <option value="实习">实习</option>
          </select>
          <input
            type="search"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            placeholder="工作地点"
            aria-label="地点"
            style={{ maxWidth: 140 }}
          />
        </div>
      </section>

      <section className="toolbar">
        <form
          className="toolbar-group"
          onSubmit={(e) => {
            e.preventDefault();
            onIngest();
          }}
        >
          <button type="submit" className="secondary" disabled={busy}>
            {busy && activity?.includes("Wikidata") ? "同步中…" : "同步 Wikidata"}
          </button>
        </form>
        <form className="toolbar-group import-form" onSubmit={onImport}>
          <select
            value={importKind}
            onChange={(e) => setImportKind(e.target.value)}
            aria-label="导入类型"
          >
            <option value="companies">公司/编制/央企/薪资</option>
            <option value="jobs">岗位与校招</option>
            <option value="disputes">纠纷</option>
            <option value="universities">密切高校</option>
          </select>
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <input
            type="number"
            min={1990}
            max={2100}
            value={importYear}
            onChange={(e) => setImportYear(e.target.value)}
            aria-label="年份"
          />
          <button type="submit" className="secondary" disabled={busy}>
            导入表
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
              if (selected.length >= 2) params.set("ids", selected.join(","));
              else {
                params.set("q", query);
                params.set("by", by);
              }
              const link = document.createElement("a");
              link.href = `/api/companies/export?${params}`;
              link.download = "gongsi.csv";
              link.click();
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
          本机 {stats.companies} 家公司 · 岗位 {stats.jobs}
          {" · "}导入 {stats.import_batches}
          {stats.last_ingest_at
            ? ` · 同步 ${new Date(stats.last_ingest_at).toLocaleString("zh-CN")}`
            : " · 尚未同步"}
        </p>
      )}
      {batches.length > 0 && (
        <ul className="batches">
          {batches.map((batch) => (
            <li key={batch.id}>
              {batch.kind} · {batch.filename} · 匹配 {batch.matched}
            </li>
          ))}
        </ul>
      )}
      {hint && <p className="hint banner">{hint}</p>}
      {error && <p className="error">{error}</p>}

      {total > 0 && (
        <div className="results-bar">
          <p>
            共 {total} 家
            {total > pageSize ? ` · 第 ${page + 1} / ${Math.max(1, Math.ceil(total / pageSize))} 页` : ""}
          </p>
          <label>
            每页
            <select
              value={pageSize}
              onChange={(e) => {
                const next = Number(e.target.value);
                setPageSize(next);
                setPage(0);
                setBusy(true);
                runSearch(query, 0, next)
                  .catch((err: Error) => setError(err.message))
                  .finally(() => setBusy(false));
              }}
              aria-label="每页条数"
            >
              {PAGE_SIZES.map((sizeOption) => (
                <option key={sizeOption} value={sizeOption}>
                  {sizeOption}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      {compared && compared.length > 0 && (
        <section className="compare">
          <h2>对比</h2>
          <table>
            <thead>
              <tr>
                <th>项目</th>
                {compared.map((c) => (
                  <th key={c.id}>{c.display_name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th>类型</th>
                {compared.map((c) => (
                  <td key={c.id}>
                    {c.is_central_soe ? "央企" : c.ownership_label}
                    {c.size_label ? ` · ${c.size_label}` : ""}
                    {c.foreign_origin ? ` · ${c.foreign_origin}` : ""}
                  </td>
                ))}
              </tr>
              <tr>
                <th>编制</th>
                {compared.map((c) => (
                  <td key={c.id}>{c.bianzhi || "暂无"}</td>
                ))}
              </tr>
              <tr>
                <th>地点</th>
                {compared.map((c) => (
                  <td key={c.id}>
                    {c.jobs[0]?.city || c.hq_city || "暂无"}
                  </td>
                ))}
              </tr>
              <tr>
                <th>薪资</th>
                {compared.map((c) => (
                  <td key={c.id}>{c.salary_note || "暂无"}</td>
                ))}
              </tr>
              <tr>
                <th>链接</th>
                {compared.map((c) => (
                  <td key={c.id}>
                    {c.homepage ? (
                      <a href={c.homepage} target="_blank" rel="noreferrer">
                        官网
                      </a>
                    ) : (
                      "暂无"
                    )}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </section>
      )}

      {results.length === 0 && !error && (
        <p className="empty">
          {query
            ? `没有命中「${query}」。可换检索类型，或先点「同步 Wikidata」。`
            : "还没有可展示的公司。请先点「同步 Wikidata」。"}
        </p>
      )}

      {results.map((company) => (
        <article key={company.id}>
          <h2>
            <label>
              <input
                type="checkbox"
                checked={selected.includes(company.id)}
                onChange={() => toggleSelect(company.id)}
              />{" "}
              {company.display_name}
            </label>
          </h2>
          <div className="facts">
            <span className="badge">
              {company.is_central_soe ? "央企" : company.ownership_label}
            </span>
            {company.size_label && <span className="badge">{company.size_label}</span>}
            {company.foreign_origin && (
              <span>外资归属 {company.foreign_origin}</span>
            )}
          </div>
          <dl className="required-facts">
            <div>
              <dt>公司编号</dt>
              <dd>
                {company.wikidata_id}
                {company.ticker ? ` · ${company.ticker}` : ""}
                {company.credit_code ? ` · ${company.credit_code}` : ""}
              </dd>
            </div>
            <div>
              <dt>公司链接</dt>
              <dd>
                {company.homepage ? (
                  <a href={company.homepage} target="_blank" rel="noreferrer">
                    打开官网
                  </a>
                ) : (
                  "暂无"
                )}
              </dd>
            </div>
            <div>
              <dt>地点</dt>
              <dd>
                {company.jobs.find((job) => job.city)?.city ||
                  (company.hq_city ? `总部 · ${company.hq_city}` : "暂无")}
              </dd>
            </div>
            <div>
              <dt>行业</dt>
              <dd>{company.industries.slice(0, 4).join(" · ") || "暂无"}</dd>
            </div>
            <div>
              <dt>编制</dt>
              <dd>{company.bianzhi || "暂无"}</dd>
            </div>
            {company.salary_note && (
              <div>
                <dt>薪资</dt>
                <dd>{company.salary_note}</dd>
              </div>
            )}
            {company.rounds[0] && (
              <div>
                <dt>校招</dt>
                <dd>
                  {company.rounds[0].year} {company.rounds[0].season}
                  {company.rounds[0].start_date
                    ? ` ${company.rounds[0].start_date}–${company.rounds[0].end_date || "?"}`
                    : ""}
                  {company.rounds[0].headcount != null
                    ? ` · ${company.rounds[0].headcount} 人`
                    : ""}
                </dd>
              </div>
            )}
          </dl>
          {company.jobs.length > 0 && (
            <p className="matched">
              岗位{" "}
              {company.jobs
                .slice(0, 4)
                .map((job) =>
                  job.city ? `${job.title}（${job.city}）` : job.title,
                )
                .join("、")}
            </p>
          )}
          {company.universities.length > 0 && (
            <p className="aka">
              密切高校{" "}
              {company.universities
                .slice(0, 4)
                .map((u) => u.university)
                .join(" · ")}
            </p>
          )}
          {company.finance.length > 0 && (
            <p className="hint">
              财务 {company.finance[0].year} · 来源 {company.finance[0].source}
              {company.finance[0].revenue != null
                ? ` · 营收 ${company.finance[0].revenue}`
                : ""}
            </p>
          )}
          {company.disputes.length > 0 && (
            <p className="hint">
              纠纷 {company.disputes[0].case_type || ""}{" "}
              {company.disputes[0].summary || "已导入"}（非天眼查）
            </p>
          )}
          {company.matched.length > 0 && (
            <p className="matched">命中：{company.matched.join("、")}</p>
          )}
        </article>
      ))}

      {total > pageSize && (
        <nav className="pager" aria-label="分页">
          <button
            type="button"
            className="secondary"
            disabled={busy || page <= 0}
            onClick={() => {
              const next = page - 1;
              setPage(next);
              setBusy(true);
              runSearch(query, next, pageSize)
                .catch((err: Error) => setError(err.message))
                .finally(() => setBusy(false));
            }}
          >
            上一页
          </button>
          <span>
            {page + 1} / {Math.max(1, Math.ceil(total / pageSize))}
          </span>
          <button
            type="button"
            className="secondary"
            disabled={busy || page + 1 >= Math.ceil(total / pageSize)}
            onClick={() => {
              const next = page + 1;
              setPage(next);
              setBusy(true);
              runSearch(query, next, pageSize)
                .catch((err: Error) => setError(err.message))
                .finally(() => setBusy(false));
            }}
          >
            下一页
          </button>
        </nav>
      )}
    </>
  );
}
