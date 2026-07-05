"""永豐 Shioaji 模擬環境測試 — 通過後才能開通正式環境。

執行：python3 scripts/sinopac_sim_test.py
開盤時間（09:00-13:30）跑效果最好，報價有效、委託不會被退。
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import shioaji as sj
from portfoliodb.brokers.config import load_credentials


def main():
    creds = load_credentials("sinopac")

    print("1. 登入模擬環境...")
    api = sj.Shioaji(simulation=True)
    api.login(api_key=creds["api_key"], secret_key=creds["secret_key"])
    print("   ✅ 登入成功")

    accounts = api.list_accounts()
    stock_acc = next(
        (a for a in accounts if "IntlAccount" not in type(a).__name__), None
    )
    if not stock_acc:
        print("❌ 找不到股票帳戶")
        api.logout()
        return

    print(f"   帳戶：{stock_acc.account_id} ({stock_acc.username})")
    api.set_default_account(stock_acc)
    time.sleep(1)

    print("\n2. 抓即時報價（2890 永豐金控）...")
    contract = api.Contracts.Stocks["2890"]
    snapshot = api.snapshots([contract])
    if snapshot and snapshot[0].close > 0:
        price = snapshot[0].close
        print(f"   最新成交價：{price}")
    else:
        price = 25.0  # fallback
        print(f"   無法取得即時價，使用預設 {price}")

    print(f"\n3. 下測試買單，價格 {price}（模擬，不會真的成交）...")
    order = api.Order(
        price=price,
        quantity=1,
        action=sj.Action.Buy,
        price_type=sj.StockPriceType.LMT,
        order_type=sj.OrderType.ROD,
        order_lot=sj.StockOrderLot.Common,
        account=stock_acc,
    )
    trade = api.place_order(contract, order)
    status = trade.status.status if trade else "unknown"
    print(f"   委託狀態：{status}")

    if "PendingSubmit" in str(status) or "Submitted" in str(status):
        print("   ✅ 委託送出成功")
    else:
        print(f"   ⚠️  委託狀態：{trade}")

    time.sleep(2)
    api.logout()

    print("\n✅ 測試完成。等 5 分鐘後執行：")
    print("   python3 ~/Projects/portfolio-db/scripts/sinopac_check_production.py")


if __name__ == "__main__":
    main()
