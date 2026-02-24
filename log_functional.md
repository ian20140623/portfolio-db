# 帳務管理系統 — 功能說明
*last updated: 2026-02-23*

> **給未來 AI 的說明**
> 請先閱讀共用指引：[`../AI_LOG_INSTRUCTIONS.md`](../AI_LOG_INSTRUCTIONS.md)
>
> **本專案補充：**
> - 暫無

---

## 系統目標
多帳戶、多用戶的股票與現金統合管理系統，涵蓋台灣、美國、新加坡三個市場，支援即時報價、損益計算、計畫下單，並整合券商 API 與 CSV 匯入實現自動化同步。

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

---

## 檔案路徑
*last updated: 2026-02-23*

| 路徑 | 用途 |
|------|------|
| `C:\Users\User\OneDrive\ClaudeProjects\portfolio-db\` | 專案程式碼（OneDrive 同步） |
| `C:\Users\User\AppData\Local\PortfolioDB\portfolio.db` | SQLite 資料庫（不隨 OneDrive 同步，避免損壞） |
| `C:\Users\User\AppData\Local\PortfolioDB\credentials.json` | 券商 API 憑證（不進版控） |

---

## 資料庫結構
*last updated: 2026-02-23*

9 張資料表：

| 資料表 | 用途 |
|--------|------|
| `users` | 用戶（username, display_name） |
| `accounts` | 帳戶（綁定用戶，含券商、市場、幣別） |
| `holdings` | 持股現況（每帳戶每股票一筆，含均價） |
| `transactions` | 交易紀錄（不可變動的買賣記錄） |
| `cash_positions` | 現金部位（每帳戶每幣別一筆） |
| `cash_transactions` | 現金異動紀錄（存提款、股息、利息） |
| `planned_orders` | 計畫下單（PENDING → EXECUTED / CANCELLED） |
| `exchange_rates` | 匯率快取（1 小時 TTL） |
| `price_cache` | 股價快取（15 分鐘 TTL） |

關鍵設計：
- 交易紀錄採 **雙重記帳**：一筆 BUY 同時更新持股（shares 增加、均價重算）和現金（扣款）
- 均價計算採 **加權平均成本法**
- 計畫下單執行後自動連結到實際交易紀錄（`linked_transaction_id`）

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
```

---

## 券商整合
*last updated: 2026-02-23*

| 券商 | 市場 | 整合方式 | 狀態 |
|------|------|----------|------|
| 永豐金 (SinoPac) | TW | Shioaji Python API | 程式碼就緒，等用戶臨櫃申請 API |
| 富邦 (Fubon) | TW | Fubon Neo Python SDK | 程式碼就緒，等用戶申請憑證 |
| Firstrade | US | CSV 匯入（Tax Center 下載） | 可用 |
| 渣打新加坡 (SCB) | SG | CSV 匯入（Online Banking 下載） | 可用 |

台灣券商重點：
- 永豐需到臨櫃簽 API 風險揭露書，拿 API Key + Sinopac.pfx 憑證
- 富邦需到 fbs.com.tw/TradeAPI 申請，下載 .whl 安裝 SDK + 憑證
- 兩家都能查庫存（`list_positions` / `inventories`）和餘額（`account_balance` / `bank_remain`）

---

## CLI 指令總覽
*last updated: 2026-02-23*

```
python -m portfoliodb <command>

init                              初始化資料庫
user     add / list               用戶管理
account  add / list               帳戶管理
holding  add / list / remove      持股管理（手動匯入）
tx       buy / sell / list        交易紀錄（自動更新持股+現金）
cash     set / deposit / withdraw / list  現金管理
order    add / list / execute / cancel    計畫下單
price    get / batch              Yahoo Finance 即時報價
summary  account / user / all     投資組合摘要（含即時損益）
fx       rate / rates             匯率查詢
sync     sinopac / fubon / firstrade / scb / credentials  自動化同步
```

---

## 支援市場
*last updated: 2026-02-23*

| 市場 | 幣別 | Yahoo Finance 格式 | 範例 |
|------|------|-------------------|------|
| 台灣 (TW) | TWD | `代碼.TW` | 2330.TW（台積電） |
| 美國 (US) | USD | `代碼` | AAPL（Apple） |
| 新加坡 (SG) | SGD | `代碼.SI` | D05.SI（DBS） |

---

## 設計原則
*last updated: 2026-02-23*

- **自動化優先**：能用 API 或 CSV 匯入的就不手動輸入
- **資料庫不隨雲端同步**：SQLite + OneDrive 會損壞，DB 存 AppData
- **憑證不進版控**：credentials.json 存 AppData，不在 OneDrive 也不在 Git
- **加權平均成本法**：台灣投資人最常用，簡單且不需追蹤每筆買入批次
- **雙重記帳**：交易同時更新持股和現金，原子操作確保資料一致
- **快取避免頻繁請求**：股價 15 分鐘、匯率 1 小時
