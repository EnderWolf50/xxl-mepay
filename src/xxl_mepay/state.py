import json

import keyring
import keyring.errors

from xxl_mepay.models import ProgressData

PROGRESS_FILE = "progress.json"
SERVICE_NAME = "xxl_mepay"


def load_progress(filename: str = PROGRESS_FILE) -> ProgressData:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "processed_codes" in data and isinstance(data["processed_codes"], list):
                data["processed_codes"] = set(data["processed_codes"])
            else:
                data["processed_codes"] = set()
            if "reurl_links" in data and isinstance(data["reurl_links"], list):
                data["reurl_links"] = set(data["reurl_links"])
            else:
                data["reurl_links"] = set()
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {
            "email": None,
            "last_max_page": None,
            "processed_codes": set(),
            "reurl_links": set(),
        }


def save_progress(data: ProgressData, filename: str = PROGRESS_FILE) -> None:
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            {
                "email": data["email"],
                "last_max_page": data["last_max_page"],
                "processed_codes": list(data["processed_codes"]),
                "reurl_links": list(data["reurl_links"]),
            },
            f,
            indent=4,
            ensure_ascii=False,
        )


def get_previous_password(email: str | None) -> str | None:
    if email is None:
        return None

    try:
        return keyring.get_password(SERVICE_NAME, email)
    except keyring.errors.KeyringError:
        return None


def save_password(email: str, password: str) -> None:
    try:
        keyring.set_password(SERVICE_NAME, email, password)
    except keyring.errors.KeyringError:
        pass
