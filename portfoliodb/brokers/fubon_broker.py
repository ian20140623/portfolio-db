"""Fubon Securities (富邦證券) integration via Fubon Neo API.

Prerequisites:
    1. Download and install fubon_neo .whl from Fubon's API page
       (https://www.fbs.com.tw/TradeAPI/)
    2. Apply for API service and download certificate
    3. Add credentials to ~/AppData/Local/PortfolioDB/credentials.json:
       {
           "fubon": {
               "user_id": "YOUR_USER_ID",
               "password": "YOUR_PASSWORD",
               "pfx_path": "C:/path/to/fubon_cert.pfx",
               "pfx_password": "YOUR_PFX_PASSWORD"
           }
       }

Usage:
    broker = FubonBroker()
    broker.login()
    holdings = broker.get_holdings()
    balance = broker.get_balance()
"""

from portfoliodb.brokers.config import load_credentials


class FubonBroker:
    """Interface to Fubon Securities via Fubon Neo SDK."""

    def __init__(self):
        self.sdk = None
        self.accounts = None
        self._logged_in = False

    def login(self) -> None:
        """Login to Fubon Neo API using stored credentials."""
        try:
            from fubon_neo.sdk import FubonSDK
        except ImportError:
            raise ImportError(
                "Fubon Neo SDK is not installed.\n"
                "Download the .whl file from https://www.fbs.com.tw/TradeAPI/\n"
                "Then run: pip install fubon_neo-<version>.whl"
            )

        creds = load_credentials("fubon")
        self.sdk = FubonSDK()
        self.accounts = self.sdk.login(
            creds["user_id"],
            creds["password"],
            creds.get("pfx_path", ""),
            creds.get("pfx_password", ""),
        )
        self._logged_in = True

    def _ensure_logged_in(self):
        if not self._logged_in:
            raise RuntimeError("Not logged in. Call login() first.")

    def _get_account(self):
        """Get the first available stock account."""
        if self.accounts and hasattr(self.accounts, 'data'):
            account_list = self.accounts.data
            if account_list:
                return account_list[0]
        raise RuntimeError("No trading accounts found")

    def get_holdings(self) -> list[dict]:
        """Get current stock holdings with unrealized P&L.

        Returns list of dicts:
            [{"ticker": "2330.TW", "shares": 1000, "avg_cost": 580.5,
              "last_price": 1915.0, "pnl": 1334500.0}, ...]
        """
        self._ensure_logged_in()
        account = self._get_account()

        # Use unrealized_gains_and_loses for detailed position data
        result = self.sdk.accounting.unrealized_gains_and_loses(account)

        holdings = []
        if result.is_success and result.data:
            for item in result.data:
                ticker = f"{item.stock_no}.TW" if hasattr(item, 'stock_no') else f"{item.symbol}.TW"
                shares = float(getattr(item, 'quantity', 0) or getattr(item, 'qty', 0))
                avg_cost = float(getattr(item, 'cost_price', 0) or getattr(item, 'price', 0))
                last_price = float(getattr(item, 'market_price', 0) or 0)
                pnl = float(getattr(item, 'unrealized_profit', 0) or getattr(item, 'pnl', 0))

                holdings.append({
                    "ticker": ticker,
                    "shares": shares,
                    "avg_cost": avg_cost,
                    "last_price": last_price,
                    "pnl": pnl,
                })

        return holdings

    def get_balance(self) -> dict:
        """Get bank cash balance.

        Returns:
            {"balance": 500000.0, "currency": "TWD"}
        """
        self._ensure_logged_in()
        account = self._get_account()

        result = self.sdk.accounting.bank_remain(account)

        balance = 0.0
        if result.is_success and result.data:
            balance = float(result.data)

        return {
            "balance": balance,
            "currency": "TWD",
        }

    def get_inventories(self) -> list[dict]:
        """Get raw inventory data (alternative to get_holdings)."""
        self._ensure_logged_in()
        account = self._get_account()

        result = self.sdk.accounting.inventories(account)

        items = []
        if result.is_success and result.data:
            for item in result.data:
                items.append({
                    "raw": str(item),
                    "ticker": getattr(item, 'stock_no', None) or getattr(item, 'symbol', None),
                    "shares": getattr(item, 'quantity', None) or getattr(item, 'qty', None),
                })

        return items
