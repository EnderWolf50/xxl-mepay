from colorama import Fore, Style


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
