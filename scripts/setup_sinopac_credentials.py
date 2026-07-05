"""設定永豐金 Shioaji API 憑證（互動式）。

執行：python3 scripts/setup_sinopac_credentials.py
"""

import json
import sys
from pathlib import Path

APP_DIR = Path.home() / "Library" / "Application Support" / "PortfolioDB"
CREDS_PATH = APP_DIR / "credentials.json"


def main():
    print("=== 永豐金 Shioaji API 憑證設定 ===\n")
    print(f"憑證將存入：{CREDS_PATH}\n")

    api_key = input("請貼上 api_key：").strip()
    secret_key = input("請貼上 secret_key：").strip()

    if not api_key or not secret_key:
        print("❌ api_key / secret_key 不能空白")
        sys.exit(1)

    APP_DIR.mkdir(parents=True, exist_ok=True)

    existing = {}
    if CREDS_PATH.exists():
        with open(CREDS_PATH, encoding="utf-8") as f:
            existing = json.load(f)

    existing["sinopac"] = {
        "api_key": api_key,
        "secret_key": secret_key,
    }

    with open(CREDS_PATH, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 已寫入 {CREDS_PATH}")
    print("   可用 `python3 -m portfoliodb sync credentials sinopac` 確認狀態")


if __name__ == "__main__":
    main()
