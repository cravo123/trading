from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd
from schwab.auth import client_from_token_file
from schwab.orders.common import Duration, Session
from schwab.orders.equities import (
    equity_buy_limit,
    equity_buy_market,
    equity_buy_to_cover_limit,
    equity_buy_to_cover_market,
    equity_sell_limit,
    equity_sell_market,
    equity_sell_short_limit,
    equity_sell_short_market,
)
from tenacity import retry, stop_after_attempt, wait_fixed

from trading.config import AuthenConfig

# client_id incrementer
IB_COUNTER = None
IB_SLEEP = 0.01


@dataclass
class QuoteData:
    """
    Get quote data
    """

    symbol: str
    quote_time: datetime
    last_price: float
    bid_price: float
    bid_size: int
    ask_price: float
    ask_size: int
    volume: float = np.nan
    min_tick: float = 0.01


def _float_to_str(
    price: float,
) -> str:
    res = f"{price:.2f}"

    return res


class SchwabTrader:
    def __init__(self) -> None:
        # Create schwab client
        self._client = client_from_token_file(
            AuthenConfig.token_path,
            AuthenConfig.api_key,
            AuthenConfig.app_secret,
        )

        self.account_id, self.account_hash = self._get_account_id()

    def _get_account_id(self) -> tuple[str, str]:
        res = self._client.get_account_numbers().json()[0]
        return res["accountNumber"], res["hashValue"]

    def get_cash(self):
        res = self._client.get_account(self.account_hash).json()
        cash = res["securitiesAccount"]["currentBalances"]["cashBalance"]

        return cash

    def get_aum(self):
        res = self._client.get_account(self.account_hash).json()
        aum = res["securitiesAccount"]["currentBalances"]["liquidationValue"]

        return aum

    def get_position(
        self,
        symbol: str,
    ):
        res = self._client.get_account(self.account_hash, fields=self._client.Account.Fields.POSITIONS).json()
        positions = res["securitiesAccount"]
        if "positions" not in positions:
            return 0
        positions = positions["positions"]
        positions = [p for p in positions if p.get("instrument", {}).get("symbol", "").upper() == symbol.upper()]

        positions = positions[0] if len(positions) > 0 else {}
        shares = positions.get("longQuantity", 0) - positions.get("shortQuantity", 0)

        return shares

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def get_quote(
        self,
        symbol: str,
    ):
        symbol = symbol.upper()
        res = self._client.get_quote(symbol)
        d = res.json()[symbol]
        q = d["quote"]
        quote = QuoteData(
            d["symbol"],
            pd.to_datetime(q["quoteTime"], unit="ms", utc=True)
            .tz_convert("America/New_York")
            .to_pydatetime()
            .replace(tzinfo=None),
            q["lastPrice"],
            q["bidPrice"],
            q["bidSize"],
            q["askPrice"],
            q["askSize"],
        )

        return quote

    def buy_market(
        self,
        symbol: str,
        quantity: int,
    ):
        res = self._client.place_order(self.account_hash, equity_buy_market(symbol, quantity))
        return res

    def sell_market(
        self,
        symbol: str,
        quantity: int,
    ):
        res = self._client.place_order(self.account_hash, equity_sell_market(symbol, quantity))
        return res

    def buy_limit(
        self,
        symbol: str,
        quantity: int,
        target_price: float,
    ):
        res = self._client.place_order(
            self.account_hash,
            (
                equity_buy_limit(symbol, quantity, _float_to_str(target_price))
                .set_duration(Duration.GOOD_TILL_CANCEL)
                .set_session(Session.SEAMLESS)
            ),
        )
        return res

    def sell_limit(
        self,
        symbol: str,
        quantity: int,
        target_price: float,
    ):
        res = self._client.place_order(
            self.account_hash,
            (
                equity_sell_limit(symbol, quantity, _float_to_str(target_price))
                .set_duration(Duration.GOOD_TILL_CANCEL)
                .set_session(Session.SEAMLESS)
            ),
        )
        return res

    def sell_short_limit(
        self,
        symbol: str,
        quantity: int,
        target_price: float,
    ):
        res = self._client.place_order(
            self.account_hash,
            (
                equity_sell_short_limit(symbol, quantity, _float_to_str(target_price))
                .set_duration(Duration.GOOD_TILL_CANCEL)
                .set_session(Session.SEAMLESS)
            ),
        )
        return res

    def buy_to_cover_limit(
        self,
        symbol: str,
        quantity: int,
        target_price: float,
    ):
        res = self._client.place_order(
            self.account_hash,
            (
                equity_buy_to_cover_limit(symbol, quantity, _float_to_str(target_price))
                .set_duration(Duration.GOOD_TILL_CANCEL)
                .set_session(Session.SEAMLESS)
            ),
        )
        return res

    def sell_short_market(
        self,
        symbol: str,
        quantity: int,
    ):
        res = self._client.place_order(
            self.account_hash,
            (
                equity_sell_short_market(symbol, quantity)
                .set_duration(Duration.GOOD_TILL_CANCEL)
                .set_session(Session.SEAMLESS)
            ),
        )
        return res

    def buy_to_cover_market(
        self,
        symbol: str,
        quantity: int,
    ):
        res = self._client.place_order(
            self.account_hash,
            (
                equity_buy_to_cover_market(symbol, quantity)
                .set_duration(Duration.GOOD_TILL_CANCEL)
                .set_session(Session.SEAMLESS)
            ),
        )
        return res

    def close_position(
        self,
        symbol: str,
        slippage: float = 0.02,
    ):
        curr_pos = self.get_position(symbol)
        if curr_pos > 0:
            # sell to close
            target_price = self.get_quote(symbol).bid_price - slippage
            return self.sell_limit(symbol, curr_pos, target_price)

        if curr_pos < 0:
            # buy to cover
            target_price = self.get_quote(symbol).ask_price + slippage
            return self.buy_to_cover_limit(symbol, -curr_pos, target_price)

        return

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    def get_price_history(
        self,
        symbol: str,
        start_date: date | datetime | str | None = None,
        end_date: date | datetime | str | None = None,
        frequency: str = "1d",
    ) -> pd.DataFrame:
        symbol = symbol.upper()
        frequency = frequency.lower()

        apis = {
            "1d": self._client.get_price_history_every_day,
            "1min": self._client.get_price_history_every_minute,
            "5min": self._client.get_price_history_every_five_minutes,
            "10min": self._client.get_price_history_every_ten_minutes,
            "15min": self._client.get_price_history_every_fifteen_minutes,
            "30min": self._client.get_price_history_every_thirty_minutes,
        }

        assert frequency in apis, "Only support above frequency queries."

        select_api = apis[frequency]

        if end_date is None:
            end_date = start_date

        start_date = pd.to_datetime(start_date)
        end_date = pd.to_datetime(end_date)

        res = select_api(
            symbol=symbol,
            start_datetime=start_date,
            end_datetime=end_date,
        )
        res = res.json()

        df = pd.DataFrame(res["candles"])

        df["symbol"] = res["symbol"]
        df["datetime"] = pd.to_datetime(df["datetime"], unit="ms", utc=True)
        df["datetime"] = df["datetime"].dt.tz_convert("America/New_York").dt.tz_localize(None)

        df = df[["symbol", "datetime", "open", "high", "low", "close", "volume"]]
        df = df.sort_values(by=["datetime"], ignore_index=True)

        if frequency == "1d":
            df["datetime"] = df["datetime"].dt.date

        return df


class Trader:
    """
    Can instantiate either schwab or IB
    """

    def __new__(
        cls,
    ) -> SchwabTrader:
        """
        is_live_data only applies to IBKR
        """
        broker = "schwab"

        return SchwabTrader()
