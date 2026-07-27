# Market Watch & Economic Calendar Dashboard — Data Point & API Map

**Focus:** Canada + USA macro, rates, markets, crypto
**Constraint:** free / near-free data sources only
**Priority key:** `P1` = build first (core dashboard) · `P2` = high value, add second · `P3` = nice to have

---

## 1. The Free Source Stack

Everything below is built on these. Get keys for the first four before you write any code.

| Source | Key? | Limits | Covers | Base URL |
|---|---|---|---|---|
| **FRED** (St. Louis Fed) | Free key | 120 req/min | ~80% of US macro + rates + spreads + some indices | `https://api.stlouisfed.org/fred/` |
| **Bank of Canada Valet** | None | Unpublished, be polite | BoC policy rate, GoC yields, CORRA, FX, CPI | `https://www.bankofcanada.ca/valet/` |
| **StatCan WDS** | None | Discrete points only, not bulk | Canadian CPI, GDP, LFS, retail, housing | `https://www150.statcan.gc.ca/t1/wds/rest/` |
| **CoinGecko Demo** | Free key | 100 calls/min, 10k/month | Prices, dominance, total mcap, volumes | `https://api.coingecko.com/api/v3/` |
| **US Treasury Fiscal Data** | None | None published | TGA balance, debt, auctions | `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/` |
| **NY Fed Markets API** | None | None published | RRP, SOFR, EFFR, repo ops | `https://markets.newyorkfed.org/api/` |
| **DefiLlama** | None | Generous | Stablecoin supply, TVL, chain flows | `https://api.llama.fi/` · `https://stablecoins.llama.fi/` |
| **Alternative.me** | None | Generous | Crypto Fear & Greed | `https://api.alternative.me/fng/` |
| **Stooq** | None | Polite scraping | EOD index/commodity/FX CSV, incl. TSX | `https://stooq.com/q/d/l/` |
| **BLS** | Free key | 500 req/day | US CPI, employment, release schedule | `https://api.bls.gov/publicAPI/v2/` |
| **BEA** | Free key | 100 req/min | GDP, PCE detail | `https://apps.bea.gov/api/data/` |

**A note on series IDs below:** FRED IDs are verified and stable. Bank of Canada and StatCan IDs I've marked `⚠️ verify` where you should confirm against the discovery endpoint rather than trusting the ID blind — these registries change and a wrong ID fails silently as an empty array.

- BoC series discovery: `https://www.bankofcanada.ca/valet/lists/series/json` and `/valet/lists/groups/json`
- StatCan table discovery: `POST /getAllCubesListLite`, then `getSeriesInfoFromCubePidCoord` to resolve a table+coordinate into a vector ID

---

## 2. Central Bank Policy & Rate Expectations

The heart of the dashboard. This is what everything else feeds into.

| Data point | Pri | Source | Endpoint / ID | Notes |
|---|---|---|---|---|
| Fed funds target (upper/lower) | P1 | FRED | `DFEDTARU`, `DFEDTARL` | Daily |
| Effective fed funds rate | P1 | NY Fed | `/api/rates/unsecured/effr/last/1.json` | Also FRED `EFFR` |
| BoC target overnight rate | P1 | BoC Valet | `/observations/V39079/json` ⚠️ verify | Also referenced as `CBC20210` — check both |
| BoC Bank Rate / deposit rate | P2 | BoC Valet | group `interest_rates` ⚠️ verify | |
| **FedWatch probabilities** | P1 | See below | — | **No free API.** Three options ↓ |
| **BoC implied probabilities** | P1 | Derive from CORRA OIS | — | No published tool. See below ↓ |
| Next FOMC meeting date | P1 | Fed (scrape) | `federalreserve.gov/monetarypolicy/fomccalendars.htm` | Stable annual HTML page, parse once/month |
| Next BoC announcement date | P1 | BoC (scrape) | `bankofcanada.ca/press/upcoming-events/` | 8 fixed dates/yr, published a year ahead |
| Fed dot plot (SEP) | P2 | Fed (PDF/HTML) | Released at 4 of 8 FOMC meetings | Manual-ish; quarterly cadence |
| BoC MPR flag | P2 | Derived | — | Only 4 of 8 BoC dates have an MPR + presser. Flag these — they're the high-vol ones |
| Fed/BoC speaker calendar | P3 | Scrape | Fed calendar page; BoC "upcoming events" | |
| Blackout period dates | P2 | Derived | FOMC date − 10 days to +1 day | Compute it, don't source it |

### On FedWatch specifically

CME's FedWatch API is **$25/month** for end-of-day, more for intraday. Free paths:

1. **Compute it yourself from ZQ futures settlements.** Implied rate = `100 − futures price`. Settlement prices are published free on CME's site daily. For a meeting mid-month you blend the pre/post-meeting portions of the contract month by day count, then back out the probability distribution across 25bp buckets. Well-documented methodology, maybe 150 lines of code.
2. **`centralbank.watch`** publishes free daily-recalculated probabilities claiming ~96–97% alignment with FedWatch. No API, but a scrapeable page. Good fallback / cross-check.
3. **Pay the $25.** If this dashboard is something you'll use daily, this is the single best $25 you'll spend on it — it removes the most fragile piece of the build.

### On BoC probabilities

There is no BoCWatch. You derive it from **CORRA OIS pricing** or from **BAX / CORRA futures** (Montréal Exchange). MX publishes settlement prices free with a delay. Same math as ZQ. Given Canada is half your focus, this is worth building — it's a genuine differentiator versus every US-centric dashboard out there.

---

## 3. Inflation — *the biggest gap in your original list*

This is what the Fed and BoC are actually reacting to. Without it, your FedWatch panel has no explanatory context.

| Data point | Pri | Source | Endpoint / ID | Notes |
|---|---|---|---|---|
| **US Core PCE** (the Fed's actual target) | P1 | FRED | `PCEPILFE` | Monthly. Not CPI — this is the one the Fed targets |
| US headline PCE | P1 | FRED | `PCEPI` | |
| US CPI headline | P1 | FRED | `CPIAUCSL` | |
| US CPI core | P1 | FRED | `CPILFESL` | |
| US PPI | P2 | FRED | `PPIFIS` (final demand) | |
| **Canada CPI headline** | P1 | StatCan | Table `18-10-0004-01` ⚠️ verify vector | Also on BoC Valet, group `CPI_MONTHLY` |
| **Canada CPI-trim / CPI-median** | P1 | BoC Valet | group `BOC_CORE_INFLATION` ⚠️ verify | **The BoC's preferred core measures.** These are what they cite in statements — more important than headline |
| Canada CPI-common | P2 | BoC Valet | same group | De-emphasized by BoC since 2022 but still tracked |
| US 10y breakeven | P2 | FRED | `T10YIE` | Market-implied inflation |
| **US 5y5y forward inflation** | P2 | FRED | `T5YIFR` | The Fed's favourite expectations gauge |
| U. Michigan 1yr expectations | P2 | FRED | `MICH` | |
| U. Michigan 5yr expectations | P3 | FRED | `MICH5YR` ⚠️ verify | |

---

## 4. Rates & the Yield Curve

You had policy rates only. The curve is where the information is.

| Data point | Pri | Source | Endpoint / ID | Notes |
|---|---|---|---|---|
| US 2Y / 5Y / 10Y / 30Y | P1 | FRED | `DGS2`, `DGS5`, `DGS10`, `DGS30` | Daily, CMT |
| **US 2s10s spread** | P1 | FRED | `T10Y2Y` | Pre-computed, don't calculate it |
| US 3m10y spread | P2 | FRED | `T10Y3M` | Better recession signal than 2s10s per Fed research |
| US 10Y real yield (TIPS) | P2 | FRED | `DFII10` | Key driver for gold and crypto |
| SOFR | P2 | NY Fed | `/api/rates/secured/sofr/last/1.json` | Also FRED `SOFR` |
| **GoC 2Y / 5Y / 10Y / long** | P1 | BoC Valet | `/observations/group/bond_yields_benchmark/json` ✅ verified | Series: `BD.CDN.2YR.DQ.YLD`, `BD.CDN.5YR.DQ.YLD`, `BD.CDN.10YR.DQ.YLD`, `BD.CDN.LONG.DQ.YLD` |
| **GoC 5Y** (mortgage-relevant) | P1 | same | `BD.CDN.5YR.DQ.YLD` | Sets Canadian fixed mortgage rates — directly relevant to your properties |
| **CORRA** | P1 | BoC Valet | series `AVG.INTWO` ⚠️ verify — check group `corra` | Canada's risk-free rate |
| Canada 2s10s | P2 | Derived | `10YR − 2YR` from above | |
| **US–Canada 2Y spread** | P1 | Derived | `DGS2 − BD.CDN.2YR.DQ.YLD` | Single biggest driver of USD/CAD. Put this on the front page |
| GoC Real Return Bond yield | P3 | BoC Valet | `BD.CDN.RRB.DQ.YLD` | |
| US 30yr mortgage rate | P3 | FRED | `MORTGAGE30US` | |

---

## 5. Growth & Activity

| Data point | Pri | Source | Endpoint / ID | Notes |
|---|---|---|---|---|
| US real GDP (level) | P1 | FRED | `GDPC1` | Quarterly |
| US real GDP (% chg SAAR) | P1 | FRED | `A191RL1Q225SBEA` | The headline number people quote |
| **Atlanta Fed GDPNow** | P1 | FRED | `GDPNOW` | Real-time nowcast — fills the gap between quarterly prints. Very high value-per-line-of-code |
| Canada GDP monthly | P1 | StatCan | Table `36-10-0434-01` ⚠️ verify | Canada publishes monthly GDP — unusual and useful |
| Canada GDP quarterly | P1 | StatCan | Table `36-10-0104-01` ⚠️ verify | |
| **Canada GDP per capita** | P2 | Derived | GDP ÷ population (Table `17-10-0009-01`) | The divergence vs headline GDP is the entire "technical growth, actual recession" story. Nobody else displays this |
| US retail sales | P2 | FRED | `RSAFS` | |
| US industrial production | P2 | FRED | `INDPRO` | |
| US consumer sentiment | P2 | FRED | `UMCSENT` | |
| **Chicago Fed NFCI** | P2 | FRED | `NFCI` | Broad financial conditions, weekly |
| Philly Fed mfg survey | P3 | FRED | `GACDISA066MSFRBPHI` | Free PMI substitute ↓ |
| Empire State mfg | P3 | FRED | `GACDFNA066MNFRBNY` ⚠️ verify | |
| Canada Ivey PMI | P3 | Ivey (scrape) | `iveypmi.uwo.ca` | |
| Building permits (CA) | P3 | StatCan | Table `34-10-0066-01` ⚠️ verify | |
| US housing starts | P3 | FRED | `HOUST` | |
| Case-Shiller HPI | P3 | FRED | `CSUSHPINSA` | |

> ⚠️ **ISM PMI is not freely available.** ISM pulled its data from FRED and licenses it commercially. S&P Global PMI is also paywalled. Use the regional Fed surveys above (Philly, Empire, Richmond, Dallas, KC) as free substitutes — they lead ISM reasonably well, and you can average them into a composite.

---

## 6. Labour

| Data point | Pri | Source | Endpoint / ID | Notes |
|---|---|---|---|---|
| US unemployment rate | P1 | FRED | `UNRATE` | |
| US nonfarm payrolls | P1 | FRED | `PAYEMS` | Show MoM change, not level |
| **US initial jobless claims** | P1 | FRED | `ICSA` | **Weekly** — fastest-moving labour indicator you'll get. High signal between monthly prints |
| US continuing claims | P2 | FRED | `CCSA` | |
| US average hourly earnings | P2 | FRED | `CES0500000003` | Wage inflation |
| JOLTS job openings | P2 | FRED | `JTSJOL` | Openings-to-unemployed ratio is the Fed's labour-tightness gauge |
| US labour force participation | P3 | FRED | `CIVPART` | |
| Canada unemployment rate | P1 | StatCan | Table `14-10-0287-01` ⚠️ verify vector | LFS, monthly |
| Canada employment change | P1 | StatCan | same table | |
| Canada wage growth | P2 | StatCan | Table `14-10-0063-01` ⚠️ verify | BoC watches this closely |

---

## 7. Liquidity & the Fed Balance Sheet

Your original list had "Fed balance sheet," which alone is misleading. The number that actually drives risk assets is net liquidity.

```
Net Liquidity = WALCL − WTREGEN − RRPONTSYD
```

| Data point | Pri | Source | Endpoint / ID | Notes |
|---|---|---|---|---|
| Fed total assets | P1 | FRED | `WALCL` | **Weekly, Wednesdays** — mismatched frequency with the daily components below. Forward-fill |
| **Treasury General Account** | P1 | Treasury Fiscal Data | `/v1/accounting/dts/operating_cash_balance` | Daily. Also FRED `WTREGEN` (weekly) — the Treasury API is fresher |
| **Overnight Reverse Repo** | P1 | NY Fed | `/api/rp/reverserepo/propositions/search.json` | Daily. Also FRED `RRPONTSYD` |
| **Net liquidity** | P1 | Derived | formula above | Plot as a line against BTC and SPX. This is one of the most useful charts you can build |
| Bank reserve balances | P2 | FRED | `WRESBAL` | Watch for the "reserve scarcity" threshold |
| US M2 | P2 | FRED | `M2SL` | |
| **Global M2** | P2 | Derived / TradingView | Sum of US + EZ + China + Japan M2, USD-converted | Tends to lead BTC by ~10–12 weeks. Buildable from FRED + ECB SDW + BOJ, but fiddly. TradingView's `GLOBAL M2` is the shortcut |
| Fed QT runoff pace | P3 | Derived | WALCL week-over-week Δ | |

---

## 8. Credit & Risk / Stress

| Data point | Pri | Source | Endpoint / ID | Notes |
|---|---|---|---|---|
| VIX | P1 | FRED | `VIXCLS` | EOD. For intraday use Yahoo `^VIX` |
| **VIX term structure** | P2 | Derived | `VIX9D / VIXCLS` or `VIX3M / VIX` (`VXVCLS`) | Backwardation (>1) is the actual stress signal. Far more informative than the VIX level |
| **High Yield OAS** | P1 | FRED | `BAMLH0A0HYM2` | **If you add only one risk indicator, make it this.** Earlier and cleaner warning than VIX |
| Investment Grade OAS | P2 | FRED | `BAMLC0A0CM` | |
| St. Louis Fed Financial Stress | P3 | FRED | `STLFSI4` | |
| MOVE index (bond vol) | P3 | — | Not free | ICE licenses it. Skip or proxy with `^MOVE` on Yahoo |

---

## 9. Markets — Equities, Commodities, FX

| Data point | Pri | Source | Endpoint / ID | Notes |
|---|---|---|---|---|
| S&P 500 | P1 | FRED `SP500` / Stooq `^spx` | | FRED is EOD + only 10yr history |
| Nasdaq Composite | P1 | FRED `NASDAQCOM` / Stooq `^ndq` | | |
| Dow | P1 | FRED `DJIA` / Stooq `^dji` | | |
| **TSX Composite** | P1 | Stooq `^tsx` / Yahoo `^GSPTSE` | | **Missing from your original list.** Half your focus is Canada |
| Russell 2000 | P2 | Stooq `^rut` | | Domestic-economy proxy; the small-cap/large-cap ratio is a useful risk gauge |
| WTI crude | P1 | FRED | `DCOILWTICO` | ~2–3 day lag. Stooq `cl.f` for fresher |
| Brent | P2 | FRED | `DCOILBRENTEU` | |
| **WCS–WTI differential** | P2 | Derived | WCS from Alberta gov / GX; WTI from FRED | The Canadian oil discount. Real CAD driver, and almost nobody displays it |
| Gold | P1 | Stooq `xauusd` / Yahoo `GC=F` | | FRED's gold series was discontinued. `metals.dev` has a free tier as backup |
| Silver | P3 | Stooq `xagusd` | | |
| Copper | P2 | Stooq `hg.f` | | Growth bellwether |
| **USD/CAD** | P1 | BoC Valet | `/observations/FXUSDCAD/json` ✅ | Official BoC noon-equivalent rate. `FXCADUSD` for the inverse |
| **DXY (dollar index)** | P1 | FRED | `DTWEXBGS` (broad) | Matters more for global risk appetite than USD/CAD alone |
| Citi Economic Surprise Index | P2 | — | Not free | Proxy: build your own from actual-vs-consensus in your calendar table. Genuinely worth doing |

---

## 10. Crypto

Your original list was all price and sentiment. The **flow** data is what actually explains moves in this cycle.

### Price & structure (you had these)

| Data point | Pri | Source | Endpoint |
|---|---|---|---|
| BTC / ETH price | P1 | CoinGecko | `/simple/price?ids=bitcoin,ethereum&vs_currencies=usd,cad&include_24hr_change=true` |
| Total crypto market cap | P1 | CoinGecko | `/global` → `data.total_market_cap.usd` |
| BTC dominance | P1 | CoinGecko | `/global` → `data.market_cap_percentage.btc` |
| Fear & Greed Index | P1 | Alternative.me | `https://api.alternative.me/fng/?limit=30` |
| **Altseason Index** | P2 | Compute it | CoinGecko `/coins/markets?order=market_cap_desc&per_page=50&price_change_percentage=90d` | The standard definition is "% of top 50 coins outperforming BTC over 90d." Blockchaincenter has no API — just calculate it. ~20 lines |

### Flows & positioning (the gap)

| Data point | Pri | Source | Endpoint / access |
|---|---|---|---|
| **Spot BTC/ETH ETF net flows** | P1 | Farside Investors | `farside.co.uk/btc/` — HTML table, scrape daily | **The dominant marginal buyer since 2024.** Single most explanatory crypto data point right now. SoSoValue is the alternative source |
| **Stablecoin total supply** | P1 | DefiLlama | `https://stablecoins.llama.fi/stablecoins?includePrices=true` | Best dry-powder proxy. Track the **rate of change**, not the level |
| Perp funding rates | P2 | CoinGlass free tier / Binance | CoinGlass `/api/futures/fundingRate`; or Binance `/fapi/v1/premiumIndex` (free, no key) | Binance direct is more reliable free |
| Open interest | P2 | Binance | `/futures/data/openInterestHist` (free) | |
| Liquidations | P2 | CoinGlass | Free tier, key required | Rate-limited hard on free |
| **Coinbase premium** | P2 | Derived | Coinbase `/products/BTC-USD/ticker` vs Binance `/api/v3/ticker/price?symbol=BTCUSDT` | US vs offshore buying pressure. Both APIs free and keyless |
| Exchange net flows | P3 | CryptoQuant / Glassnode | Mostly paid | Limited free tiers |
| MVRV Z-score | P2 | bitcoin-data.com | `https://bitcoin-data.com/v1/mvrv-zscore` (free) | Cycle-position gauge |
| NUPL | P3 | bitcoin-data.com | `/v1/nupl` ⚠️ verify | |
| **BTC–Nasdaq 30d correlation** | P2 | Derived | Rolling corr of daily returns | Tells you whether crypto is trading as a macro asset or on its own. Cheap to compute, surprisingly useful |
| Total DeFi TVL | P3 | DefiLlama | `https://api.llama.fi/v2/historicalChainTvl` | |

---

## 11. Canada-Specific (things most dashboards skip)

Half your focus is Canada, and this is where you can build something that doesn't exist elsewhere.

| Data point | Pri | Source | Notes |
|---|---|---|---|
| **GoC 5Y yield** | P1 | BoC Valet `BD.CDN.5YR.DQ.YLD` | Sets fixed mortgage rates. Relevant to your rentals |
| **US–CA 2Y spread** | P1 | Derived | Primary USD/CAD driver |
| CPI-trim / CPI-median | P1 | BoC Valet | BoC's actual core measures |
| GDP per capita vs headline | P2 | StatCan derived | The story headline GDP hides |
| Household debt-to-income | P2 | StatCan Table `36-10-0664-01` ⚠️ verify | Quarterly |
| Mortgage renewal volumes | P2 | BoC / CMHC reports | Not an API — periodic PDF. The renewal wall is a real 2025–26 macro variable |
| Population / immigration | P2 | StatCan Table `17-10-0009-01` ⚠️ verify | One of the biggest Canadian macro swing factors recently |
| WCS–WTI differential | P2 | Alberta Energy / GX | |
| CREA Home Price Index | P2 | CREA (scrape) | `creastats.crea.ca` — no API |
| Housing starts | P3 | CMHC / StatCan | |
| USMCA review timeline | P2 | Manual | Hardcode key dates; tariff deadlines move markets |
| NL-specific housing | P3 | CREA / NLAR | You'll care about this one personally |

---

## 12. Economic Calendar

This is the piece with no clean free equivalent to TradingEconomics. Assemble it from official release calendars.

| Component | Source | Endpoint |
|---|---|---|
| **US release dates (all FRED series)** | FRED Releases API | `/fred/releases/dates?realtime_start=...` — **this is the trick.** FRED knows when every series it carries is next published |
| BLS release schedule | BLS | `bls.gov/schedule/news_release/` — ICS + HTML |
| BEA release schedule | BEA | `bea.gov/news/schedule` |
| Census (retail, housing) | Census | `census.gov/economic-indicators/` |
| **StatCan release calendar** | StatCan | `www150.statcan.gc.ca/n1/dai-quo/index-eng.htm`; or `getChangedCubeList` for what dropped today |
| FOMC dates | Fed | `federalreserve.gov/monetarypolicy/fomccalendars.htm` |
| BoC dates | BoC | `bankofcanada.ca/press/upcoming-events/` |
| Treasury auctions | TreasuryDirect | `treasurydirect.gov/TA_WS/securities/auctioned?format=json` (free) |
| Quarterly refunding | Treasury | Announced early Feb/May/Aug/Nov |
| OPEX / quad witching | Computed | 3rd Friday monthly; quad = Mar/Jun/Sep/Dec |
| Earnings anchors | FMP / Finnhub free tier | Just the mega-caps, not the full calendar |

**Critical display detail:** show **Previous / Consensus / Actual** side by side, and compute the surprise. The number alone tells you nothing — the deviation from consensus is what moves markets. Consensus is the hard part to source free; Finnhub's economic calendar free tier is the most likely candidate, but verify it's still on the free plan before you design around it.

---

## 13. Design Recommendations

**Normalize everything.** Raw levels are unreadable at a glance. Display each indicator as a **z-score or percentile rank vs. its own 10-year history**, with the raw value secondary.

> "Unemployment: 4.2%" → means nothing
> "Unemployment: 68th pct of 10yr range, ↑ 3 months" → instantly readable

**Add a "what changed" strip at the top.** Biggest 1-day movers across every tracked series, ranked by z-score change. This becomes the thing you actually look at every morning.

**Build your own surprise index.** Once you're storing actual-vs-consensus in the calendar table, a rolling 3-month standardized average gives you a free Citi Economic Surprise Index equivalent, per country. This is a real edge — very few free dashboards have it.

---

## 14. Gotchas

| Issue | Impact |
|---|---|
| **TradingEconomics ToS** | Their API is expensive and scraping violates ToS. Don't design around it. Everything above replaces it |
| **CoinGecko free = 10k calls/month** | ~13/hour if spread evenly. Cache aggressively — 60s TTL on prices, 5min on `/global`. Batch coin IDs into one `/simple/price` call |
| **FRED release lag** | `SP500`, `DCOILWTICO`, etc. are EOD with a 1–3 day lag. Fine for macro, useless for a live ticker. Use Stooq or Yahoo for anything that needs to feel live |
| **Yahoo Finance is unofficial** | `query1.finance.yahoo.com` works and is widely used but is undocumented and against ToS. Fine for personal use; don't build anything public on it. Stooq is the safer default |
| **WALCL is weekly** | Net liquidity mixes weekly (WALCL) and daily (TGA, RRP) series. Decide explicitly: forward-fill WALCL, or downsample everything to weekly |
| **StatCan vectors ≠ table numbers** | You resolve table + coordinate → vector ID once, then query by vector. Do this discovery step manually and hardcode the vectors |
| **Revisions** | GDP, payrolls, and Canadian GDP all get revised. If you're storing history, store the vintage or you'll silently corrupt your own backtests. FRED's ALFRED handles this if you care |
| **Timezones** | BoC publishes bond yields 09:30–10:00 ET, interest rates 12:15–12:30 ET, FX 16:30 ET. Your "today's data" logic needs to know this |
| **Farside is a scrape** | HTML table, no API, no SLA. It will break eventually. Cache the last good response and fail gracefully |

---

## 15. Suggested Build Order

**Phase 1 — Core (all P1, ~one weekend)**
FRED + BoC Valet + CoinGecko. Rates, curve, CPI/PCE, unemployment, GDP, VIX, HY OAS, indices, USD/CAD, BTC/ETH/dominance/mcap/F&G. This alone beats most free dashboards.

**Phase 2 — Calendar**
FOMC/BoC dates, FRED releases API, StatCan calendar. Prior/consensus/actual layout.

**Phase 3 — The differentiators**
Net liquidity, FedWatch (buy or build), BoC implied probabilities, ETF flows, stablecoin supply, US–CA 2Y spread.

**Phase 4 — Polish**
Z-score normalization, "what changed" strip, your own surprise index, Canada-specific panel.

---

## Appendix: Endpoint Patterns

```
# FRED
https://api.stlouisfed.org/fred/series/observations
  ?series_id=DGS10&api_key=KEY&file_type=json&sort_order=desc&limit=1

# FRED — upcoming release dates
https://api.stlouisfed.org/fred/releases/dates
  ?api_key=KEY&file_type=json&include_release_dates_with_no_data=true

# BoC Valet — single series
https://www.bankofcanada.ca/valet/observations/FXUSDCAD/json?recent=1

# BoC Valet — whole group in one call
https://www.bankofcanada.ca/valet/observations/group/bond_yields_benchmark/json?recent=1

# StatCan WDS (POST, JSON body)
POST https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods
[{"vectorId":41690973,"latestN":3}]

# CoinGecko
https://api.coingecko.com/api/v3/simple/price
  ?ids=bitcoin,ethereum&vs_currencies=usd,cad&include_24hr_change=true
https://api.coingecko.com/api/v3/global

# Alternative.me Fear & Greed
https://api.alternative.me/fng/?limit=30&format=json

# DefiLlama stablecoins
https://stablecoins.llama.fi/stablecoins?includePrices=true

# NY Fed — RRP
https://markets.newyorkfed.org/api/rp/reverserepo/propositions/search.json
  ?startDate=2026-01-01&endDate=2026-07-27

# Treasury — TGA daily balance
https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance
  ?filter=record_date:gte:2026-01-01&sort=-record_date

# Binance — funding rate (free, keyless)
https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT

# Stooq — EOD CSV
https://stooq.com/q/d/l/?s=^spx&i=d
https://stooq.com/q/d/l/?s=^tsx&i=d
```
