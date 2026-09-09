CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journals (
    id INTEGER PRIMARY KEY,
    openalex_id TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    issn_l TEXT,
    issns TEXT,
    alternate_titles TEXT,
    publisher TEXT,
    homepage TEXT,
    is_oa INTEGER NOT NULL DEFAULT 0,
    works_count INTEGER NOT NULL DEFAULT 0,
    cited_by_count INTEGER NOT NULL DEFAULT 0,
    citedness_2yr REAL,
    country_code TEXT,
    type TEXT,
    is_chinese INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_topics (
    journal_id INTEGER NOT NULL REFERENCES journals(id) ON DELETE CASCADE,
    topic_id TEXT NOT NULL,
    topic_name TEXT NOT NULL,
    field_name TEXT,
    share REAL,
    PRIMARY KEY (journal_id, topic_id)
);

CREATE TABLE IF NOT EXISTS import_batches (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    year INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'csv',
    imported_at TEXT NOT NULL,
    matched INTEGER NOT NULL DEFAULT 0,
    unmatched INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS journal_metrics (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES import_batches(id) ON DELETE CASCADE,
    journal_id INTEGER NOT NULL REFERENCES journals(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    jcr_quartile INTEGER,
    impact_factor REAL,
    impact_factor_5 REAL,
    cas_quartile INTEGER,
    warning INTEGER NOT NULL DEFAULT 0,
    review_days INTEGER
);

CREATE INDEX IF NOT EXISTS idx_journals_issn_l ON journals(issn_l);
CREATE INDEX IF NOT EXISTS idx_journals_chinese ON journals(is_chinese);
CREATE INDEX IF NOT EXISTS idx_journals_cited ON journals(cited_by_count DESC);
CREATE INDEX IF NOT EXISTS idx_topics_name ON journal_topics(topic_name);
CREATE INDEX IF NOT EXISTS idx_metrics_journal_year ON journal_metrics(journal_id, year);
CREATE INDEX IF NOT EXISTS idx_metrics_batch ON journal_metrics(batch_id);

CREATE VIRTUAL TABLE IF NOT EXISTS journals_fts USING fts5(
    display_name,
    issn_l,
    issns,
    publisher,
    content='journals',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS journals_ai AFTER INSERT ON journals BEGIN
    INSERT INTO journals_fts(rowid, display_name, issn_l, issns, publisher)
    VALUES (new.id, new.display_name, new.issn_l, new.issns, new.publisher);
END;

CREATE TRIGGER IF NOT EXISTS journals_ad AFTER DELETE ON journals BEGIN
    INSERT INTO journals_fts(journals_fts, rowid, display_name, issn_l, issns, publisher)
    VALUES ('delete', old.id, old.display_name, old.issn_l, old.issns, old.publisher);
END;

CREATE TRIGGER IF NOT EXISTS journals_au AFTER UPDATE ON journals BEGIN
    INSERT INTO journals_fts(journals_fts, rowid, display_name, issn_l, issns, publisher)
    VALUES ('delete', old.id, old.display_name, old.issn_l, old.issns, old.publisher);
    INSERT INTO journals_fts(rowid, display_name, issn_l, issns, publisher)
    VALUES (new.id, new.display_name, new.issn_l, new.issns, new.publisher);
END;

CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY,
    wikidata_id TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    aliases TEXT,
    homepage TEXT,
    ticker TEXT,
    credit_code TEXT,
    country_code TEXT,
    hq_city TEXT,
    ownership TEXT,
    is_central_soe INTEGER NOT NULL DEFAULT 0,
    bianzhi TEXT,
    size_band TEXT,
    foreign_origin TEXT,
    employees INTEGER,
    founded_year INTEGER,
    salary_note TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS company_industries (
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    industry TEXT NOT NULL,
    PRIMARY KEY (company_id, industry)
);

CREATE TABLE IF NOT EXISTS company_import_batches (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    year INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'companies',
    source TEXT NOT NULL DEFAULT 'csv',
    imported_at TEXT NOT NULL,
    matched INTEGER NOT NULL DEFAULT 0,
    unmatched INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS company_jobs (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    batch_id INTEGER REFERENCES company_import_batches(id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    major TEXT,
    city TEXT,
    education TEXT,
    year INTEGER
);

CREATE TABLE IF NOT EXISTS recruitment_rounds (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    batch_id INTEGER REFERENCES company_import_batches(id) ON DELETE SET NULL,
    year INTEGER NOT NULL,
    season TEXT NOT NULL,
    start_date TEXT,
    end_date TEXT,
    headcount INTEGER,
    source TEXT
);

CREATE TABLE IF NOT EXISTS company_finance (
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    year INTEGER NOT NULL,
    revenue REAL,
    net_income REAL,
    currency TEXT,
    source TEXT,
    PRIMARY KEY (company_id, year, source)
);

CREATE TABLE IF NOT EXISTS company_disputes (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    batch_id INTEGER REFERENCES company_import_batches(id) ON DELETE CASCADE,
    year INTEGER,
    case_type TEXT,
    summary TEXT,
    url TEXT
);

CREATE TABLE IF NOT EXISTS company_universities (
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    university TEXT NOT NULL,
    relation TEXT,
    works_count INTEGER,
    source TEXT,
    PRIMARY KEY (company_id, university, source)
);

CREATE INDEX IF NOT EXISTS idx_companies_ticker ON companies(ticker);
CREATE INDEX IF NOT EXISTS idx_companies_ownership ON companies(ownership);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON company_jobs(company_id);
CREATE INDEX IF NOT EXISTS idx_rounds_company ON recruitment_rounds(company_id);

CREATE VIRTUAL TABLE IF NOT EXISTS companies_fts USING fts5(
    display_name,
    aliases,
    ticker,
    wikidata_id,
    content='companies',
    content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS companies_ai AFTER INSERT ON companies BEGIN
    INSERT INTO companies_fts(rowid, display_name, aliases, ticker, wikidata_id)
    VALUES (new.id, new.display_name, new.aliases, new.ticker, new.wikidata_id);
END;

CREATE TRIGGER IF NOT EXISTS companies_ad AFTER DELETE ON companies BEGIN
    INSERT INTO companies_fts(companies_fts, rowid, display_name, aliases, ticker, wikidata_id)
    VALUES ('delete', old.id, old.display_name, old.aliases, old.ticker, old.wikidata_id);
END;

CREATE TRIGGER IF NOT EXISTS companies_au AFTER UPDATE ON companies BEGIN
    INSERT INTO companies_fts(companies_fts, rowid, display_name, aliases, ticker, wikidata_id)
    VALUES ('delete', old.id, old.display_name, old.aliases, old.ticker, old.wikidata_id);
    INSERT INTO companies_fts(rowid, display_name, aliases, ticker, wikidata_id)
    VALUES (new.id, new.display_name, new.aliases, new.ticker, new.wikidata_id);
END;
