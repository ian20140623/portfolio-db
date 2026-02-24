# 帳務管理系統 — 流水帳
*2026-02-23*

> **給未來 AI 的說明**
> 共用指引見 [`../shared/LOG_GUIDE.md`](../shared/LOG_GUIDE.md)
>
> **本專案補充：**
> - 暫無

---

## 起點：從 Excel 到系統化
- 用戶想建立多帳戶統合系統，管理台灣、美國、新加坡的股票和現金
- 初步想法是用 Excel，但考量到未來要串接券商 API 下單，Excel 無法擴展
- 討論後決定用 Python + SQLite + CLI 架構

## 技術選型討論
- **為什麼不用 Excel**：多帳戶管理不便、跨市場匯率手動、無法串接 API 下單
- **為什麼選 Python + SQLite**：SQLite 是檔案型資料庫，不需安裝伺服器；Python 有 yfinance 生態；未來串接券商 API 成熟
- **折衷方案**：Python 管資料庫 + 自動產出 Excel 報表，但用戶選了純 Python 方案
- **前端**：先做 CLI，之後再考慮網頁介面
- **資料來源**：Yahoo Finance（免費、不需 API key）
- **下單功能**：先做模擬/記錄（計畫下單），之後擴展為實際券商 API 下單

## 資料庫設計
- 9 張表：users, accounts, holdings, transactions, cash_positions, cash_transactions, planned_orders, exchange_rates, price_cache
- 核心設計決策：
  - 持股表（holdings）是「現況快照」，由交易紀錄驅動更新，而非每次從交易紀錄重算
  - 均價採加權平均成本法（台灣投資人標準，比 FIFO 簡單）
  - 交易採雙重記帳：BUY 同時增加持股、減少現金，原子操作
  - SQLite 資料庫存在 AppData（非 OneDrive），避免雲端同步損壞

## 驗證 Yahoo Finance
- 測試三個市場全部成功：
  - 台灣：2330.TW（台積電 NT$1,915）、2317.TW（鴻海 NT$227）、0050.TW（元大台灣50 NT$77.2）
  - 美國：AAPL（$264.58）、NVDA（$189.82）、TSLA（$411.82）
  - 新加坡：D05.SI（DBS S$57.99）、O39.SI（OCBC S$21.72）
  - 匯率：USD/TWD 31.5790、USD/SGD 1.2684、SGD/TWD 24.9218
- Windows 終端機中文顯示有亂碼（cmd.exe 編碼問題），但資料正確

## 完成核心系統建構
- 建立完整 CLI 系統（init, user, account, holding, tx, cash, order, price, summary, fx）
- 實測端到端流程：建用戶 → 建帳戶 → 匯入持股 → 記錄交易 → 查看摘要含即時損益
- 跨市場用戶匯總正常運作：台灣帳戶 + 美國帳戶自動匯率換算後合計

## 用戶堅持自動化，研究券商整合
- 用戶明確表示「一定要自動化，台灣的也一定要做」
- 研究結論：
  - **台灣券商 CSV 匯出能力極差**（大多只有 PDF 或螢幕顯示）
  - 但永豐和富邦都有官方 Python API：
    - 永豐 Shioaji：`api.list_positions()` 查庫存、`api.account_balance()` 查餘額
    - 富邦 Neo API：`sdk.accounting.inventories()` 查庫存、`sdk.accounting.bank_remain()` 查餘額
  - 兩者都需要臨櫃申請（簽風險揭露書、拿 API Key 和憑證），用戶尚未申請
  - Firstrade：有 CSV 匯出（Tax Center），已寫好解析器
  - 渣打新加坡：銀行帳戶有 CSV 匯出，已寫好解析器
  - TDCC（集保中心）只有 PDF、沒有開放 API；台灣沒有類似 Plaid 的整合服務

## 建立四種同步管道
- `sync sinopac <account_id>`：永豐 Shioaji API（就緒，等用戶申請）
- `sync fubon <account_id>`：富邦 Neo API（就緒，等用戶申請）
- `sync firstrade <account_id> <csv_path>`：Firstrade CSV 匯入（可用）
- `sync scb <account_id> <csv_path>`：渣打新加坡 CSV 匯入（可用）
- `sync credentials sinopac/fubon`：查看/設定 API 憑證狀態

## 專案目錄更名
- 工作目錄從 `PortfolioDB` 改為 `portfolio-db`

## 今日結論
- 核心系統完整可用：用戶管理、帳戶管理、持股、交易、現金、計畫下單、即時報價、損益摘要、匯率
- 四個券商的同步管道全部建好
- 下一步：用戶去臨櫃申請永豐和富邦的 API 權限，拿到 Key 後填入 credentials.json 即可自動同步
