"""SinoPac Securities (永豐金證券) integration via Shioaji API.

Prerequisites:
    1. pip install shioaji
    2. Apply for API Key at SinoPac (need to visit branch in person)
    3. Download Sinopac.pfx certificate
    4. Add credentials to ~/AppData/Local/PortfolioDB/credentials.json:
       {
           "sinopac": {
               "api_key": "YOUR_API_KEY",
               "secret_key": "YOUR_SECRET_KEY",
               "ca_path": "C:/path/to/Sinopac.pfx",
               "ca_password": "YOUR_ID_NUMBER"
           }
       }

Usage:
    broker = SinoPacBroker()
    broker.login()
    holdings = broker.get_holdings()
    balance = broker.get_balance()
    broker.logout()
"""

from portfoliodb.brokers.config import load_credentials


class SinoPacBroker:
    """Interface to SinoPac Securities via Shioaji."""

    def __init__(self):
        self.api = None
        self._logged_in = False

    def login(self) -> None:
        """Login to Shioaji API using stored credentials."""
        try:
            import shioaji as sj
        except ImportError:
            raise ImportError(
                "Shioaji is not installed. Run: pip install shioaji[speed]"
            )

        creds = load_credentials("sinopac")
        self.api = sj.Shioaji()
        self.api.login(
            api_key=creds["api_key"],
            secret_key=creds["secret_key"],
        )

        # Activate certificate for account queries
        if "ca_path" in creds:
            self.api.activate_ca(
                ca_path=creds["ca_path"],
                ca_passwd=creds.get("ca_password", ""),
            )

        self._logged_in = True

    def logout(self) -> None:
        """Logout from Shioaji."""
        if self.api and self._logged_in:
            self.api.logout()
            self._logged_in = False

    def _ensure_logged_in(self):
        if not self._logged_in:
            raise RuntimeError("Not logged in. Call login() first.")

    def get_holdings(self) -> list[dict]:
        """Get current stock holdings.

        Returns list of dicts:
            [{"ticker": "2330.TW", "shares": 1000, "avg_cost": 580.5,
              "last_price": 1915.0, "pnl": 1334500.0}, ...]
        """
        self._ensure_logged_in()
        positions = self.api.list_positions(self.api.stock_account)

        holdings = []
        for pos in positions:
            # Shioaji returns code like "2330", we append ".TW"
            ticker = f"{pos.code}.TW"
            shares = pos.quantity
            # direction: "Buy" means long position
            if pos.direction.value == "Sell":
                shares = -shares

            holdings.append({
                "ticker": ticker,
                "shares": float(shares),
                "avg_cost": float(pos.price),
                "last_price": float(pos.last_price) if hasattr(pos, 'last_price') else None,
                "pnl": float(pos.pnl) if hasattr(pos, 'pnl') else None,
            })

        return holdings

    def get_balance(self) -> dict:
        """Get account cash balance.

        Returns:
            {"balance": 500000.0, "currency": "TWD", "date": "2026-02-21"}
        """
        self._ensure_logged_in()
        bal = self.api.account_balance()

        return {
            "balance": float(bal.acc_balance),
            "currency": "TWD",
            "date": str(bal.date) if hasattr(bal, 'date') else None,
        }

    def get_margin(self) -> dict | None:
        """Get futures/options margin info (if applicable)."""
        self._ensure_logged_in()
        try:
            margin = self.api.margin(self.api.futopt_account)
            return {
                "equity": float(margin.equity),
                "available_margin": float(margin.available_margin),
                "today_balance": float(margin.today_balance),
            }
        except Exception:
            return None
