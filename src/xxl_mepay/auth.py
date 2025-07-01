import httpx

from xxl_mepay.models import LoginResponse


async def login(email: str, password: str) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://www.mepay.com.tw/api/auth/login",
            json={"email": email, "password": password, "remember": 0},
        )
        if res.status_code != 200:
            raise Exception("Login failed")

        json: LoginResponse = res.json()
        if not json.get("success", False):
            raise Exception("Login failed")

        token = res.json()["data"]["token"]
        return token
