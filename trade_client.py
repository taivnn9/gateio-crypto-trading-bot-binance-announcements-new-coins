from datetime import datetime

from gate_api.exceptions import GateApiException, ApiException

from logger import logger

from auth.gateio_auth import *
from gate_api import ApiClient, Order, SpotApi

client = load_gateio_creds('auth/auth.yml')
spot_api = SpotApi(ApiClient(client))

last_trade = None


def get_previous_price(currency_pair, limit, interval):
    # currency_pair = 'BTC_USDT'  # str | Currency pair
    # limit = 100  # int | Maximum recent data points to return. `limit` is conflicted with `from` and `to`. If either `from` or `to` is specified, request will be rejected. (optional) (default to 100)
    # _from = 1546905600  # int | Start time of candlesticks, formatted in Unix timestamp in seconds. Default to`to - 100 * interval` if not specified (optional)
    # to = 1546935600  # int | End time of candlesticks, formatted in Unix timestamp in seconds. Default to current time (optional)
    # interval = '30m'  # str | Interval time between data points (optional) (default to '30m')

    try:
        # Market candlesticks
        api_response = spot_api.list_candlesticks(currency_pair, limit=limit, interval=interval)
        return api_response
    except GateApiException as ex:
        logger.error("Gate api exception, label: %s, message: %s\n" % (ex.label, ex.message))
    except ApiException as e:
        logger.error("Exception when calling SpotApi->list_candlesticks: %s\n" % e)


def get_last_price(base, quote, return_price_only):
    """
    Args:
    'DOT', 'USDT'
    """
    global last_trade
    trades = spot_api.list_trades(currency_pair=f'{base}_{quote}', limit=1)
    assert len(trades) == 1
    trade = trades[0]

    create_time_ms = datetime.utcfromtimestamp(int(trade.create_time_ms.split('.')[0]) / 1000)
    create_time_formatted = create_time_ms.strftime('%d-%m-%y %H:%M:%S.%f')

    if last_trade and last_trade.id > trade.id:
        logger.debug(f"STALE TRADEBOOK RESULT FOUND. RE-TRYING.")
        return get_last_price(base=base, quote=quote, return_price_only=return_price_only)
    else:
        last_trade = trade

    if return_price_only:
        return trade.price

    logger.info(f"LATEST TRADE: {trade.currency_pair} | id={trade.id} | create_time={create_time_formatted} | "
                f"side={trade.side} | amount={trade.amount} | price={trade.price}")
    return trade


def get_min_amount(base, quote):
    """
    Args:
    'DOT', 'USDT'
    """
    try:
        min_amount = spot_api.get_currency_pair(currency_pair=f'{base}_{quote}').min_quote_amount
    except Exception as e:
        logger.info('get_min_amount Exception')
        logger.error(e)
    else:
        return min_amount


def place_order(base, quote, volume, side, price):
    """
    Args:
    'DOT', 'USDT', 4000$, 'buy', 400$
    """
    try:
        order = Order(amount=str(float(volume) / float(price)), price=price, side=side,
                      currency_pair=f'{base}_{quote}', time_in_force='ioc')
        order = spot_api.create_order(order)
        t = order
        logger.info(
            f"PLACE ORDER: {t.side} | {t.id} | {t.account} | {t.type} | {t.currency_pair} | {t.status} | "
            f"amount={t.amount} | price={t.price} | left={t.left} | filled_total={t.filled_total} | "
            f"fill_price={t.fill_price} | fee={t.fee} {t.fee_currency}")
    except Exception as e:
        logger.info('place_order Exception')
        logger.error(e)
        raise

    else:
        return order
