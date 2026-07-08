# portfolio-db

多帳戶、多用戶、跨市場（台 / 美 / 新加坡）的家族 portfolio 管理 CLI，支援即時報價、損益計算、現金部位、計畫下單，並涵蓋**法律名義人 vs 經濟所有人**雙層所有權結構（家族借名 / 信託情境必備）。

## Quickstart

```bash
# 安裝依賴
pip install -r requirements.txt

# 初始化 DB（per-OS app data dir、不在 cloud sync 範圍）
python -m portfoliodb init

# 建立用戶
python -m portfoliodb user add ian "張益堅"
python -m portfoliodb user add dad "張正彥"

# 建帳戶（legal owner = 戶頭名義；--economic-owner = 實際擁有人、不指定預設同 legal）
python -m portfoliodb account add ian "Firstrade 49871084" Firstrade US
python -m portfoliodb account add dad "富邦證券 板橋 0394434" Fubon TW --economic-owner ian

# 灌持股 / 現金
python -m portfoliodb holding add 1 NVDA 100 95.64
python -m portfoliodb cash set 1 USD 5000

# 家族 portfolio 全展開（8 維 aggregation + flat positions）
python -m portfoliodb summary breakdown
```

## Tech Stack

- **Python 3.14**
- **SQLite**：檔案型、存在 per-OS app data dir、避免 cloud sync 損壞 WAL
- **click**：CLI framework
- **rich**：終端機表格 / 顏色
- **yfinance**：Yahoo Finance 即時股價 + 匯率（免 API key）

## DB 與憑證位置

跨平台分流（`db._app_dir()`）：

| 平台 | App data dir |
|---|---|
| macOS | `~/Library/Application Support/PortfolioDB/` |
| Windows | `~/AppData/Local/PortfolioDB/` |
| Linux | `~/.local/share/PortfolioDB/` |

DB（`portfolio.db`）+ 券商 API 憑證（`credentials.json`）都在這個 dir、**不入 git、不雲端同步**。

## 主要 CLI 指令

```
init                              初始化 DB
user     add / list               用戶管理
account  add / list               帳戶管理（含 --economic-owner override）
holding  add / list / remove      持股管理
tx       buy / sell / list        交易紀錄（雙重記帳）
cash     set / deposit / withdraw / list  現金管理（11 幣別：TWD/USD/SGD/HKD/JPY/EUR/CNY/GBP/AUD/NZD/ZAR）
order    add / list / execute / cancel    計畫下單
price    get / batch              Yahoo Finance 即時報價
summary  account / user / all / breakdown  投資組合摘要
fx       rate / rates             匯率
sync     sinopac / fubon / firstrade / scb / credentials  券商同步（API + CSV）
rank     add / list / show        個股排名快照（PEG / Kelly f* / 15分模型，含 method_version 版號追蹤）
```

詳細指令參數見 `system_map.md` 或 `python -m portfoliodb <cmd> --help`。

## Ticker 規則

- 台股上市：`2330.TW`（台積電）
- 台股上櫃：`8299.TWO`（群聯）
- 美股：純代號 `NVDA / GOOG / TSM`
- 新加坡：`D05.SI`（DBS）

`order add` 在 TW 帳戶下會自動補 `.TW` 給 2/3 字頭裸數字（如 `2330` → `2330.TW`）；6/8/9 字頭因可能上市可能上櫃、要 explicit 寫 `.TW` 或 `.TWO`。

## Ticker / Issuer 兩層身份

- **Instrument 層**（security）：`2330.TW`、`TSM` 是兩個不同 instrument — ADR 與普通股的市場 / 幣別 / 價格 / 交易單位 / P&L 全不同、order / position / P&L / execution 一律走這層
- **Company 層**（issuer）：兩者同屬 `TSMC`、僅 issuer aggregation 視圖使用（如未來 `summary breakdown by issuer`）
- 兩層 schema：`companies` / `instruments` / `company_aliases`、由 `portfoliodb/migrations/m001_canonical_ticker_and_instruments.py` seed
- 一次性 backfill：`python -m portfoliodb.migrations.m001_canonical_ticker_and_instruments`（dry-run）+ `--apply`、idempotent 可重跑、log 在 `<APP_DIR>/migration_001.log`

## Migrations

**portfolio-db 是 per-machine DB**（每台機器各自的本機檔案、不隨 git pull 自動同步 schema）。跨機器（NB / Air）pull 到新版 code 後、如果 code 引入了 schema 變動（新 constraint、新欄位），**要各自手動跑一次對應的 migration**：

```
python -m portfoliodb.migrations.m001_canonical_ticker_and_instruments --apply   # ticker canonical + instruments/companies
python -m portfoliodb.migrations.m002_rankings_schema_hardening --apply          # rankings 表 UNIQUE + method_version
```

都是 dry-run 預設、`--apply` 才真寫、idempotent 可重跑（已是最終形狀會直接印「nothing to do」）。跑 `--apply` 前建議先 `python -m portfoliodb backup`。

## Tests

```
pytest tests/
```

`tests/conftest.py` 用 tmp_db fixture 隔離正式 DB、66 tests 覆蓋 canonical / migration / ranking / review aggregation / yfinance noise capture。

## 設計原則

- **Single-machine app**：DB 留 master 機、跨機器讀走 Tailscale / API、不靠 cloud sync DB 檔
- **資料攝取務實主義**：API > CSV > 截圖 vision（後者是台灣券商主路徑、因 CSV 匱乏 + API 申請門檻）
- **兩層所有權**：legal owner ⊥ economic owner；報稅 / 對帳走 legal、portfolio 統計走 economic
- **加權平均成本法**：台灣投資人標準
- **雙重記帳**：交易同時更新持股 + 現金、原子操作
- **快取**：股價 15 分、匯率 60 分

## 文件

- [`system_map.md`](system_map.md) — 系統現狀快照（schema / CLI / 設計細節）
- [`log_chronological.md`](log_chronological.md) — 開發決策時序紀錄
- [`CLAUDE.md`](CLAUDE.md) — AI 協作規則 + session 流程
