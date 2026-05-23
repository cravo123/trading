from schwab.auth import client_from_manual_flow

from trading.config import AuthenConfig


def main() -> None:
    client_from_manual_flow(
        AuthenConfig.api_key,
        AuthenConfig.app_secret,
        AuthenConfig.callback_url,
        AuthenConfig.token_path,
    )


if __name__ == "__main__":
    main()
