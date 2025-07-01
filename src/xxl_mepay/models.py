from dataclasses import dataclass
from typing import TypedDict


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


class SupportUserData(TypedDict):
    username: str | None
    support_user_code: str | None


class SupportUserResult(TypedDict):
    success: bool
    message: str
    support_code: str
    username: str | None
    support_user_code: str | None


class ProgressData(TypedDict):
    email: str | None
    last_max_page: int | None
    processed_codes: set[str]


@dataclass(frozen=True)
class CollectedResult:
    max_page: int
    support_codes: set[str]
