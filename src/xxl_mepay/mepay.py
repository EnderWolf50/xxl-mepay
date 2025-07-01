import re
from typing import cast

import httpx

from xxl_mepay.models import (
    GetSupportUserCodeFailedData,
    GetSupportUserCodeResponse,
    GetSupportUserCodeSuccessData,
    SupportUserData,
    SupportUserResult,
)

_SUPPORTED_PATTERN = re.compile(r".+ 已應援過 (.+)，不可重複應援。")


def get_support_user_data(
    client: httpx.Client, support_code: str
) -> SupportUserData | None:
    res = client.get(f"https://www.mepay.com.tw/api/xxl/friendSupport/{support_code}")
    if res.status_code == 405:
        return None

    json: GetSupportUserCodeResponse = res.json()

    data = json.get("data")
    if "message" in data:
        data = cast(GetSupportUserCodeFailedData, data)
        message = data["message"]

        if message == "無法應援自己":
            return {"username": "自己", "support_user_code": None}

        match = _SUPPORTED_PATTERN.match(message)
        assert match is not None

        return {"username": match.group(1), "support_user_code": None}

    data = cast(GetSupportUserCodeSuccessData, data)
    return {
        "username": data["user"]["nickname"],
        "support_user_code": data["support_user_code"],
    }


def support_user(mepay_token: str, support_code: str) -> SupportUserResult:
    with httpx.Client(headers={"Authorization": f"Bearer {mepay_token}"}) as client:
        support_user_data = get_support_user_data(client, support_code)
        if support_user_data is None:
            return {
                "success": False,
                "message": "未知的錯誤，可能是連結有誤",
                "support_code": support_code,
                "username": None,
                "support_user_code": None,
            }

        username = support_user_data["username"]
        support_user_code = support_user_data["support_user_code"]
        if support_user_code is None:
            return {
                "success": False,
                "message": f"已應援過 {username}",
                "support_code": support_code,
                **support_user_data,
            }

        support_res = client.post(
            "https://www.mepay.com.tw/api/xxl/friendSupport",
            json={"support_user_code": support_user_code},
        )
        if support_res.status_code != 200:
            return {
                "success": False,
                "message": "未知的錯誤，可能是伺服器有問題",
                "support_code": support_code,
                **support_user_data,
            }

        return {
            "success": True,
            "message": f"成功應援 {username}",
            "support_code": support_code,
            **support_user_data,
        }
