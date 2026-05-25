# 帳務管理系統 — 流水帳
*2026-02-23*

> **給未來 AI 的說明**
> 共用指引見 [`../shared/LOG_GUIDE.md`](../shared/LOG_GUIDE.md)
>
> **本專案補充：**
> - 暫無 ^ck-626c9e-0

---

## 起點：從 Excel 到系統化
- 用戶想建立多帳戶統合系統，管理台灣、美國、新加坡的股票和現金
- 初步想法是用 Excel，但考量到未來要串接券商 API 下單，Excel 無法擴展
- 討論後決定用 Python + SQLite + CLI 架構 ^ck-2fde8f-2

## 技術選型討論
- **為什麼不用 Excel**：多帳戶管理不便、跨市場匯率手動、無法串接 API 下單
- **為什麼選 Python + SQLite**：SQLite 是檔案型資料庫，不需安裝伺服器；Python 有 yfinance 生態；未來串接券商 API 成熟
- **折衷方案**：Python 管資料庫 + 自動產出 Excel 報表，但用戶選了純 Python 方案
- **前端**：先做 CLI，之後再考慮網頁介面
- **資料來源**：Yahoo Finance（免費、不需 API key）
- **下單功能**：先做模擬/記錄（計畫下單），之後擴展為實際券商 API 下單 ^ck-61d0e1-3

## 資料庫設計
- 9 張表：users, accounts, holdings, transactions, cash_positions, cash_transactions, planned_orders, exchange_rates, price_cache
- 核心設計決策：
  - 持股表（holdings）是「現況快照」，由交易紀錄驅動更新，而非每次從交易紀錄重算
  - 均價採加權平均成本法（台灣投資人標準，比 FIFO 簡單）
  - 交易採雙重記帳：BUY 同時增加持股、減少現金，原子操作
  - SQLite 資料庫存在 AppData（非 OneDrive），避免雲端同步損壞 ^ck-d2077f-4

## 驗證 Yahoo Finance
- 測試三個市場全部成功：
  - 台灣：2330.TW（台積電 NT$1,915）、2317.TW（鴻海 NT$227）、0050.TW（元大台灣50 NT$77.2）
  - 美國：AAPL（$264.58）、NVDA（$189.82）、TSLA（$411.82）
  - 新加坡：D05.SI（DBS S$57.99）、O39.SI（OCBC S$21.72）
  - 匯率：USD/TWD 31.5790、USD/SGD 1.2684、SGD/TWD 24.9218
- Windows 終端機中文顯示有亂碼（cmd.exe 編碼問題），但資料正確 ^ck-6a7906-5

## 完成核心系統建構
- 建立完整 CLI 系統（init, user, account, holding, tx, cash, order, price, summary, fx）
- 實測端到端流程：建用戶 → 建帳戶 → 匯入持股 → 記錄交易 → 查看摘要含即時損益
- 跨市場用戶匯總正常運作：台灣帳戶 + 美國帳戶自動匯率換算後合計 ^ck-642838-6

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
  - TDCC（集保中心）只有 PDF、沒有開放 API；台灣沒有類似 Plaid 的整合服務 ^ck-15ef77-7

## 建立四種同步管道
- `sync sinopac <account_id>`：永豐 Shioaji API（就緒，等用戶申請）
- `sync fubon <account_id>`：富邦 Neo API（就緒，等用戶申請）
- `sync firstrade <account_id> <csv_path>`：Firstrade CSV 匯入（可用）
- `sync scb <account_id> <csv_path>`：渣打新加坡 CSV 匯入（可用）
- `sync credentials sinopac/fubon`：查看/設定 API 憑證狀態 ^ck-5bc286-8

## 專案目錄更名
- 工作目錄從 `PortfolioDB` 改為 `portfolio-db` ^ck-ca94bd-9

## 今日結論
- 核心系統完整可用：用戶管理、帳戶管理、持股、交易、現金、計畫下單、即時報價、損益摘要、匯率
- 四個券商的同步管道全部建好
- 下一步：用戶去臨櫃申請永豐和富邦的 API 權限，拿到 Key 後填入 credentials.json 即可自動同步 ^ck-d79b59-10

---

## 2026-05-24（週日）

### 20:30 [MINI] 跨平台 path + 兩層所有權 schema + 截圖 vision 灌入 8 個 account
- **觸發**：3 個月後在 Mac mini 重啟、發現 DB 路徑寫死 Windows `~/AppData/Local/`、Mac 上不存在
- **券商 API 路線改變**：原計畫等永豐/富邦 API 申請、Sir 決定改走「**截圖 + vision 辨識**」路徑、繞過台灣券商 CSV 匱乏 + API 申請門檻
- **架構決策**（per /athena framing）：portfolio-db 是 **single-machine app**、master DB 留 Mac mini（24/7 開機 + 已是 ks host）、不靠 cloud sync DB 檔（SQLite + WAL vs cloud sync 必衝突）、跨機器讀寫之後走 Tailscale ssh / HTTP；定期備份等有資料量再做、現在不 over-engineer
- **schema 改動**：accounts 表 `user_id` 拆成 `legal_owner_id` + `economic_owner_id`、支援「戶頭借名」場景（爸名下實質 Ian 的 / Ian 自己的 / 真的爸的三種 case）。`get_user_summary` 改走 economic owner
- **跨平台 path**：`db.py` 加 `_app_dir()` 依 OS 分流（Darwin → `~/Library/Application Support/PortfolioDB/`、Windows → 原 AppData、Linux → XDG `~/.local/share/`）、APP_DIR export 給 `brokers/config.py` 共用、brokers docstring 拿掉硬寫死路徑
- **`.TWO` 上櫃支援**：`detect_market` 補 `ticker.endswith(".TWO")` 也歸 TW market（8299 群聯 / 8021 尖點等上櫃股可正確處理）
- **多幣別支援**：`CURRENCIES` enum 從 3 個（TWD/USD/SGD）擴 11 個（+HKD/JPY/EUR/CNY/GBP/AUD/NZD/ZAR）、cli cash 指令的 Choice() 從硬寫改為 sorted(CURRENCIES) 一處改處處生效、CURRENCY_SYMBOLS 同步加 8 個符號
- **新增 `summary breakdown` 指令**：家族資產 8 個維度 aggregation（economic owner / legal owner / type / currency / market / broker / account_type / ticker concentration）+ flat positions 全展開、寬版 console 避免 truncate。`portfolio_service.get_family_breakdown(base_currency)` 為 service-layer entry
- **實際灌入 8 個 accounts、跨 4 個 broker、跨 3 幣別**：富邦證/富邦銀（dad/ian）+ 永豐證/永豐複委託/永豐銀（dad/dad）+ Firstrade（ian/ian）+ SCB SG ian（ian/ian）+ SCB SG dad（dad/ian）。家族總資產 NT$~371M、4.4% 現金、95.6% 股票、Top 3（2383 台光電 / 8299 群聯 / NVDA）concentration 61%
- **截圖辨識公式紀律**：永豐 vs 富邦 vs Firstrade vs SCB 各家「庫存總市值」/「損益試算」公式不同（賣出實得含 0.4575% 稅費 vs 毛市值 vs cost-includes-fees vs FIFO）、cross-source 驗證用 yfinance + cnyes 鉅亨網。當帳戶只給「股數+損益」時、反推均價要套對家公式 ^ck-260524-portfolio-db-revive

---

## 2026-05-25（週一）

### 21:23 [MINI] Claude Code memory + PJHub layout + CLAUDE.md pointer
- **觸發**：跟 Athena 9 輪深度對話後（議題：是否離職管理家族財富、借名 unwind、信託架構、Silent Protector pattern 等）、Sir 要求留 documentation continuity、未來 AI session 不從頭講
- **內容極度 sensitive**：含家族財富 NT$4 億、借名 NT$123M、太太 information asymmetry、弟弟精神問題、公證遺囑 67/33 等 — 絕對不入 git
- **layout 演化**（5 次到位、records JV pattern 對 PJHub convention 不夠敏感）：
  1. `~/.claude/projects/.../memory/` → Sir 嫌 hidden 不好改
  2. `~/Projects/portfolio-db/memory/` + .gitignore + symlink → 發現被 ks watcher vectorize (config 含 `/Users/ianchang/Projects` recursive *.md)
  3. `Dropbox/personal_archive/` sibling folder → Sir 提 PJHub
  4. `PJHub/personal_memory/portfolio-db/` → Sir 指出該是 `PJHub/portfolio-db/...`
  5. `PJHub/portfolio-db/memory/` ← 對齊 PJHub convention（同 broker-reports / fl-strategy pattern）
- **Final layout**：
  - 真實 file：`~/Library/CloudStorage/Dropbox/PJHub/portfolio-db/memory/` — Dropbox 自動跨機器 sync、不在 ks watcher recursive scope、不被向量化
  - Claude Code symlink：`~/.claude/projects/-Users-ianchang-Projects-portfolio-db/memory` → 上面
  - 4 個 draft memory file（draft_family_wealth_architecture / draft_family_stakeholder_map / draft_unwind_game_plan / draft_silent_protector_pattern）+ MEMORY.md index
- **CLAUDE.md 加 pointer**（safe modification、不洩漏 memory content、只寫 path + 用途 + 跨機器 setup 指令）— git tracked、推 GitHub OK
- **ks vectorization audit**：grep chunks/ 確認 no memory file traces ingested（watcher 沒來得及 process、現在 source 已移走、catch up 後 nothing to index）
- **Debug pattern reuse**：撞「Resource deadlock avoided」at `mv` step、按 CLAUDE.md errno-first 紀律改用 `cp -a + rm -rf` 取代 mv ^ck-260525-memory-pjhub-layout
