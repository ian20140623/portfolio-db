"""確認永豐正式環境是否已開通。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import shioaji as sj
from portfoliodb.brokers.config import load_credentials

creds = load_credentials("sinopac")
api = sj.Shioaji()
api.login(api_key=creds["api_key"], secret_key=creds["secret_key"])
for acc in api.list_accounts():
    print(acc)
api.logout()
