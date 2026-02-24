"""Broker API credentials configuration.

Credentials are stored in a JSON file outside OneDrive for security.
Path: ~/AppData/Local/PortfolioDB/credentials.json

Example credentials.json:
{
    "sinopac": {
        "api_key": "YOUR_API_KEY",
        "secret_key": "YOUR_SECRET_KEY",
        "ca_path": "C:/path/to/Sinopac.pfx",
        "ca_password": "YOUR_ID_NUMBER",
        "person_id": "YOUR_ID_NUMBER"
    },
    "fubon": {
        "user_id": "YOUR_USER_ID",
        "password": "YOUR_PASSWORD",
        "pfx_path": "C:/path/to/fubon_cert.pfx",
        "pfx_password": "YOUR_PFX_PASSWORD"
    }
}
"""

import json
from pathlib import Path

CREDENTIALS_DIR = Path.home() / "AppData" / "Local" / "PortfolioDB"
CREDENTIALS_PATH = CREDENTIALS_DIR / "credentials.json"


def load_credentials(broker: str) -> dict:
    """Load credentials for a specific broker.

    Args:
        broker: "sinopac" or "fubon"

    Returns:
        Dict of credential key-value pairs.

    Raises:
        FileNotFoundError: If credentials.json doesn't exist.
        KeyError: If the broker section is missing.
    """
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"Credentials file not found at {CREDENTIALS_PATH}\n"
            f"Please create it with your API keys. See documentation for format."
        )

    with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
        all_creds = json.load(f)

    if broker not in all_creds:
        raise KeyError(
            f"No credentials found for '{broker}' in {CREDENTIALS_PATH}\n"
            f"Available brokers: {', '.join(all_creds.keys())}"
        )

    return all_creds[broker]


def save_credentials(broker: str, credentials: dict) -> None:
    """Save or update credentials for a broker."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)

    all_creds = {}
    if CREDENTIALS_PATH.exists():
        with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
            all_creds = json.load(f)

    all_creds[broker] = credentials

    with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
        json.dump(all_creds, f, indent=2, ensure_ascii=False)


def has_credentials(broker: str) -> bool:
    """Check if credentials exist for a broker."""
    if not CREDENTIALS_PATH.exists():
        return False
    with open(CREDENTIALS_PATH, "r", encoding="utf-8") as f:
        all_creds = json.load(f)
    return broker in all_creds
