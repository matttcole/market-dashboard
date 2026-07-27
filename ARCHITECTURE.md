# Dashboard Architecture

## The decision that determines everything else

Your FRED and CoinGecko keys **cannot live in the browser**. That single constraint rules out a frontend-only app and forces this shape:

```
  scheduled ingest job  ──▶  local store  ──▶  materialized snapshot  ──▶  frontend
   (Python, has keys)         (SQLite)          (snapshot.json)          (static)
```

The frontend never talks to an external API. No CORS problems, no key exposure, no rate-limit risk from a page refresh, and the dashboard loads in one request instead of thirty.

Everything below follows from that.

---

## Stack — keep it boring

| Layer | Choice | Why not the fancier option |
|---|---|---|
| Ingest | Python + `requests` + cron | You don't need Airflow for 25 sources |
| Store | **SQLite** | ~500k rows over 10 years. Postgres is ops overhead for one user |
| Serve | Static JSON | The frontend is read-only. There's no API to build |
| Frontend | Static HTML + chart lib | React is fine, but it's not doing anything React is for |
| Host | **GitHub Actions cron → GitHub Pages** | Free, no server, and every commit is a free backup of your time series |

That last row is worth a second look. A GH Actions workflow on a cron schedule that runs the ingest, commits `snapshot.json`, and lets Pages serve it gives you a zero-cost, zero-server dashboard **and** git history of every snapshot you've ever taken. That commit history is genuinely useful — it's a free audit trail of what the data said on any given day, which is exactly what you need to build the "vs. 1 week ago" comparisons.

Running it on your Mac works too, but then the dashboard is stale whenever the laptop is shut.

---

## Schema

The instinct is a table per indicator. Resist it — you have 80+ heterogeneous series and that becomes 80 migrations. One generic observations table handles all of them.

```sql
-- What a series IS. Your namespace, not the vendor's.
CREATE TABLE series (
    series_key   TEXT PRIMARY KEY,   -- 'us.rate.10y'  (stable, yours)
    source       TEXT NOT NULL,      -- 'fred' | 'boc' | 'statcan' | 'coingecko'
    source_id    TEXT NOT NULL,      -- 'DGS10'  (vendor's, swappable)
    label        TEXT NOT NULL,
    unit         TEXT,               -- 'percent' | 'usd' | 'index' | 'bp' | 'ratio'
    frequency    TEXT,               -- 'd' | 'w' | 'm' | 'q'
    category     TEXT,               -- 'rates' | 'inflation' | 'crypto' | ...
    country      TEXT,               -- 'US' | 'CA' | 'GLOBAL'
    priority     INTEGER,            -- 1 | 2 | 3, drives panel placement
    invert       INTEGER DEFAULT 0,  -- 1 if higher = worse (for z-score colouring)
    active       INTEGER DEFAULT 1
);

-- Every observation, every series, one table.
CREATE TABLE observations (
    series_key  TEXT NOT NULL REFERENCES series(series_key),
    obs_date    TEXT NOT NULL,       -- the period the value describes
    value       REAL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (series_key, obs_date)
);
CREATE INDEX ix_obs_recent ON observations(series_key, obs_date DESC);
```

**Decouple `series_key` from `source_id` from day one.** When a BoC series ID changes or you swap Stooq for something else, you edit one row in `series` and every downstream query, chart, and frontend reference keeps working. This costs nothing now and saves a refactor later.

### Revisions

GDP, payrolls, and Canadian GDP all get revised. Full vintage tracking (adding `vintage_date` to the PK) complicates every single query. Cheaper pattern — only log when a value you've already seen *changes*:

```sql
CREATE TABLE revisions (
    series_key TEXT, obs_date TEXT,
    old_value REAL, new_value REAL, detected_at TEXT
);
```

Your upsert checks for a differing value before writing. You get a revision feed (genuinely interesting — "payrolls revised down 62k" is a real signal) without paying the vintage tax on normal reads.

### Rate probabilities — different shape, own table

```sql
CREATE TABLE rate_probabilities (
    asof_date     TEXT NOT NULL,
    central_bank  TEXT NOT NULL,     -- 'FED' | 'BOC'
    meeting_date  TEXT NOT NULL,
    outcome       TEXT NOT NULL,     -- 'hold' | '-25bp' | '-50bp' | '+25bp'
    probability   REAL NOT NULL,
    implied_rate  REAL,
    anchor        TEXT,              -- 'clean' | 'split' | 'assumed'
    PRIMARY KEY (asof_date, central_bank, meeting_date, outcome)
);
```

Storing by `asof_date` is what gives you FedWatch's best feature: **current vs. 1 day ago vs. 1 week ago**. The probability level is much less interesting than the direction it's been moving. Store from the first run or you'll wish you had.

### Calendar

```sql
CREATE TABLE calendar_events (
    event_id     TEXT PRIMARY KEY,
    release_ts   TEXT NOT NULL,      -- ISO8601 with timezone
    country      TEXT, name TEXT,
    importance   INTEGER,            -- 1-3
    series_key   TEXT,               -- links to the series it updates
    previous     REAL, consensus REAL, actual REAL,
    surprise_z   REAL                -- (actual - consensus) / stdev(historical surprises)
);
```

That `surprise_z` column is what you later aggregate into your own Citi Economic Surprise Index equivalent. Rolling 3-month mean of `surprise_z` per country. Nobody free has this.

---

## Caching — four layers, each doing one job

| Layer | What | Lifetime | Why it exists |
|---|---|---|---|
| **L1** HTTP conditional | ETag / `If-Modified-Since` | per-request | FRED honours these. Free bandwidth + rate-limit savings on unchanged data |
| **L2** Raw response log | `raw_responses(url_hash, fetched_at, status, body)` | 7 days | **When a scrape breaks, this is what saves you.** Diff today's HTML against Tuesday's and you'll see what changed in 30 seconds |
| **L3** `observations` | Parsed, canonical | forever | Source of truth |
| **L4** `snapshot.json` | Materialized, denormalized | regenerated each ingest | What the frontend loads. One file, one request |

L2 is the one people skip and then regret. Farside is an HTML scrape with no SLA — it *will* break, and having the last known-good body on disk turns a debugging session into a diff.

---

## Refresh cadences

Driven by when each source actually publishes, not by round numbers.

### Intraday

| Source | Cadence | Window | Notes |
|---|---|---|---|
| CoinGecko | **10 min** | 16h/day | See budget below — this is the binding constraint |
| Stooq / Yahoo quotes | 15 min | market hours | Delayed anyway; faster gains nothing |
| ZQ futures strip | 15 min | 08:00–16:00 CT | Plus one settlement pull after 16:00 CT |
| DefiLlama stablecoins | 1 hr | 24h | Moves slowly |

**CoinGecko budget math.** <cite>10,000 calls/month</cite> ÷ 30 days = 333/day. At 2 calls per cycle (`/simple/price` + `/global`), 10-minute intervals over a 16-hour window = 96 cycles × 2 = **192 calls/day ≈ 5,800/month**. That leaves ~40% headroom for retries and manual pokes. Going to 5-minute intervals blows the monthly cap around day 22 — don't.

### Daily, timed to publication

| Source | Run at (ET) | Because |
|---|---|---|
| BoC bond yields | 10:15 | Published 09:30–10:00 ET |
| BoC interest rates | 12:45 | Published 12:15–12:30 ET |
| BoC FX (USD/CAD) | 16:45 | Published 16:30 ET |
| StatCan releases | 09:00 | Releases land 08:30 ET |
| NY Fed RRP | 13:30 | Op results post ~13:15 |
| Treasury TGA | 16:30 | Daily statement posts EOD |
| FRED daily series | 09:00 | Most update overnight |
| Farside ETF flows | 19:00 | Compiled after US close |
| Fear & Greed | 09:00 | Updates once daily |

### Weekly / event-driven

| Source | When |
|---|---|
| **WALCL** (Fed balance sheet) | Thu 16:45 ET — H.4.1 releases Thursday |
| Initial claims (`ICSA`) | Thu 09:00 ET |
| Calendar deep refresh | Sun 06:00 ET |
| FOMC / BoC date re-scrape | Monthly |

---

## The mixed-frequency problem

This bites everyone building a macro dashboard and it has no clever solution, only a disciplined one.

Your panel mixes daily FX, weekly WALCL, monthly CPI, and quarterly GDP. **Pick one rule and never break it:**

> Display the latest available observation, always stamped with its own `obs_date`. Never forward-fill in the display layer.

If WALCL is five days old, the tile says "as of Jul 22" — it does not silently pretend to be today's number. For *derived* series like net liquidity, forward-fill the inputs to compute, but **stamp the result with the oldest contributing input's date**. Net liquidity is only as fresh as WALCL, and the display must say so.

The failure mode you're avoiding: glancing at a tile in six months, assuming it's current, and making a decision on a stale number.

---

## Backfill

Z-scores and percentile ranks need 10 years of history. Your first run is a different job from every subsequent run:

- **FRED**: full history in one call per series — trivial
- **BoC Valet**: full history via `/observations/{series}/json` with no `recent` param
- **StatCan**: `getBulkVectorDataByRange` for the long pull, then `getDataFromVectorsAndLatestNPeriods` incrementally
- **CoinGecko**: free tier history is limited — accept a shorter window for crypto z-scores, or seed from a one-time CSV

Run backfill once, gate it behind a flag, then never touch it again.

---

## Build order

1. **Verification spike** ← `verify_sources.py`. One hour. Nothing else starts until this is green.
2. Schema + ingest for the ~15 P1 FRED series. One source, end to end, proves the pattern.
3. Add BoC + StatCan. Now you have two source *shapes* (REST GET, POST-with-body).
4. `snapshot.json` + the crudest possible HTML table. **Look at real numbers on a screen.** This is where you find out which indicators you actually care about, and it's always fewer than the list suggests.
5. FedWatch module ← `fedwatch.py`, already written.
6. Crypto panel.
7. Calendar.
8. Z-scores, "what changed" strip, surprise index.

Step 4 before step 5 is deliberate. Ugly and real beats polished and hypothetical — you'll cut a third of your indicator list the first time you see them all on one screen, and it's cheaper to cut them before you've built tiles for them.
