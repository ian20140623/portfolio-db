"""背景輪詢永豐正式環境，通了就推播通知。

執行：python3 scripts/sinopac_wait_production.py &
"""

import sys
import time
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from portfoliodb.brokers.config import load_credentials

CHECK_INTERVAL = 900  # 15 分鐘


def notify(title, message):
    subprocess.run([
        "osascript", "-e",
        f'display notification "{message}" with title "{title}" sound name "Glass"'
    ])


def check_production():
    try:
        import shioaji as sj
        creds = load_credentials("sinopac")
        api = sj.Shioaji()
        api.login(api_key=creds["api_key"], secret_key=creds["secret_key"])
        accounts = api.list_accounts()
        api.logout()
        return True, accounts
    except Exception as e:
        return False, str(e)


def main():
    print("開始輪詢永豐正式環境（每 15 分鐘）...", flush=True)
    attempt = 0
    while True:
        attempt += 1
        ok, result = check_production()
        ts = time.strftime("%H:%M")
        if ok:
            print(f"[{ts}] ✅ 正式環境已開通！{result}", flush=True)
            notify("永豐 API 開通", "正式環境已可使用，可開始同步部位")
            break
        else:
            print(f"[{ts}] 第 {attempt} 次：尚未開通，{CHECK_INTERVAL//60} 分鐘後再試", flush=True)
            time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
