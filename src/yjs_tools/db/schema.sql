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
