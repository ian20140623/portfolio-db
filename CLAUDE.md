# CLAUDE.md — portfolio-db

> 專案資訊見 system_map.md
> 共用指引與環境規則見 ../shared/CLAUDE.md、../shared/LOG_GUIDE.md ^ck-d33d9c-0


## 核心原則
SRP / Information Hiding / OCP / No Silent Workaround(遇阻停下報告不繞路) / Explicit Intent(做之前先宣告 scope)。詳見 [shared/ARCHITECTURE_PRINCIPLES.md](../shared/ARCHITECTURE_PRINCIPLES.md)。 ^ck-b7bced-1

## 環境需求
- Python: 見 .python-version
- pip 套件：yfinance, click, rich（見 requirements.txt）
- Lock files: requirements.txt ^ck-d33d9c-1

## 執行
- `python -m portfoliodb <command>`
- DB 在 AppData（不在 OneDrive），credentials.json 不進 git ^ck-d33d9c-2

## 開 Session 流程
每次新對話開始，在回應用戶之前，先執行：
1. `git fetch && git log origin/master --oneline -10`（掌握跨機器最近變更）
2. 讀 `system_map.md`（如果存在，掌握系統現狀）
3. 讀 `log_chronological.md` 最後 10 筆（如果存在，掌握決策脈絡）
4. 讀 `ROADMAP.md`（如果存在，掌握開發方向）
5. 如果 ROADMAP.md 存在，讀完後問用戶：「目前 ROADMAP 的優先順序要不要調整？」
以上檔案不存在就跳過，不要報錯。
每個步驟都要向用戶顯示目前正在做什麼（例如「正在讀取 system_map.md...」）。 ^ck-d33d9c-3

## Scratch 規則
見 ../shared/CLAUDE.md「環境注意」 ^ck-d33d9c-4

## 收工：LCP

見 ../shared/CLAUDE.md（含 ROADMAP 同步規則） ^ck-d33d9c-5

## 家族財富規劃 context（sensitive、不入 git）

Family wealth planning 議題（含借名 unwind / Athena framework / Level 0-4 action ladder / Silent Protector pattern）的 distilled context、存於 Claude Code project memory：

- **真實 file 位置**：`~/Library/CloudStorage/Dropbox/PJHub/portfolio-db/memory/`（跨機器 Dropbox sync、不被 ks watcher vectorize）
- **Claude Code auto-load**：`~/.claude/projects/-Users-ianchang-Projects-portfolio-db/memory` symlink → 上面
- **未來 AI 行為**：開 session 時 Claude Code 自動 load MEMORY.md + 4 個 `draft_*.md`、不要重新發明 framework / 不要從頭跟 Sir 重講

跨機器（NB / Air）開 portfolio-db 時、若 Claude Code memory symlink 尚未 setup、跑：
```
ln -s ~/Library/CloudStorage/Dropbox/PJHub/portfolio-db/memory ~/.claude/projects/-Users-ianchang-Projects-portfolio-db/memory
``` ^ck-family-memory-pointer
