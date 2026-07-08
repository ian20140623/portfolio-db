# 帳務管理系統 — 功能說明
*last updated: 2026-05-26*

> **給未來 AI 的說明**
> 共用指引見 [`../shared/LOG_GUIDE.md`](../shared/LOG_GUIDE.md)
>
> **本專案補充：**
> - 暫無 ^ck-c536f7-0

---

## 系統目標
多帳戶、多用戶的股票與現金統合管理系統，涵蓋台灣、美國、新加坡三個市場，支援即時報價、損益計算、計畫下單，並整合券商 API 與 CSV 匯入實現自動化同步。 ^ck-52059c-2

---

## 技術架構
*last updated: 2026-02-23*

| 技術 | 角色 |
|------|------|
| Python 3.14 | 主程式語言 |
| SQLite | 資料庫（檔案型，存在 AppData，不隨 OneDrive 同步） |
| click | CLI 框架 |
| rich | 終端機美化輸出（表格、顏色） |
| yfinance | Yahoo Finance 即時股價與匯率（免費、不需 API key） |
^ck-62e86e-4 ^ck-146a5d-4

---

## 檔案路徑
*last updated: 2026-05-24*

DB / credentials 走 per-OS app-data dir（`db.APP_DIR`）、跨平台分流、**single-machine app**（DB 留 master 機、不靠 cloud sync DB 檔避免 SQLite WAL 衝突）：

| 平台 | App data dir |
|------|------|
| macOS | `~/Library/Application Support/PortfolioDB/` |
| Windows | `~/AppData/Local/PortfolioDB/` |
| Linux | `~/.local/share/PortfolioDB/` |

| 檔案 | 用途 |
|------|------|
| `<APP_DIR>/portfolio.db` | SQLite 資料庫（不在雲端同步資料夾） |
| `<APP_DIR>/credentials.json` | 券商 API 憑證（不進版控） |

當前 master：Mac mini（24/7 開機、跟 ks host 同台）。 ^ck-485fad-6 ^ck-3d61b8-6

---

## 資料庫結構
*last updated: 2026-07-08*

13 張資料表：

| 資料表 | 用途 |
|--------|------|
| `users` | 用戶（username, display_name） |
| `accounts` | 帳戶（綁定**法律名義人 + 經濟所有人**雙欄、含券商、市場、幣別） |
| `holdings` | 持股現況（每帳戶每股票一筆，含均價） |
| `transactions` | 交易紀錄（不可變動的買賣記錄） |
| `cash_positions` | 現金部位（每帳戶每幣別一筆、支援多幣別） |
| `cash_transactions` | 現金異動紀錄（存提款、股息、利息） |
| `planned_orders` | 計畫下單（PENDING → EXECUTED / CANCELLED） |
| `exchange_rates` | 匯率快取（1 小時 TTL） |
| `price_cache` | 股價快取（15 分鐘 TTL） |
| `companies` | **Issuer 層**（company_id PK e.g. "TSMC"、display_name、notes）|
| `instruments` | **Security 層**（instrument_id PK、ticker UNIQUE canonical key、market、currency、company_id nullable FK、security_type COMMON/ADR/ETF）|
| `company_aliases` | Issuer 別名（alias、company_id FK、kind name_zh/name_en/abbr）|
| `rankings` | 個股排名快照（ticker/method/method_version/score_date/headline_score/weight_pct/source/notes，2026-07-08 加入）|

關鍵設計：
- **兩層所有權**：`accounts.legal_owner_id`（戶頭掛誰名下）+ `accounts.economic_owner_id`（錢實際是誰的）。「戶頭借名」場景必備 — 例如父親名下實際是兒子的資產
- **兩層 ticker identity**（2026-05-26 加入）：
  - **Instrument 層**（security）= `instruments.ticker` canonical key、order / position / price / P&L / execution 走這層。ADR 與普通股保持獨立（如 `TSMC_TW_COMMON` ticker=2330.TW vs `TSMC_US_ADR` ticker=TSM）
  - **Company 層**（issuer）= `instruments.company_id` 同一個、僅 `summary breakdown by issuer` 類 aggregation 使用
  - `holdings` / `transactions` / `planned_orders` / `price_cache` 的 `ticker` column 維持 TEXT、不改 FK、用 canonical 字串 JOIN
  - 唯一 normalization 來源：`portfoliodb/utils/ticker.py:canonical_ticker(raw, market_hint)` — 已有 suffix 不動、TW + 2/3 字頭裸數字補 .TW、6/8/9 字頭裸數字標 unresolved（不猜上市/上櫃）
  - Migration 001（`portfoliodb/migrations/m001_canonical_ticker_and_instruments.py`）支援 dry-run + apply + idempotent、audit trail 到 `<APP_DIR>/migration_001.log`
- 交易紀錄採 **雙重記帳**：一筆 BUY 同時更新持股（shares 增加、均價重算）和現金（扣款）
- 均價計算採 **加權平均成本法**
- 計畫下單執行後自動連結到實際交易紀錄（`linked_transaction_id`）
- `get_user_summary(username)` 走 **economic owner**（看「真實 portfolio」、不看名義人）
- **個股排名不綁單一方法論**（2026-07-08）：`rankings` 表存快照（ticker/method/score_date/headline_score/…），不是計算引擎——PEG（Lynch 式、分數越低越好）、Kelly f*（越高越好）、V1 15 分模型（掌握度+估值吸引力+長期品質、越高越好）三種方法論的排名方向定義在 `utils/constants.RANKING_DIRECTION`（顯式 dict，非集合排除法——2026-07-08 Spock review 後從 `RANKING_LOWER_IS_BETTER` 改的，避免新增 method 忘記登記時靜默用錯方向）。DB 只負責存 + 依方向排序、不重算分數（分數怎麼算見 `../peg` skill + Dropbox-synced `scratch/20260527-投組初步想法.md`）
- **`rankings.method_version` 追蹤方法論演進**（2026-07-08）：Sir 的排名框架還在演進中（不是凍結規格）——例如 Kelly 在 7/6 session 引入「G-trajectory 當 b 值 proxy」的算法，還沒寫回 Dropbox-synced 主檔 `scratch/20260527-投組初步想法.md` 第九節。`method_version` 是自由文字欄位（非嚴格 semver，因為這是活文件不是程式碼發布），讓同一 method 底下不同規則版本算出來的分數不會被誤當同一把尺比較。目前回填：PEG 13 筆中的 7 筆標 `V1`（peg skill 方法論本身沒改版）、Kelly 6 筆標 `V1.1`（反映 7/6 的 G-trajectory 延伸，非主檔原文）——**這個版號是 JV 的判斷、不是 Sir 明訂，主檔本身尚未同步更新這個 section，值得之後回頭對齊** ^ck-d59a01-8

---

## 程式碼結構
*last updated: 2026-05-26*

```
portfoliodb/
  cli.py                    ← CLI 入口（所有 click 指令）
  db.py                     ← SQLite 連線與 schema 初始化
  backup.py                 ← off-machine cold backup（online-backup API → Dropbox、輪替 + integrity check + restore）
  models.py                 ← dataclass 定義（User, Account, Holding, ...）
  __main__.py               ← python -m portfoliodb 入口

  services/
    user_service.py          ← 用戶 CRUD
    account_service.py       ← 帳戶 CRUD（含市場/幣別驗證）
    holding_service.py       ← 持股管理（均價計算）
    transaction_service.py   ← 交易紀錄（雙重記帳核心）
    cash_service.py          ← 現金部位管理
    order_service.py         ← 計畫下單 + review_orders 回顧
    price_service.py         ← Yahoo Finance 報價 + 快取 + stderr noise capture
    fx_service.py            ← 匯率抓取與換算
    portfolio_service.py     ← 彙總摘要與損益計算 + family breakdown
    sync_service.py          ← 券商同步與 CSV 匯入的協調層
    ranking_service.py       ← 個股排名快照（PEG/Kelly/15分模型）存取，不計算分數

  brokers/
    config.py                ← 憑證管理（讀寫 credentials.json）
    sinopac_broker.py        ← 永豐金 Shioaji API 整合
    fubon_broker.py          ← 富邦 Neo API 整合

  importers/
    firstrade_csv.py         ← Firstrade CSV 解析器
    scb_csv.py               ← 渣打新加坡 CSV 解析器

  migrations/                ← 一次性 DB 升級腳本（dry-run + apply + idempotent）
    m001_canonical_ticker_and_instruments.py
                             ← canonical ticker backfill + companies / instruments / aliases seed
    m002_rankings_schema_hardening.py
                             ← rankings 表補 UNIQUE(ticker,method,score_date) + method_version 欄位（dedup 保留最新一筆）——**每台機器各自的本機 DB 都要手動跑一次**（single-machine DB、不隨 git pull 自動套用）

  utils/
    constants.py             ← 市場、幣別、稅率定義
    ticker.py                ← canonical_ticker / detect_market / resolve_instrument / resolve_company
                              （**單一 normalization 來源**）
    formatting.py            ← 金額、損益、百分比格式化

tests/                       ← pytest（tmp_db fixture 隔離正式 DB）
  conftest.py
  test_ticker_canonical.py   ← 11 test、canonical_ticker 規則
  test_migration_001.py      ← 8 test、backfill + idempotent + identity
  test_migration_002.py      ← 11 test、rankings 表補 UNIQUE/method_version + dedup + idempotent
  test_review_orders.py      ← 3 test、canonical aggregation + ADR/普通股不合併
  test_price_warnings.py     ← 3 test、yfinance noise capture
  test_ranking.py            ← 20 test、ranking 方向排序 + canonicalization + 歷史查詢 + method_version
``` ^ck-c47767-10

---

## 資料攝取（broker 整合）
*last updated: 2026-05-24*

實務上 3 條路徑、依券商現有 API 可達性決定：

| 券商 | 市場 | 路徑 | 狀態 |
|------|------|------|------|
| 永豐金 (SinoPac) | TW + 美股複委託 | (a) Shioaji API（程式碼就緒、未申請）／(b) **截圖 + vision 辨識** | 截圖路線實證可用 |
| 富邦 (Fubon) | TW | (a) Fubon Neo SDK（程式碼就緒、未申請）／(b) **截圖 + vision 辨識** | 截圖路線實證可用 |
| Firstrade | US | (a) CSV 匯入（程式碼就緒）／(b) **截圖 + vision 辨識** | 截圖路線實證可用 |
| 渣打新加坡 (SCB) | SG + 美股 | (a) CSV 匯入（程式碼就緒）／(b) **截圖 + vision 辨識** | 截圖路線實證可用 |

**截圖 + vision 路徑**（事實上的主路徑）：
- 用戶 ship app 截圖（庫存頁 + 現金頁 + 損益頁）、AI 辨識個股 / 股數 / 均價 / cash、套各家公式驗算 internal consistency、用 `account add` / `holding add` / `cash set` 灌進 DB
- 各家「庫存總市值」公式不同：永豐 = 賣出實得（毛市值 × 0.995575、扣 0.3% 證交稅 + 0.1425% 手續費）/ 富邦庫存頁 = 同上 / 富邦即時庫存頁 = 毛市值 / Firstrade = 純市值 / SCB = USD 純市值 + SGD 換算 view
- 截圖只給「股數+損益」時、反推均價公式：`均價 = 現價 × tax_factor − 損益/股數`（永豐/富邦套 0.995575、Firstrade/SCB 套 1.0）
- Cross-source price check：yfinance + cnyes 鉅亨網雙源驗證 ^ck-2517d3-12

---

## CLI 指令總覽
*last updated: 2026-05-26*

```
python -m portfoliodb <command>

init                              初始化資料庫
user     add / list               用戶管理
account  add / list               帳戶管理（含 --economic-owner override）
holding  add / list / remove      持股管理（手動匯入）
tx       buy / sell / list        交易紀錄（自動更新持股+現金）
cash     set / deposit / withdraw / list  現金管理（支援 11 幣別）
order    add / list / execute / cancel / review    計畫下單 + 回顧
price    get / batch              Yahoo Finance 即時報價
summary  account / user / all / breakdown  投資組合摘要
fx       rate / rates             匯率查詢
sync     sinopac / fubon / firstrade / scb / credentials  自動化同步
rank     add / list / show        個股排名快照（PEG / Kelly f* / 15分模型）
```

**`order add` 新 syntax**（signed shorthand、最小 friction）：
- `order add <account_id> <ticker> +1000 --price 1180 --reason "..."` — `+N` = BUY
- `order add <account_id> <ticker> -500 --price 5400 --reason "..."` — `-N` = SELL
- Fallback：`order add <account_id> <ticker> buy 1000` 或 `sell 500`（給 shell 吃掉 leading dash 的情境）
- Ticker auto-suffix：TW market account 內、`2330` 自動變 `2330.TW`、上櫃要 explicit 寫 `8299.TWO`
- Reason 是 optional free text、不強制 articulation（per friction-minimization doctrine）

**`order review --since N`** retrospective stats：
- Counts（total / PENDING / EXECUTED / CANCELLED）
- Execution lag（create → execute 天數）
- 反覆出現的個股（心裡惦記的 ticker）
- 未執行 plan + 當前股價對照（猶豫沒下手後續走勢）

**`summary breakdown`**（家族 portfolio 全展開）：
- 8 維 aggregation：by 經濟所有人 / 法律名義人 / 資產類別 / 幣別 / 市場 / 券商 / 帳戶類型 / 個股 concentration
- **個股 concentration 加 `intent` column**：JOIN PENDING orders、annotation 形式 `→加 500 @1180` / `→減 200 @5400`、沒 plan 的 cell 空白（zero visual cost）
- Flat positions：每個 holding × account + 每個 cash position 都單獨一行、按 base-currency 市值排序
- 預設 base = TWD、用 `--currency USD` 切換 ^ck-897bce-14

**`rank add <ticker> <peg|kelly|fifteen_point> <headline_score>`**（2026-07-08 加入）：
- `--date`（default 今天）/ `--weight`（Kelly 常用）/ `--source`（引用出處）/ `--notes`（支撐細節，如 PEG 的 G/FwdPE、Kelly 的 G-trajectory/b）/ `--market`（裸數字 TW ticker 要補 suffix 時給 hint）/ `--framework-version`（自由文字、標這筆分數是哪個版本的方法論算出來的，如 `V1`/`V1.1`；框架還在演進中、選填但建議填）
- `rank list --method <method> --latest`：每檔最新一筆、依該 method 的「越低越好 / 越高越好」方向排序（PEG 越低越好，Kelly / 15分模型越高越好）
- `rank show <ticker>`：該檔所有方法的歷史快照，時間序
- DB 不算分數、只存 + 排序；分數怎麼算見 `../peg` skill（PEG）與 Dropbox-synced `scratch/20260527-投組初步想法.md`（15分模型 + Kelly 定位）

---

## 支援市場 + 幣別
*last updated: 2026-05-24*

**Market**（影響 account 主幣別 + ticker 偵測）：

| 市場 | 主幣別 | Yahoo Finance 格式 | 範例 |
|------|------|-------------------|------|
| 台灣 (TW) | TWD | `代碼.TW`（上市）/ `代碼.TWO`（上櫃） | 2330.TW（台積電）、8299.TWO（群聯） |
| 美國 (US) | USD | `代碼` | AAPL / NVDA / TSM(ADR) |
| 新加坡 (SG) | SGD | `代碼.SI` | D05.SI（DBS） |

**Cash 支援幣別**（11 種、`CURRENCIES` enum）：
TWD / USD / SGD / HKD / JPY / EUR / CNY / GBP / AUD / NZD / ZAR

— 一個 account 可持有多幣別 cash（例如 SCB SG account 同時持 USD 主 + HKD 零頭）。 ^ck-30750e-16 ^ck-62d63e-16

---

## 設計原則
*last updated: 2026-05-24*

- **Speculative benefit vs concrete cost**（2026-05-26 Athena framework）：portfolio-db design 對 feature decision 的 filter — **對 speculative benefit + concrete cost、default 不 hedge**（例如：mandatory commitment ritual / 4-question prompt 等「也許 protect alpha」的 friction 一律不做、因為 time 是 concrete cost、alpha protection 是 speculative）。對 concrete benefit + concrete cost、比大小決定。Time > speculative alpha 是 Sir 的真實 weighting
- **Single-machine app**：DB 留 master 機（Mac mini）、跨機器讀靠 Tailscale ssh / 之後做 API。不靠 cloud sync DB **live 檔**（SQLite + WAL 會跟 OneDrive/Dropbox/iCloud 衝突致 corruption）
- **Off-machine cold backup**（2026-06-18 加入、補 single-machine 設計缺口）：「不 live sync」≠「不備份」。`portfoliodb/backup.py` 用 SQLite online-backup API 產生**靜態一致快照**（無 WAL）→ 寫進 Dropbox `PJHub/portfolio-db/db_backups/` 當 cold copy（單向、不 live 開啟、不會 corruption）。`.tmp` → atomic rename 發布、寫後 `PRAGMA integrity_check`、輪替保留 30 份。launchd `com.portfoliodb.backup` 每日 03:30 自動跑（`scripts/install_backup_schedule.sh` 安裝）。CLI：`backup` / `backup list` / `backup restore [檔] [--force]`（restore 會先存 pre-restore 安全副本）。**起因**：2026-06-14 Mac mini 重灌、本機 AppData 的 DB + migration 快照全失、無 Time Machine 無 off-machine copy → DB 整個重建。當初只做對「不 live sync」一半、沒做「定期 cold dump」另一半
- **資料攝取務實主義**：API > CSV > 截圖 vision 三條路徑、依券商現有可達性決定。台灣券商 CSV 匱乏 + API 申請門檻高、截圖路徑成為事實上的主路徑
- **兩層所有權**：legal owner（戶頭名義）⊥ economic owner（錢實際是誰的）。報稅 / 對帳走 legal、portfolio 統計走 economic
- **憑證不進版控**：credentials.json 存 APP_DIR，不在 OneDrive 也不在 Git
- **加權平均成本法**：台灣投資人最常用，簡單且不需追蹤每筆買入批次
- **雙重記帳**：交易同時更新持股和現金，原子操作確保資料一致
- **快取避免頻繁請求**：股價 15 分鐘、匯率 1 小時 ^ck-029e2c-18
