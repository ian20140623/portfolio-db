# 帳務管理系統 — 功能說明
*last updated: 2026-05-24*

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
*last updated: 2026-05-24*

9 張資料表：

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

關鍵設計：
- **兩層所有權**：`accounts.legal_owner_id`（戶頭掛誰名下）+ `accounts.economic_owner_id`（錢實際是誰的）。「戶頭借名」場景必備 — 例如父親名下實際是兒子的資產
- 交易紀錄採 **雙重記帳**：一筆 BUY 同時更新持股（shares 增加、均價重算）和現金（扣款）
- 均價計算採 **加權平均成本法**
- 計畫下單執行後自動連結到實際交易紀錄（`linked_transaction_id`）
- `get_user_summary(username)` 走 **economic owner**（看「真實 portfolio」、不看名義人） ^ck-d59a01-8

---

## 程式碼結構
*last updated: 2026-02-23*

```
portfoliodb/
  cli.py                    ← CLI 入口（所有 click 指令）
  db.py                     ← SQLite 連線與 schema 初始化
  models.py                 ← dataclass 定義（User, Account, Holding, ...）
  __main__.py               ← python -m portfoliodb 入口

  services/
    user_service.py          ← 用戶 CRUD
    account_service.py       ← 帳戶 CRUD（含市場/幣別驗證）
    holding_service.py       ← 持股管理（均價計算）
    transaction_service.py   ← 交易紀錄（雙重記帳核心）
    cash_service.py          ← 現金部位管理
    order_service.py         ← 計畫下單
    price_service.py         ← Yahoo Finance 報價 + 快取
    fx_service.py            ← 匯率抓取與換算
    portfolio_service.py     ← 彙總摘要與損益計算
    sync_service.py          ← 券商同步與 CSV 匯入的協調層

  brokers/
    config.py                ← 憑證管理（讀寫 credentials.json）
    sinopac_broker.py        ← 永豐金 Shioaji API 整合
    fubon_broker.py          ← 富邦 Neo API 整合

  importers/
    firstrade_csv.py         ← Firstrade CSV 解析器
    scb_csv.py               ← 渣打新加坡 CSV 解析器

  utils/
    constants.py             ← 市場、幣別、稅率定義
    ticker.py                ← 股票代碼驗證與市場偵測
    formatting.py            ← 金額、損益、百分比格式化
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
*last updated: 2026-05-24*

```
python -m portfoliodb <command>

init                              初始化資料庫
user     add / list               用戶管理
account  add / list               帳戶管理（含 --economic-owner override）
holding  add / list / remove      持股管理（手動匯入）
tx       buy / sell / list        交易紀錄（自動更新持股+現金）
cash     set / deposit / withdraw / list  現金管理（支援 11 幣別）
order    add / list / execute / cancel    計畫下單
price    get / batch              Yahoo Finance 即時報價
summary  account / user / all / breakdown  投資組合摘要
fx       rate / rates             匯率查詢
sync     sinopac / fubon / firstrade / scb / credentials  自動化同步
```

**`summary breakdown`**（家族 portfolio 全展開）：
- 8 維 aggregation：by 經濟所有人 / 法律名義人 / 資產類別 / 幣別 / 市場 / 券商 / 帳戶類型 / 個股 concentration
- Flat positions：每個 holding × account + 每個 cash position 都單獨一行、按 base-currency 市值排序
- 預設 base = TWD、用 `--currency USD` 切換 ^ck-897bce-14

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

- **Single-machine app**：DB 留 master 機（Mac mini）、跨機器讀靠 Tailscale ssh / 之後做 API。不靠 cloud sync DB 檔（SQLite + WAL 會跟 OneDrive/Dropbox/iCloud 衝突致 corruption）
- **資料攝取務實主義**：API > CSV > 截圖 vision 三條路徑、依券商現有可達性決定。台灣券商 CSV 匱乏 + API 申請門檻高、截圖路徑成為事實上的主路徑
- **兩層所有權**：legal owner（戶頭名義）⊥ economic owner（錢實際是誰的）。報稅 / 對帳走 legal、portfolio 統計走 economic
- **憑證不進版控**：credentials.json 存 APP_DIR，不在 OneDrive 也不在 Git
- **加權平均成本法**：台灣投資人最常用，簡單且不需追蹤每筆買入批次
- **雙重記帳**：交易同時更新持股和現金，原子操作確保資料一致
- **快取避免頻繁請求**：股價 15 分鐘、匯率 1 小時 ^ck-029e2c-18
