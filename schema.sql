-- Series registry: stable identifiers + metadata
CREATE TABLE IF NOT EXISTS series (
    series_key TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    label TEXT NOT NULL,
    unit TEXT,
    frequency TEXT,
    category TEXT,
    country TEXT,
    priority INTEGER DEFAULT 2,
    invert INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1
);

-- All observations: every series, every date
CREATE TABLE IF NOT EXISTS observations (
    series_key TEXT NOT NULL,
    obs_date TEXT NOT NULL,
    value REAL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (series_key, obs_date),
    FOREIGN KEY (series_key) REFERENCES series(series_key)
);

CREATE INDEX IF NOT EXISTS ix_obs_recent ON observations(series_key, obs_date DESC);

-- Track when values change
CREATE TABLE IF NOT EXISTS revisions (
    series_key TEXT NOT NULL,
    obs_date TEXT NOT NULL,
    old_value REAL,
    new_value REAL,
    detected_at TEXT,
    FOREIGN KEY (series_key) REFERENCES series(series_key)
);

-- Raw API responses for debugging (7-day retention)
CREATE TABLE IF NOT EXISTS raw_responses (
    url_hash TEXT,
    fetched_at TEXT,
    status INTEGER,
    body TEXT
);

CREATE INDEX IF NOT EXISTS ix_raw_recent ON raw_responses(fetched_at DESC);
