import re
import sys
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd

# from ib_async import IB, Contract, Future, LimitOrder, MarketOrder, Order, Stock, util
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

from .common import plog, to_date, to_datetime
from .config import BROKERS, IBPaperAccount
from .config import AuthenConfig as AC

# client_id incrementer
IB_COUNTER = None
IB_SLEEP = 0.01

# STOCK_SVXY = Stock("SVXY", "SMART", "USD")
# STOCK_SPY = Stock("SPY", "SMART", "USD")
# FUTURE_ES = Future("ES", exchange="CME")
# FUTURE_MES = Future("MES", exchange="CME")
# FUTURE_VIX = Future("VIX", exchange="CFE")

EXCHANGES = {
    "ES": "CME",
    "MES": "CME",
    "VIX": "CFE",
}


# class IBTrader:
#     def __init__(self, is_live_data=True):
#         # to support jupyter notebook
#         if "ipykernel" in sys.modules:
#             util.startLoop()

#         global IB_COUNTER
#         if IB_COUNTER is None:
#             scale = 100
#             IB_COUNTER = np.random.randint(0, 1001) * scale

#         self._client = IB()
#         self._client.connect(
#             IBPaperAccount.host,
#             IBPaperAccount.port,
#             clientId=IB_COUNTER,
#             timeout=10,
#         )
#         self.sleep(1)
#         IB_COUNTER += 1
#         # 1: live data
#         # 3: deplayed live data
#         if is_live_data:
#             self._client.reqMarketDataType(1)
#         else:
#             self._client.reqMarketDataType(3)
#         self.sleep(1)

#         return

#     def get_cash(
#         self,
#     ):
#         """
#         Really getting available fund, which excludes margin
#         """
#         res = self._client.accountSummary()
#         res = [
#             act for act in res if act.tag == "AvailableFunds" and act.currency == "USD"
#         ]

#         return float(res[0].value)

#     def get_aum(
#         self,
#     ):
#         res = self._client.accountSummary()
#         res = [
#             act for act in res if act.tag == "NetLiquidation" and act.currency == "USD"
#         ]

#         return float(res[0].value)

#     def get_position(
#         self,
#         contract: Contract = None,
#         symbol: str = "",
#         security_type: str = "future",
#         contract_month: str = "",
#         exchange: str = "",
#     ) -> int:
#         contract = self.get_contract(
#             contract, symbol, security_type, contract_month, exchange
#         )
#         contract_id = contract.conId
#         res = self._client.positions()
#         res = [p for p in res if p.contract.conId == contract_id]

#         res = res[0].position if len(res) > 0 else 0

#         return res

#     def close_position(
#         self,
#         contract: Contract = None,
#         symbol: str = "",
#         security_type: str = "future",
#         contract_month: str = "",
#         exchange: str = "",
#         slippage: float = 0,
#     ):
#         contract = self.get_contract(
#             contract, symbol, security_type, contract_month, exchange
#         )
#         curr_pos = self.get_position(contract)

#         if curr_pos == 0:
#             return

#         curr_quote = self.get_quote(contract)

#         if curr_pos > 0:
#             # sell to close
#             target_price = curr_quote.bid_price - slippage
#             return self.sell_limit(
#                 contract, quantity=curr_pos, target_price=target_price
#             )
#         elif curr_pos < 0:
#             # buy to cover
#             target_price = curr_quote.ask_price + slippage
#             return self.buy_limit(
#                 contract, quantity=-curr_pos, target_price=target_price
#             )
#         return

#     def get_contract_detail(
#         self,
#         symbol: str,
#         exchange: str = "",
#     ):
#         symbol = symbol.upper()
#         exchange = exchange.upper()

#         if symbol == "ES":
#             contract = FUTURE_ES
#         elif symbol == "MES":
#             contract = FUTURE_MES
#         elif symbol == "VIX":
#             contract = FUTURE_VIX
#         else:
#             contract = Future(symbol, exchange=exchange)
#             raise NotImplementedError(f"Doesn't support {symbol}")

#         # self._client.qualifyContracts(contract)

#         res = self._client.reqContractDetails(contract)
#         self.sleep()
#         res = util.df(res)
#         res = res.sort_values(by="contractMonth", ignore_index=True)
#         header_cols = ["contract", "contractMonth", "realExpirationDate"]
#         header_cols = [col for col in header_cols if col in res.columns]
#         remaining_cols = [col for col in res.columns if col not in header_cols]
#         res = res[header_cols + remaining_cols]

#         if symbol == "VIX":
#             res = res[res["marketName"] == "VX"].reset_index(drop=True)

#         return res

#     def get_quote(
#         self,
#         contract: Contract = None,
#         symbol: str = "",
#         security_type: str = "future",
#         contract_month: str = "",
#         exchange: str = "",
#     ):
#         contract = self.get_contract(
#             contract, symbol, security_type, contract_month, exchange
#         )

#         q = self._client.reqMktData(contract, snapshot=True)
#         # async, sleep to make sure we do receive data from IB...
#         self.sleep()

#         quote = QuoteData(
#             q.contract.symbol,
#             pd.to_datetime(q.time, utc=True)
#             .tz_convert("America/New_York")
#             .to_pydatetime()
#             .replace(tzinfo=None),
#             q.last,
#             q.bid,
#             q.bidSize,
#             q.ask,
#             q.askSize,
#             q.volume,
#             q.minTick,
#         )

#         return quote

#     def get_open_interest(
#         self,
#         contract,
#     ) -> dict:
#         if isinstance(contract, Contract):
#             contract = [contract]

#         res = []
#         self.sleep(2)
#         for con in contract:
#             self._client.qualifyContracts(con)
#             self.sleep(1)
#             ticker = self._client.reqMktData(con, "588", snapshot=False)
#             self.sleep(1)

#             for _ in range(3):
#                 if not np.isnan(ticker.futuresOpenInterest):
#                     break
#                 plog(f"try {_} with {ticker}")
#                 ticker = self._client.reqMktData(con, "588", snapshot=False)
#                 self.sleep(10)
#             else:
#                 self._client.cancelMktData(con)
#                 raise ValueError(f"Cannot get open interest for ticker {ticker}")

#             res.append([con, ticker.futuresOpenInterest])
#             self._client.cancelMktData(con)

#         res.sort(key=lambda x: x[0].lastTradeDateOrContractMonth)
#         res = dict(res)

#         return res

#     def get_front_month_contract(
#         self,
#         symbol: str,
#         exchange: str = "",
#     ):
#         contracts = self.get_contract_detail(symbol, exchange)
#         contract_list = contracts["contract"].values

#         open_interest = self.get_open_interest(contract_list)

#         contracts["open_interest"] = contracts["contract"].map(open_interest)
#         # contracts = contracts.dropna(subset=["open_interest"])
#         contracts = contracts.sort_values(
#             by=["open_interest"], ascending=False, ignore_index=True
#         )

#         return contracts

#     def _place_order(
#         self,
#         order: Order,
#         contract: Contract,
#         symbol: str = "",
#         security_type: str = "future",
#         contract_month: str = "",
#         exchange: str = "",
#     ):
#         contract = self.get_contract(
#             contract, symbol, security_type, contract_month, exchange
#         )
#         _ = self._client.placeOrder(contract, order)
#         # while not trade.isDone():
#         #     self._client.waitOnUpdate()

#     def buy_market(
#         self,
#         contract: Contract = None,
#         symbol: str = "",
#         security_type: str = "future",
#         contract_month: str = "",
#         exchange: str = "",
#         quantity: int = 0,
#     ):
#         assert quantity > 0, "quantity must be positive!"

#         # outsideRth=True
#         order = MarketOrder("BUY", quantity, tif="GTC")
#         self._place_order(
#             order, contract, symbol, security_type, contract_month, exchange
#         )

#         return

#     def buy_limit(
#         self,
#         contract: Contract = None,
#         symbol: str = "",
#         security_type: str = "future",
#         contract_month: str = "",
#         exchange: str = "",
#         quantity: int = 0,
#         target_price: float = 0,
#     ):
#         assert quantity > 0, "quantity must be positive!"
#         assert target_price > 0, "target_price must be positive!"

#         order = LimitOrder("BUY", quantity, target_price, tif="GTC")
#         self._place_order(
#             order, contract, symbol, security_type, contract_month, exchange
#         )

#         return

#     def sell_market(
#         self,
#         contract: Contract = None,
#         symbol: str = "",
#         security_type: str = "future",
#         contract_month: str = "",
#         exchange: str = "",
#         quantity: int = 0,
#     ):
#         assert quantity > 0, "quantity must be positive!"

#         order = MarketOrder("SELL", quantity, tif="GTC")
#         self._place_order(
#             order, contract, symbol, security_type, contract_month, exchange
#         )

#         return

#     def sell_limit(
#         self,
#         contract: Contract = None,
#         symbol: str = "",
#         security_type: str = "future",
#         contract_month: str = "",
#         exchange: str = "",
#         quantity: int = 0,
#         target_price: float = 0,
#     ):
#         assert quantity > 0, "quantity must be positive!"
#         assert target_price > 0, "target_price must be positive!"

#         order = LimitOrder("SELL", quantity, target_price, tif="GTC")
#         self._place_order(
#             order, contract, symbol, security_type, contract_month, exchange
#         )

#         return

#     def get_price_history(
#         self,
#         contract: Contract = None,
#         symbol: str = "",
#         security_type: str = "stock",
#         contract_month: str = "",
#         exchange: str = "",
#         start_date: date | datetime | str = None,
#         end_date: date | datetime | str = None,
#         frequency: str = "1d",
#     ) -> pd.DataFrame:
#         """
#         frequency 1d, 1min, 5min
#         """
#         contract = self.get_contract(
#             contract, symbol, security_type, contract_month, exchange
#         )

#         start_date = to_date(start_date)
#         end_date = to_date(end_date)

#         num_of_days = (end_date - start_date).days
#         duration_str = f"{int(num_of_days + 1)} D"

#         match = re.search(r"(\d+)([a-zA-Z]+)", frequency)
#         freq_num = int(match.group(1))
#         freq_unit = match.group(2).lower()

#         if freq_unit == "min" and freq_num > 1:
#             freq_unit = "mins"
#         elif freq_unit == "d":
#             freq_unit = "day"
#             if freq_num > 1:
#                 freq_unit += "s"

#         frequency = f"{freq_num} {freq_unit}"

#         df = self._client.reqHistoricalData(
#             contract,
#             endDateTime=end_date,
#             durationStr=duration_str,
#             barSizeSetting=frequency,
#             whatToShow="TRADES",
#             useRTH=True,
#             formatDate=1,
#         )
#         df = util.df(df)
#         df = df.rename(columns={"date": "datetime"})
#         df["symbol"] = contract.symbol

#         df["datetime"] = pd.to_datetime(df["datetime"]).dt.tz_localize(None)

#         df = df[
#             [
#                 "symbol",
#                 "datetime",
#                 "open",
#                 "high",
#                 "low",
#                 "close",
#                 "volume",
#                 "average",
#                 "barCount",
#             ]
#         ]
#         df = df.sort_values(by=["datetime"], ignore_index=True)

#         return df

#     def get_contract(
#         self,
#         contract: Contract = None,
#         symbol: str = "",
#         security_type: str = "future",
#         contract_month: str = "",
#         exchange: str = "",
#     ) -> Contract:
#         if contract is None:
#             security_type = security_type.lower()
#             assert security_type in [
#                 "stock",
#                 "future",
#             ], "Only support stock and futures for now."

#             symbol = symbol.upper()

#             if security_type == "stock":
#                 contract = Stock(symbol, "SMART", "USD")
#             elif security_type == "future":
#                 contract = Future(
#                     symbol, contract_month, EXCHANGES[symbol], includeExpired=True
#                 )

#         self._client.qualifyContracts(contract)

#         return contract

#     def sleep(
#         self,
#         secs: float = 0.2,
#     ):
#         self._client.sleep(secs=secs)
