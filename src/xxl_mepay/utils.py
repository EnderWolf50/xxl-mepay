from colorama import Fore, Style


def tip(message: str, prefix: str = "TIP") -> None:
    print(f"{Style.BRIGHT}{Fore.WHITE}[{prefix}] {message}{Style.RESET_ALL}")


def info(message: str, prefix: str = "INFO") -> None:
    print(f"{Fore.BLUE}[{prefix}] {message}{Style.RESET_ALL}")


def error(message: str, prefix: str = "ERROR") -> None:
    print(f"{Fore.RED}[{prefix}] {message}{Style.RESET_ALL}")


def warning(message: str, prefix: str = "WARNING") -> None:
    print(f"{Fore.YELLOW}[{prefix}] {message}{Style.RESET_ALL}")


def skip(message: str) -> None:
    warning(message, "SKIP")


def success(message: str, prefix: str = "SUCCESS") -> None:
    print(f"{Fore.GREEN}[{prefix}] {message}{Style.RESET_ALL}")


def result(message: str) -> None:
    success(message, "RESULT")
