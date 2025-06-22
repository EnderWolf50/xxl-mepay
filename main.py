import asyncio
import json
import re
from dataclasses import dataclass
from typing import TypedDict, cast
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup
from colorama import Fore, Style

PROGRESS_FILE = "progress.json"
SUPPORT_CODE_PATTERN = re.compile(
    r"https://www\.mepay\.com\.tw/XXL\?supportCode=([a-zA-Z0-9=]+)"
)
SUPPORTED_PATTERN = re.compile(r".+ 已應援過 (.+)，不可重複應援。")


class LoginResponseData(TypedDict):
    message: str
    token: str


class ApiResponse(TypedDict):
    code: int
    locale: str
    message: str
    success: bool


class LoginResponse(ApiResponse):
    data: LoginResponseData


class GetSupportUserCodeSuccessUserData(TypedDict):
    email: str
    id: int
    nickname: str
    username: str


class GetSupportUserCodeSuccessData(TypedDict):
    support_user_code: str
    user: GetSupportUserCodeSuccessUserData


class GetSupportUserCodeFailedData(TypedDict):
    message: str


class GetSupportUserCodeResponse(ApiResponse):
    data: GetSupportUserCodeSuccessData | GetSupportUserCodeFailedData


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


def extract_support_codes(text: str) -> set[str]:
    return set(SUPPORT_CODE_PATTERN.findall(text))


def extract_support_codes_in_page(soup: BeautifulSoup) -> set[str]:
    extracted_codes: set[str] = set()

    contents = soup.select(".c-post__body .c-article .c-article__content")
    for content in contents:
        content_text = content.get_text()
        extracted_codes.update(extract_support_codes(content_text))

    return extracted_codes


def parse_page_number_from_url(url: str) -> int:
    parsed_url = urlparse(url)
    query_params = parse_qs(parsed_url.query)
    page_param = query_params.get("page")
    if page_param is None:
        raise ValueError("Page parameter not found in URL")
    try:
        return int(page_param[0])
    except ValueError:
        raise ValueError("Page parameter is not a valid integer")


def get_max_page_number(soup: BeautifulSoup) -> int:
    page_numbers = []
    pagination = soup.select_one("p.BH-pagebtnA")
    if pagination is None:
        return 1

    pages = pagination.select("a")
    for page in pages:
        page_class = page.get("class")
        if isinstance(page_class, list) and "pagenow" in page_class:
            page_numbers.append(int(page.get_text()))
            continue

        href = page.get("href")
        if not isinstance(href, str) or "?page=" not in href:
            continue
        try:
            page_number = parse_page_number_from_url(href)
            page_numbers.append(page_number)
        except ValueError:
            continue

    return max(page_numbers) if page_numbers else 1


@dataclass(frozen=True)
class CollectedResult:
    max_page: int
    support_codes: set[str]


async def collect_first_floor_comment_support_codes(
    client: httpx.AsyncClient,
) -> set[str]:
    res = await client.get(
        "https://forum.gamer.com.tw/ajax/moreCommend.php",
        params={"bsn": "80107", "snB": "161"},
    )
    if res.status_code != 200:
        return set()

    data: dict[str, dict[str, str | int] | int] = res.json()

    comments = set()
    for value in data.values():
        if isinstance(value, int):
            continue

        comment = value.get("comment")
        if comment is None or not isinstance(comment, str):
            continue
        comments.update(extract_support_codes(comment))

    return comments


async def collect_max_page_and_support_codes(
    start_page: int = 1,
) -> CollectedResult:
    codes: set[str] = set()
    base_url = "https://forum.gamer.com.tw/C.php"
    base_params = {"bsn": "80107", "snA": "67"}

    async with httpx.AsyncClient() as client:
        first_page_res = await client.get(
            base_url, params={**base_params, "page": start_page}
        )
        first_page_soup = BeautifulSoup(first_page_res.text, "html.parser")

        first_page_codes = extract_support_codes_in_page(first_page_soup)
        codes.update(first_page_codes)

        first_floor_comment_codes = await collect_first_floor_comment_support_codes(
            client
        )
        codes.update(first_floor_comment_codes)

        max_page = get_max_page_number(first_page_soup)

        tasks = [
            client.get(base_url, params={**base_params, "page": page_num})
            for page_num in range(max(2, start_page), max_page + 1)
        ]
        if not tasks:
            return CollectedResult(max_page, codes)

        page_responses: list[httpx.Response] = await asyncio.gather(*tasks)
        for page_res in page_responses:
            page_soup = BeautifulSoup(page_res.text, "html.parser")
            page_codes = extract_support_codes_in_page(page_soup)
            codes.update(page_codes)

    return CollectedResult(max_page, codes)


class SupportUserData(TypedDict):
    username: str | None
    support_user_code: str | None


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

        match = SUPPORTED_PATTERN.match(message)
        assert match is not None

        return {"username": match.group(1), "support_user_code": None}

    data = cast(GetSupportUserCodeSuccessData, data)
    return {
        "username": data["user"]["nickname"],
        "support_user_code": data["support_user_code"],
    }


class SupportUserResult(TypedDict):
    success: bool
    message: str
    support_code: str
    username: str | None
    support_user_code: str | None


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


class ProgressData(TypedDict):
    last_max_page: int | None
    processed_codes: set[str]


def load_progress(filename: str = PROGRESS_FILE) -> ProgressData:
    """Loads progress data from a JSON file."""
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            if "processed_codes" in data and isinstance(data["processed_codes"], list):
                data["processed_codes"] = set(data["processed_codes"])
            else:
                data["processed_codes"] = set()
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return {"last_max_page": None, "processed_codes": set()}


def save_progress(data: ProgressData, filename: str = PROGRESS_FILE) -> None:
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(
            {
                "last_max_page": data["last_max_page"],
                "processed_codes": list(data["processed_codes"]),
            },
            f,
            indent=4,
            ensure_ascii=False,
        )


def tip(message: str) -> None:
    print(f"{Style.BRIGHT}{Fore.WHITE}[TIP] {message}{Style.RESET_ALL}")


def info(message: str) -> None:
    print(f"{Fore.BLUE}[INFO] {message}{Style.RESET_ALL}")


def error(message: str) -> None:
    print(f"{Fore.RED}[ERROR] {message}{Style.RESET_ALL}")


def skip(message: str) -> None:
    print(f"{Fore.YELLOW}[SKIP] {message}{Style.RESET_ALL}")


def result(message: str) -> None:
    print(f"{Fore.GREEN}[RESULT] {message}{Style.RESET_ALL}")


async def main() -> None:
    email = input("請輸入你的魔儲信箱: ")
    if not email.strip():
        raise ValueError("信箱不能為空")
    password = input("請輸入你的魔儲密碼: ")
    if not password.strip():
        raise ValueError("密碼不能為空")

    tip("可以使用 Ctrl + C 停止運行（沒用的話可以多點幾次）")
    progress = load_progress()

    last_max_page = progress["last_max_page"]
    processed_codes = progress["processed_codes"]

    info("抓取最新應援碼...")
    collected_result = await collect_max_page_and_support_codes(
        last_max_page if last_max_page is not None else 1
    )

    info(f"先前最後抓取頁數: {last_max_page}")
    info(f"先前已處理應援碼數: {len(processed_codes)}")
    info(f"本次抓取頁數: {collected_result.max_page}")
    info(f"本次抓取應援碼數: {len(collected_result.support_codes)}")

    mepay_token = await login(email, password)
    for support_code in collected_result.support_codes:
        if support_code in processed_codes:
            skip(f"已有應援紀錄，跳過: {support_code}")
            continue

        support_result = support_user(mepay_token, support_code)

        processed_codes |= {support_code}
        save_progress(
            {"last_max_page": last_max_page, "processed_codes": processed_codes}
        )

        result(support_result["message"])

    save_progress(
        {"last_max_page": collected_result.max_page, "processed_codes": processed_codes}
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        error("已停止運行")
    except Exception as e:
        error(f"發生錯誤: {e}")
    finally:
        input("按 Enter 鍵以關閉程式...")
