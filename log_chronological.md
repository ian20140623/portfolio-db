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

---

## 2026-05-27（週三）

---

## 2026-05-30（週六）

### 16:00 [MINI] 家族治理 framework v0.2 → v0.3（doctrine + GPT deep research mechanism integration）
- **觸發**：portfolio-db V1 是 Sir 自己 active 階段工具、但跨上一層「家族治理」doctrine 一直在 PJHub memory 4 drafts（internal sensitive context）+ scratch 沒結構化的對話。今天 Sir ship 家族 v0.2 doctrine + GPT deep research 進到 scratch、要整合 v0.3
- **v0.2 framework（Sir 寫）**：10 章 + 收尾句、family governance doctrine 公開層 — 一/二/三 核心使命 + 哲學 + 兩層資本架構（個人自由基金 ~$10M/人 + 家族資本池）、四 治理（所有權 / 管理權分離）、五 退出機制（4 方案 + 冷靜期）、六 投資哲學（passive ETF for 後代）、七 跨國韌性、八 制度進化、九 未來擴張、十 待研究、核心句「家族資本目的不是讓下一代繼續管理我的人生、而是讓下一代有能力選擇自己的人生」
- **我的 v0.2 first-pass review**（vision 層 solid、結構層對但缺 mechanism、execution 層誠實但 7 個 missing layer）
- **GPT deep research（5/30）**：industry anchor 補 v0.2 缺的 binding layer mechanism。關鍵 anchor：SFO 經濟門檻 $100M（$10M 不該做 full SFO、做「微型家辦」即可）、PwC 2026 SFO 結構成本 80.7 bps、US$60,000 estate tax 門檻（Sir 直接持 NVDA / GOOG / TSM / MSFT 已遠超、是真實風險）、SIPC $500K / SG DI S$100K、台灣 2026 連續受益人信託 100 年存續新規。跨國分層：台灣（家庭 + 稅務接點）+ SG / CH（制度 / 保管）+ US（執行）、不是「全部放一國」
- **GPT 補了 / 漏了**：我之前點出的 7 個 missing layer 中、GPT 補了 3 個（治理 mechanism / voting / dispute）、partial 補 2 個（transition path / boundary mechanism）、完全沒處理 2 個（從 Sir 現狀走到 v0.2 setup 的 transition path、家族成員擴張界線）。Hidden context（借名 unwind / 21 年 active capability / 太太 information asymmetry / 弟精神問題）GPT 不可能知道、Sir 必須自己跟 lead counsel 補
- **v0.3 結構**（`scratch/家族v0.3.md`）：保留 v0.2 一到十章 + 核心句完整、新增 4 章 — 十一 治理 mechanism（三層 voting 憲法 unanimous / 政策 2/3 / 日常 IPS + 三個獨立角色 trustee / 估值專家 / facilitator + 三層衝突處理 mediation / expert / arbitration）、十二 退出公式（30 天通知 / 60 天冷靜期 / 10-20% 初始 + 3-7 年分期 / liquid 不用 minority discount / illiquid 獨立估值）、十三 跨國分層 + 顧問體系（微型家辦不做 SFO + 台/SG/CH/US 各層角色 + lead counsel / lead tax / trustee / custodian / facilitator RACI）、十四 實施順序（短/中/長期 Gantt + 「先做順序、不要先做工具」收尾）
- **三層 framework 整體**：(a) 家族 v0.3 = public-facing doctrine + mechanism（可給律師 / 顧問看）(b) memory 4 drafts = internal sensitive context（爸 85 / 太太 / 弟 / 借名、不對外）(c) portfolio-db V1 = Sir 自己 active 階段工具
- **doctrine point**：v0.3 mimic Sir voice（短句 / blockquote 強調 / 列表 enumerate / 不堆術語）、不寫成 GPT 顧問報告 style。對應 Sir「畢竟只是建議」哲學 + 「核心價值不易改、操作層可改」pace layering
- **跨層 mapping**：portfolio-db Layer 0「美股 39% ≈ Sir eco 比重 = 借名 unwind 路徑」其實是 V1 active framework 朝家族 v0.3「個人自由基金 + 家族資本池」前進的中介狀態。Sir eco 部分遷到自己 legal 美股、之後分入女兒 A / B 個人自由基金、就完成從 V1 到 v0.3 的 transition
- **outstanding（v0.3 範圍外、要 Sir 另解）**：(1) 借名 unwind path（Sir + lead counsel 設計、不能寫進 doctrine）(2) Sir active → 後代 passive 的 hand-over timing（V1 → v0.3 銜接 trigger）(3) 第一層 ↔ 第二層 boundary trigger（何時撥下去個人自由基金）(4) 家族成員定義（配偶 / 同性 / 離婚 / 再婚 / 非婚生 / 孫輩 qualify 條件）^ck-260530-family-v03-integration

---

## 2026-06-10（週三）

### 11:51 [MINI] 投組 review + 家族財富規劃深談 → distilled 入 project memory（不入 git）
- **投組 review**：`summary breakdown` + 重抓 live 報價，對照 Layer 0 偏離（部位/餘額數字在 DB，不入 log）
- **家族財富規劃 sensitive 討論**（unwind 執行窗口 / 時序 / 結構）→ 全部 distilled 進 `memory/`（Dropbox、不被 ks vectorize、不入 git）。新增 `draft_unwind_execution_window`、`draft_freedom_and_two_kinds_of_money` + `feedback_portfolio_all_in_ai`，並更新 `MEMORY.md` 索引
- **無 code 變更**；本 commit 僅 `.claude/settings.local.json` permission allowlist 更新
- **outstanding**（細節記在 memory）：永豐實際餘額更新進 DB、跨境前置清單
- 過程踩到 Dropbox FileProvider placeholder evict（hydrate / `MEMORY.md` EPERM 繞 shell 寫入）——已知 papercut，永久解 = Finder 把 `memory/` 設「一律保留在此裝置」

---

## 2026-06-13（週六）

### 16:30 [Mac mini] KS 私密內容分層 doctrine + 清 stale memory leak；家族 context 續談（distilled 入 memory）
- **KS 隱私發現（非敏感、infra 層）**：續談家族 context 時岔出——5/25 那批 `draft_*` 家族 memory 因早期一次性手動 import **殘留在 ks 索引、跨專案 `ks_search` 搜得到**（project-docs 37 chunk + `chunks` collection 舊 Windows 路徑 4 chunk = 41）。**修正 6/10 log「不被 ks vectorize」的錯誤認知**——當時其實已 leak。
- **防線一（清 leak、還原語意）**：停 ks-search/watcher/inbox → 快照 vectordb → 按 source 刪 41 chunk → 驗殘留 0 + 三 query 確認家族內容不再被搜到 → 重啟 → 刪快照。
- **防線二（output-firewall）**：立 `feedback_private_context_not_content.md`——私層只當 context、對外產物 default-deny、送出前主動揭露含哪些私層（不向量化）。
- **L0 公開知識**：抽資產規劃相關法規（洗防法 §5/§13、律師 vs 會計師特權、券商/銀行限額、央行結匯、意定監護）成 `Ian-Vault/法規參考/台灣_資產規劃相關法規參考.md`（已查證官方來源、可 ks 搜、零私層）。
- **KS 分層 doctrine（Mnemosyne spawn 拍）**：三層 L0 public / L1 private-indexed / L2 private-airgapped + D1–D5（D1 `search_all`→allowlist 動核心走 arch-review、D3 upsert 物理 gate、D4 memory 永不 import、D5 跨專案 stale 清理）→ 記入 hub cross_todo `^ck-260613-ks-sensitivity-layering`。Athena spawn 先 framing scoped-retrieval。
- **家族財富規劃 sensitive 續談**（顧問分工 / 資產規劃法規 / 結構層）→ 全部 distilled 進 `memory/`（本機、不入 git）；更新 `draft_compliance_advisor_sequencing` 等。
- **無 portfolio-db code 變更**；本 commit 僅 log + `.claude/settings.local.json`（本 session 法規 WebFetch 網域 + bash 權限累積）。

---

## 2026-06-18（週四）

### [Mac mini] 建立 off-machine cold backup 機制（補 6/14 重灌資料全失的缺口）
- **觸發**：Sir 報「錢從富邦匯到新加坡、留 200 萬下來」（unwind plan 6/10 拍板 one-shot 富邦→SG 結構正式執行），要落帳時發現 `portfolio.db` 開不了——AppData 目錄整個不存在。查出 **6/14 Mac mini 重灌**：DB 是刻意不進 git / 不進雲端的單機設計（避 SQLite WAL 衝突），重灌 = 本機 DB + migration 快照全失、**無 Time Machine、無 off-machine copy**。Dropbox 只有家族 memory `.md`（還在）、DB 從來沒備份。
- **根因診斷**：當初 system_map:219「不 cloud sync DB」只做對一半——對的是「不能 live 雙向 sync」（WAL corruption），漏的是「定期 cold dump 到 off-machine」。靜態快照沒 WAL 問題、單向 copy 不會 corruption，是當初該做沒做的安全網。
- **`portfoliodb/backup.py`**（新模組）：SQLite online-backup API 產生一致性快照（無 WAL）→ 寫 Dropbox `PJHub/portfolio-db/db_backups/`。`.tmp` → atomic rename 發布（Dropbox 不會上傳半截檔）、寫後 `PRAGMA integrity_check`、輪替保留 30 份、`*.db.tmp` 自動清。`restore` 前先驗 integrity + 存 `portfolio.pre-restore-*.db` 安全副本（可逆）。無 DB 時 `create_backup` 乾淨回 None（排程在重建前是 no-op 非 error）。
- **CLI**：`backup`（立即）/ `backup list` / `backup restore [檔] [--force]`。
- **排程**：launchd `com.portfoliodb.backup` 每日 03:30（`scripts/install_backup_schedule.sh` 從環境生 plist、已安裝 + kickstart 驗過跑通）。
- **測試**：`tests/test_backup.py` 10 案全綠（no-op / 快照 integrity / atomic 無 .tmp / 輪替 / stale tmp 清除 / restore / 拒覆蓋無 force / force + 安全副本 / 拒 corrupt / 缺檔）。非 yfinance 既有測試 31 全綠。
- **遵 Recovery≠Optimization**：本次只建備份機制（獨立改動）、不夾帶任何 schema / 邏輯優化；DB 重建是下一個獨立步驟。
- **發現的環境缺口**（reformat collateral、非本次 code 問題）：本機 `yfinance` 未裝（requirements.txt 有、6/14 後沒重裝 deps）→ `price_service` import 失敗、連帶 2 個既有測試 collection error。待 `pip install -r requirements.txt`。
- **outstanding**：(1) DB 從零重建（log 交易史 + 券商現況截圖）(2) 重建後補落帳富邦→SG 匯出 + 富邦留 NT$2,000,000 (3) 重裝 deps。 ^ck-260618-cold-backup

### [Mac mini] DB 重建 Phase 1：環境 + 結構層（部位層待截圖）
- **重裝 deps**：`pip install -r requirements.txt`（yfinance/click/rich/pytest），補 6/14 重灌後缺的 runtime；全測試 35 綠（25 既有 + 10 backup）。
- **建空 schema**：`portfoliodb init`（12 表全建）。
- **結構層重建**（從 5/24 log 的帳戶結構 + Sir 確認）：2 users（ian / dad）+ 8 accounts，**ID 順序刻意對齊 5/24**（1=富邦證 2=富邦銀 3=永豐證 4=永豐複委託 5=永豐銀 6=Firstrade 7=SCB-SG-ian 8=SCB-SG-dad），owner 對應全部 Sir 確認過（acct 1/2/8 eco=ian legal=dad、acct 3/4/5 dad/dad、acct 6/7 ian/ian）。instruments 兩層身份跑 m001 --apply reseed（空 DB 只 seed TSMC company + 2 instrument + 4 alias，原 9 條 provisional 是當初從既有部位 backfill 出來的、會在灌持股時自然產生）。
- **首份真實備份**：`portfolio-20260618-095703.db`（106KB）進 Dropbox、端到端驗證 backup 機制對真實 DB 可用。
- **Sir 指示**：富邦證 (acct 1) **retiring 以後先不用**（富邦→SG 匯款後），但**先不標 is_active=0**，等截圖確認清空/殘留再設（避免擋掉可能要補的轉出紀錄）。
- **重建策略**（對齊 Recovery≠Optimization）：log 只有零星部位片段、均價救不回 → 不重建 5/24 舊狀態套 delta，改**直接抓 6/18 當前部位**重灌（天然含富邦匯出 + 留 200 萬 + SG 進款）；transaction 歷史 6/14 前不可逆遺失、記為可接受偏離。
- **outstanding**：holdings + cash 逐帳戶截圖灌入（Sir 慢慢給）→ 每批灌完 commit + backup；灌完富邦證後標停用；落帳富邦→SG + 留 NT$2,000,000。 ^ck-260618-db-rebuild-phase1

---

## 2026-06-22（週一）

### 11:30 [Mac mini] 4 天 re-sync 驗證 + 建截圖匯入通道（Phase 2 前置）
- **re-sync 驗證**（6/18→6/22 隔 4 天）：repo up-to-date；備份機制每日有跑（6/18~6/21 共 4 份日快照 + 輪替正常）；DB 結構完好（直查 DB：8 accounts / 2 users / 0 holdings / 0 cash，符合 Phase 1 結束狀態）。
- **備份時間觀察**：plist 設 03:30、實際快照落在 18:30。研判 Mac mini 03:30 在睡、launchd 把錯過的 calendar job 延到機器醒來（約 18:30）補跑。**每日一份 off-machine 快照的目標達成**，時間點不影響保護力；要釘死需另設 pmset 喚醒（暫不做）。
- **手機截圖丟不進來 root cause**：Sir 用 **Claude 手機 App** 丟圖、那是**獨立 session**、跟本 Mac mini 終端機 session 不互通 → 圖不會出現在這裡（不是壞掉）。DB rebuild context 在本 session、DB/repo/備份在 Mac mini。
- **解法 = 建檔案通道繞過聊天圖片**：建 `~/Library/CloudStorage/Dropbox/PJHub/portfolio-db/screenshots_inbox/`。Sir 手機 Dropbox App 上傳截圖到此夾 → Dropbox sync 到 Mac mini → JV 用 Read tool 直接讀檔灌入。AirDrop→Downloads 為備援路徑。
- **Phase 2 SOP 定案**：截圖落 `screenshots_inbox/` →（檔名標帳戶更佳、不標 JV 逐張確認）→ JV 灌 holdings/cash → 當場對帳 → 每批 commit + backup。建議順序富邦證→富邦銀→SCB SG（匯款動線）。
- **本 commit 僅 log + settings.local.json（pm2 list 權限）**；無 code 變更。 ^ck-260622-rebuild-phase2-channel

---

## 2026-05-29（週五、接續）

### 17:00 [MINI] V1 第十二節 final（4 子節）+ append 進主檔、framework 12 節完整
- **觸發**：5/27 Athena 對話 + 5/28 ~ 5/29 framework iteration 後、Sir 拍板 4 個 design decision、第十二節 finalize 並 append 進 `20260527-投組初步想法.md` 主檔
- **拍板的 4 個 framework decision**（從複雜走回簡單、對齊 Sir「畢竟只是建議」哲學）：
  - **priority 順序不寫**：我推論的「長期品質 > 掌握度 > 估值」是從 Sir 對話 inferring、不是 Sir 明寫。Sir 不認可寫進 framework — V1 第一節原本「三維等權重加總 15 分」就足夠、加 priority 層會跟信用評等式精神打架
  - **12.5 Two-strikes 紀律不寫**：D（V1 第一節 15 分加總）+ 第三節階梯式（12-13 中高 / 14-15 高信心）已**隱含** Lynch cutting flowers 紀律。例如：估值 5→2 但其他維度不動、總分仍 12 分 = 中高比重、不會自然 trigger sell。emergent property、不需要 explicit 寫 two-strikes
  - **12.4 升級 / 淘汰 transition rule 整個拿掉**：升級 / 淘汰 implicit 走 D（15 分加總）+ 12.2（換手 threshold）、不另立 mechanical rule（連續 N 季 parameter 也不寫）。轉機升級 = 重評 15 分 + 走 12.2、淘汰 = 分數退低 + 走 12.2
  - **estimation realtime / 其他 event-driven**：估值要 portfolio decision 時 pull、掌握度 + 長期品質 事件觸發、無定期 trigger（reject Athena 提的 fixed cadence）
- **第十二節 final 結構**（4 子節、簡潔對齊 V1 前 11 節風格）：
  - 12.1 三類輸入更新節奏（estimation realtime / 其他 event-driven）
  - 12.2 換手 threshold 分級（gap ≥ 1 建議 / ≥ 3 強烈建議 / < 1 不動、grey zone 不動要寫理由防 narrative drift）
  - 12.3 新標的觸發 re-score（同桶 / 同主題 / 同共同風險、吸收 opportunity cost re-pricing）
  - 12.4 一句話濃縮
- **append 進主檔**：`scratch/20260527-投組初步想法.md` 在第十一節「最終一句話版本」後加第十二節、framework 12 節完整
- **doctrine 收斂**：framework 從「多層 priority + Two-strikes + N 季 parameter + sub rules」收斂到「D 等權重 + 12.2 換手 threshold + 第三節階梯」三件事。Sir 的判斷：framework 給 ranking signal、不替 Sir 強制執行、過度規則化反而會違反「分數負責排序、不直接等於投資比重」的 V1 第三節原意
- **Athena 第三方視角 net contribution**：surface「時間紀律 vs 空間紀律」對立 + 「新 idea = trigger re-score 不是手續」reframe + 「分數 → 比重 translation 有兩維」精確診斷、撐住 framework 整體 coherence。但具體規則內容由 Sir 21 年 buy-side 直覺拍板、Athena 不替 Sir 下結論（對齊 Athena spawn skill 的 niche）
- **outstanding**：產業 PEG 25 ticker + 桶平均 + 個股 vs 桶 比較表 → Sir-friendly 單一 worksheet（含掌握度 / 估值 / 護城河 三 column 給 Sir 填）。Framework 完成後、實際填表是下一個 hop ^ck-260529-v1-section12-final

---

## 2026-05-27（週三、接續）

### 15:30 [MINI] Athena 對話建 V1 第十二節（時間紀律 / 換手規則）+ Lynch two-strikes 紀律 + 產業 PEG 抓全 27 → 25 ticker
- **觸發**：跟 Athena 3 輪對話、起點 Sir 問「top-down allocation 準度不高、bottom-up 微調太煩」
- **Athena round 1**：Sir 直覺「top-down 不準」對、但 Layer 0「美股 39%」本來就不是市場預測、是借名 unwind invariant 物理外顯、不依賴市場準度。Sir「煩」實際上是 V1 critical gap — 沒寫「時間維度」、把估值 / 掌握度 / 長期品質三類半衰期不同的輸入用同 cadence 追蹤
- **Athena round 2**：Sir 續問「想加新標的、水位高、要降誰」、Athena reframe 為「不是『誰讓位』、是『X 是否強過排尾』」+ 拆兩個正交問題（A. X 值不值得進、B. 頂掉誰 = conviction 最低）+ cash 不是 baseline、最弱舊持股才是
- **Sir push back**：Athena 用「順不順眼 / 找祭旗對象」措辭、Sir 不領情、強調 V1 15 分模型本身就是 conviction × valuation × moat 三維系統化排序方法論、不是憑感覺
- **Athena round 3**：認錯「順不順眼」措辭、但守住核心 — V1 第三節「分數主要負責排序、不直接等於投資比重」這句 Sir 自己寫的已暗示 translation 有空間 + 時間兩維、V1 把空間維度展開（兩層配置 + 共同風險 + 風險調整）、時間維度沒展開（換手規則）。提議寫成 V1 第十二節、避免 framework fork drift
- **V1 第十二節初稿**（`scratch/20260527_v1_section12_draft.md`、5 個子節）：
  - **1. 三類輸入更新節奏** — Sir 拍板：估值 = realtime / on-demand pull、掌握度 + 長期品質 = 不定期 event-driven、無定期 trigger（reject Athena 提的 fixed cadence、保留 event-driven）
  - **2. 換手 threshold 分級**（Sir 拍板）：gap ≥ 1 分建議換手、gap ≥ 3 分強烈建議、gap < 1 不動。對齊 V1 第三節階梯式風格（12-13 中高 / 14-15 高信心）。3 分跨度 = 跨一個信心區間
  - **3. 新標的觸發 re-score** — X 浮現本身就是 event-driven trigger、re-score 同桶 / 同主題 / 同共同風險舊持股、吸收 opportunity cost re-pricing signal（absolute scale 對機會成本變化遲鈍的補救）
  - **4. 升級 / 淘汰 transition rule**：轉機股 → 一般股升級 N 季可持續性 5 分（parameter 未填）、探索股 → 一般股升級條件對齊第八節、一般股 → 降級 / 出場 N 季 thesis 證偽（parameter 未填）
  - **5. Sir surface tension**：「成長股最好做法是抱緊、可是這樣沒辦法買新股」+「曾經短期漲多就賣、後來少賺一大段」+「拉開 PEG 分數會更容易因股價賣出」 — 引 Peter Lynch *One Up on Wall Street* multi-bagger / cutting flowers 紀律
- **提議 12.5 Two-Strikes 紀律**（待 Sir 拍板）：
  - **估值單獨惡化 ≠ 賣**、必須 (估值 ↓) AND (掌握度 OR 長期品質 ↓) 才走第 2 條換手 threshold
  - 估值單獨惡化只 trigger trim（部分減碼）、不 trigger switch（整檔換出）
  - 對應 Lynch 紀律 — 純估值貴不賣、fundamentals 變壞才賣（避免 cutting flowers / watering weeds）
  - 不需先定義「核心持股」、universal 規則套所有持股、sidestep motivated reasoning（Athena 可能挑的點）
  - 同時解開「拉開 PEG 分數區辨力」vs「過動換手」兩個 design tension
- **產業分桶 + PEG 抓取（早上 / 中午先跑完）**：
  - 候選大族群清單從 15 縮 9（per Sir「不用全部產業」、轉機 / 探索改回 attribute 不獨佔大族群）
  - 樣本範圍 27 → 25（per Sir 「LGD 034220.KS / 5425 台半 移除、vault 無 data 且非核心 universe」）
  - PEG 抓取 3 層 fallback：yfinance pegRatio → vault frontmatter eps_2026 → vault recursive deep dig（含 `_company/` 自家整理）。最終 25 ticker 全有 source（vault frontmatter 13 / vault body-only 2 / yfinance only 10）
  - yfinance `earningsGrowth` 不可信（過去 YoY TTM、被低基期反彈 dilute）、自己算 PEG 失真。yfinance 自己的 `pegRatio` 較對（用 forward forecast、但仍有 outlier 如南電 11.28）
  - vault deep dig 發現 broker_reports pipeline 對 13/15 ticker 抽到 `target_price + broker_name + rating` 進 frontmatter、但 `eps_2026` 只 2 檔（2383 + 8021）。其他要看 body 內文 EPS table 或 `_analysis/<公司>_法說會_<日期>.md` 自家整理（含「平均 EPS / 目標價區間」消化過數字）
  - Sir 自家 `_analysis/` 比 broker report 更精煉 — 群聯 8299 整理：4 家券商 2026E EPS 估值 75-220 元、分歧近 3 倍、凱基估 2027E EPS 年減 55%
- **doctrine 點**：framework V1 的本質是 living ranking、不是 static collection。新標的浮現 = trigger re-score、不是 just 評 X。Sir 21 年直覺對齊 quality-led long-hold + Lynch two-strikes、framework 該明寫這個 priority 順序：長期品質 > 掌握度 > 估值
- **outstanding**：12.5 Two-strikes 待拍板、2 個 parameter 待填（轉機升級 N 季 / 淘汰 N 季）、產業 PEG 算術平均 + 個股 vs 桶比較表還沒整成 Sir-friendly 單一 worksheet ^ck-260527-v1-section12-athena-lynch

### 11:00 [MINI] Portfolio construction framework V1（scratch）+ Layer 0 unwind reframe + 產業分桶 worksheet 啟動
- **觸發**：5/26 三筆 TW 成交入帳後、Sir 從 row-by-row 部位調整跳到 portfolio construction methodology 層級。問題從「2383 富邦減 1,000 股嗎」變「我只有 100%、想用 PEG + Kelly 綜合 + 加新標的、怎麼系統化分配」
- **Framework V1**（寫在 `scratch/20260527-投組初步想法.md`、Sir 親自撰寫）：
  - **15 分模型**（掌握度 + 估值吸引力 + 長期品質）、每維度 1-5 分、信用評等式絕對標準（非 sample 內相對排名）
  - **兩層配置**：大族群分數 → 額度 → 族群內個股分數 → 個股比重、擋「同類股越找越多、主題自動變大」的假分散
  - **族群不切太細**（同核心假設 = 同桶）+ **共同風險檢查**（6 維度：需求 / 客戶 / 景氣 / 估值因子 / 政策 / 籌碼）
  - **轉機股獨立 frame**（用 normalised EPS / FCF / ROE 不用 PEG）+ **探索股獨立 frame**（單檔 ≤ 3%、同主題 5/10/15% escalation ladder + 升級 / 淘汰條件事前寫）
  - **Kelly 降級成警報器**：不當主工具（estimation noise 對 Full Kelly 過敏感）、用來反向壓力測試「現在這個部位是否需要過度樂觀假設才合理」
- **Layer 0 reframe — Sir 後續補的關鍵**：在 V1 之前加「現金 2% / 台股 59% / 美股 39%」top-down 分配、**美股 39% ≈ Sir eco 比重 39.4%**。framework intent 不是純資產配置、是 **借名 unwind 路徑** — Sir eco 部分逐步遷到美股（自己 legal 持有）、爸 eco 部分留台股 + cash。跟 PJHub memory `draft_unwind_game_plan` 的 Type B substance unwind + Silent Protector pattern 高度對齊
- **TSMC 算美股**：對應 5/26 ship 的 instrument-layer ticker identity — portfolio 配置走 instrument（TSM 算美股 / 2330.TW 算台股 分開）、issuer 級 TSMC 整體曝險走第六節「共同風險檢查」處理
- **我 critique 浮上 5 個 critical gap**（framework V1 未補）：(1) 分數 → 比重 mapping 仍 judgment call、未量化 (2) 大族群額度公式空白（14 分族群配多少 %）(3) Kelly 警報 trigger 條件未定 (4) rebalancing 時間維度缺失（多久 review、什麼條件動）(5) 轉機 → 一般股升級 transition rule 未寫
- **產業分桶 worksheet 啟動**（`scratch/20260527_industry_buckets_candidates.md`）：列 15 個候選大族群 + 現有 12 檔初步分桶（4 檔屬性不確定：旺宏 / 一詮 / 立隆電 / 群創）+ 10 row 空白給 Sir 填潛在標的。Sir 填完我跑 yfinance 抓 PE / forward growth、算每桶 PEG median 當錨點、Sir 用「個股 PEG vs 產業 PEG」判估值吸引力 1-5 分
- **honest 對比**（修正後、target − 現有 convention）：cash 4.1% vs target 2% (−2.1%、5/28 永豐扣 4.2M 後自然到位)、台股 73.7% vs target 59% (−14.7%、削 ~60M)、美股 22.2% vs target 39% (+16.8%、加 ~69M)。主軸 ~NT$60-70M TW → US rotate、但跨法律名義人 / 幣別 / 國別、要走 unwind plan 4-phase 不是純買賣
- **outstanding**：5/28（明天）永豐交割扣 −4,212,337、Sir ship 銀行餘額截圖後 `cash set 3 TWD <新數字>` 重對齊。3481 群創 cash flow 沒在 DB（−4,429,803）、5/28 結算後 broker 與 DB 差此額、用 5/28 set 蓋過去即可 ^ck-260527-framework-v1-layer0-unwind

---

## 2026-05-26（週二）

### 16:10 [MINI] ticker canonical + company / instrument 兩層身份 + migration 001 + 25 tests
- **觸發**：5/26 早上 `order review` 跑出三條 data quality issue — DB 內 `2330` / `2383` 沒 suffix 跟 `2330.TW` / `2383.TW` 被當不同 ticker、`repeated_tickers` 被拆分淹掉、yfinance 對 raw ticker 噴 HTTP 404 stderr 噪音污染 console。Sir 給 6 階段任務 brief、要求採 A + B + ticker identity 改成 company / instrument 兩層
- **核心原則**：TSM 與 2330.TW 同公司 TSMC（issuer-layer）、但不同 instrument（ADR vs 普通股、市場 / 幣別 / 價格 / 交易單位 / P&L 全不同）。**order / position / price / P&L / execution 層不可合併**、只有 `summary breakdown by issuer`（未來功能）才可走 company-layer
- **設計選擇**：mapping table + canonical helper、不重寫 5 個 ticker column 的 schema 結構（per Sir「最小安全修正、不大型 FK refactor」）
- **Schema 新增**（idempotent `CREATE TABLE IF NOT EXISTS`）：
  - `companies (company_id PK, display_name, notes)` — issuer 層
  - `instruments (instrument_id PK, ticker UNIQUE, market, currency, company_id NULLABLE FK, security_type, notes)` — security 層、`ticker` 是 canonical key
  - `company_aliases (alias, company_id FK, kind, UNIQUE(alias, company_id))` — 別名、**僅 issuer aggregation 用、絕不當 instrument identity**
- **`portfoliodb/utils/ticker.py` 加 `canonical_ticker(raw, market_hint) → (canonical, unresolved_reason)`** — **唯一** normalization 來源、所有 write 入口應 route 經此（本次 wire 到 `order_service.create_order`、其他 service 留 future patch）
- **`canonical_ticker` 規則**：已有 `.TW`/`.TWO`/`.SI` suffix 不動；TW + 2/3 字頭裸數字 → +.TW；6/8/9 字頭裸數字 → unresolved（不猜上市 vs 上櫃、要 Sir 手動寫 suffix）；字母 ticker → 視為 US 不動
- **Migration `m001_canonical_ticker_and_instruments.py`**：dry-run + apply + log 到 `<APP_DIR>/migration_001.log`、idempotent 可重跑、第二次 apply 0 update
  - Backfill 結果：planned_orders ID 1 `2330` → `2330.TW`、ID 2 `2383` → `2383.TW`、holdings / transactions / price_cache 全 canonical 不動
  - Seed TSMC company + `TSMC_TW_COMMON` (2330.TW) + `TSMC_US_ADR` (TSM) + 4 aliases（台積電 / Taiwan Semiconductor / TSMC etc.）
  - 9 條 provisional instruments（NVDA / GOOG / 2337.TW / 2486.TW / 3481.TW / 3702.TW / 8021.TW / 8299.TWO / 2383.TW、instrument_id == ticker、company_id NULL）— notes 標 `"provisional"` 避免誤認
- **`review_orders` + `get_family_breakdown.pending_intents` 都走 canonical** — SQL JOIN 帶 `account.market` 當 hint、舊資料 runtime safety net
- **yfinance noise capture** — `fetch_prices` 用 `contextlib.redirect_stderr` 包 `yf.Ticker.fast_info`、known no-quote patterns（404 / "possibly delisted" / "Quote not found"）吞掉、未知 stderr replay、CLI 顯示 `[dim]Data warnings: ...[/dim]` 區塊不污染主 output
- **25 tests pass**（pytest 9.0.3、3.12s）— 覆蓋 Sir 列的 8 個 case + migration idempotency + alias 不可當 instrument key + 未知 stderr 不被吞、新增 `tests/conftest.py` tmp_db fixture 隔離正式 DB
- **不動**：models.py / accounts / holdings / transactions / cash_positions schema、4 broker、2 importer、holding_service / transaction_service / sync_service 主要 logic — 維持「最小修正、不擴大 scope」
- **未來可升級成完整 instrument master**：9 條 provisional 待 link company、`holding_service` / `transaction_service` 還沒 wire canonical_ticker、6/8/9 字頭 TW 數字 ticker 可接 TWSE / TPEx 公開資料源做精確判斷、`summary breakdown by issuer` 視圖
- **DB backup**：`portfolio.db.backup-20260526-160234`（migration apply 前 snapshot）

### 16:20 [MINI] 今日三筆 TW 成交入帳 + acct 3 永豐 cash 對齊 broker app
- **觸發**：Sir ship 永豐證券當日成交回報截圖、3 筆 TW 成交、總預估付 −NT$4,212,337
- **成交內容**：
  - 09:43:00 X0DQC **賣 2383 台光電 1,000 股 @ 5,280** — 實得 NT$5,256,636（扣 7,524 手續費 + 15,840 證交稅 0.3%）
  - 09:53:42 X0G0A **買 2472 立隆電 17,000 股 @ 296** — 實付 NT$5,039,170（含 7,170 手續費）— 新標的、之前 DB 沒這支
  - 09:19:49 X09O2 **買 3481 群創 90,000 股 @ 49.15** — 實付 NT$4,429,803（含 6,303 手續費）— 5/24 vision 灌資料時已預先記到 holdings、本次跳過避免 double-count
- **動作**：
  - `tx sell 3 2383.TW 1000 5280 --fee 7524 --tax 15840 --note "X0DQC 永豐 09:43"` — acct 3 永豐 2383 持股 10,000 → 9,000、avg_cost 1228.24 不變
  - `tx buy 3 2472.TW 17000 296 --fee 7170 --note "X0G0A 永豐 09:53"` — 新增 17,000 股 @ 296
  - 3481 群創 skip
- **Cash 對齊**：Sir 再 ship 兩張截圖（永豐銀行餘額 NT$4,754,075 @ 5/26 18:10、交割訊息 5/28 應付 −4,212,337 確認 T+2 schedule）。acct 3 之前無 TWD cash position record、執行 `cash set 3 TWD 4754075` 直接對齊 broker app current view
- **帳戶總值驗證**（`summary account 3`）：持股市值 NT$196,238,500 + 現金 NT$4,754,075 = **NT$200,992,575**、跟 broker app 「庫存試算 + 銀行餘額」一致（未交割前 view）
- **5/28 reconcile reminder**：交割日 broker 銀行帳會實扣 4,212,337、剩 541,738。那天 Sir 再給 broker 銀行餘額截圖、`cash set 3 TWD <新數字>` 重對齊。3481 那筆 cash flow（−4,429,803）DB 沒記、5/28 broker 結算後 DB 用 set 蓋過去即可 ^ck-260526-tx-canonical-cash-reconcile

### 16:30 [MINI] DB rebuild Phase 2 — 全 8 帳戶部位 + 現金入庫（截圖匯入）+ 永豐 Shioaji API 申請
- **Phase 2 目標**：Phase 1 建好 schema 後、Phase 2 把真實部位全填入
- **資料來源**：全截圖手動匯入（各券商 app 截圖 → JV 讀圖 → CLI 逐筆輸入）；永豐 Shioaji API 申請中、正式環境尚未開通
- **入庫結果（8 帳戶）**：
  - acct 1 富邦證：無持股（空）
  - acct 2 富邦銀：TWD 2,102,828 + USD 1.45
  - acct 3 永豐證：9 檔台股（2330/2337/2383/2472/2486/3481/3702/8021/8299）含均價
  - acct 4 永豐複委託：NVDA 6,029 股 @ USD 95.64
  - acct 5 永豐銀：TWD 6,978,639
  - acct 6 Firstrade：GOOG 1,170 @ USD 315.80、NVDA 2,381 @ USD 135.82、cash USD 120,108
  - acct 7 SCB-SG-ian：NVDA 17 @ USD 190.09、cash SGD 62.74
  - acct 8 SCB-SG-dad：NVDA 14,316 @ USD 209.78、TSM 1,575 @ USD 320.49、cash SGD 50,147.59
- **永豐 Shioaji 申請流程**：大戶豐 app 申請 API → 下載同意書 → 簽署 → 模擬環境測試（place_order 2890 成功）→ 正式環境等審核中；background polling script (sinopac_wait_production.py) 跑中，通過時 macOS 通知
- **均價公式**：永豐/富邦 TW 股：均價 = 現價 × 0.995575 − 損益/股數；Firstrade/SCB：均價 = 市值 − 損益 / 股數（無台灣稅）
- **schema 注意**：avg_cost 無 per-holding currency field、SCB-SG 帳戶內 USD 持股均價以 SGD label 顯示但數字正確（USD 原值）^ck-260705-phase2-holdings-import

### 14:39 [MINI] order add signed-shares + review retrospective + breakdown intent column + README + design doctrine
- **觸發**：跟 Athena 9 輪對話討論「加碼/減碼如何 model」、最終 ship list 5 條（同表 annotation / 一行 CLI / retrospective / 不擴 schema / doctrine 寫進文件）
- **CLI 改動**：
  - `order add` 改 signed shorthand：`+1000` = BUY、`-1000` = SELL；用 click `ignore_unknown_options` 解 `-1000` 被誤判為 flag 的問題；fallback 保留 `buy 1000` / `sell 500` explicit form（給 shell 吃掉 leading dash 的 edge case）
  - `order add` ticker auto-suffix：TW market account 內 `2330` 自動變 `2330.TW`（避免 breakdown intent JOIN key mismatch、上櫃要 explicit 寫 `8299.TWO`）
  - `order review --since N` 新指令：counts（PENDING/EXECUTED/CANCELLED）+ execution lag + 反覆出現的個股 + 未執行 plan + 當前股價對照
  - `summary breakdown` 個股 concentration table 加 `intent` column：JOIN PENDING orders、annotation 形式 `→加 1000 @1180` / `→減 1000 @5400`、沒 plan 的 cell 空白（zero visual cost）
- **Service 改動**：
  - `order_service.review_orders(since_days)`：4 個純機械 SQL stat、不做 LLM / ML / scoring（per Athena friction-minimization doctrine）
  - `order_service.create_order` 加 TW market ticker auto-suffix logic
  - `portfolio_service.get_family_breakdown` return 加 `pending_intents` field：dict[ticker → list of intent strings]
- **Doctrine 寫進 system_map.md**：「Speculative benefit vs concrete cost — 對 speculative benefit + concrete cost、default 不 hedge」— 未來 feature decision 的 filter、避免為 hedge 不確定的 alpha protection 而浪費 concrete time
- **README.md 新增**：第一次來看 repo 的人 / 未來重 visit 自己的 entry point；含 quickstart 5 行 command 走完 full workflow、tech stack、DB per-OS path、CLI 索引、ticker 規則、設計原則
- **Athena 9 輪過程的 meta lesson**（不入 git、見 memory）：Sir 第 1 輪直覺「做一起最方便」是對的、Athena framework 兩輪 over-engineered（friction-as-feature → minimax regret）、Sir 用「不需要為摩擦可能的好處浪費生命」拍板 reduce-friction direction。Conversation pattern = 壓力測試已有直覺、不是 think-out-loud find answer
- **沒改 schema**：planned_orders 既有 `reason TEXT` 一個 free text field 就夠、不擴 conviction_score / why_must / trigger / alternative ^ck-260526-order-signed-shorthand-retrospective
