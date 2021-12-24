from trade_client import *
from store_order import *
from logger import logger
from load_config import *
from new_listings_scraper import *
import globals
from collections import defaultdict
from datetime import datetime, time
import time
import threading
import copy
import json
from json import JSONEncoder
import os.path
import sys, os

# To add a coin to ignore, add it to the json array in old_coins.json
globals.old_coins = load_old_coins()
logger.debug(f"old_coins: {globals.old_coins}")

# loads local configuration
config = load_config('config.yml')

# load necessary files
if os.path.isfile('sold.json'):
    sold_coins = load_order('sold.json')
else:
    sold_coins = {}

if os.path.isfile('order.json'):
    order = load_order('order.json')
else:
    order = {}

# memory store for all orders for a specific coin
if os.path.isfile('session.json'):
    session = load_order('session.json')
else:
    session = {}

# Keep the supported currencies loaded in RAM so no time is wasted fetching
# currencies.json from disk when an announcement is made
global supported_currencies

logger.debug("Starting get_all_currencies")
supported_currencies = get_all_currencies(single=True)
logger.debug("Finished get_all_currencies")

logger.info(f'{datetime.now().strftime("%H:%M:%S")} Bot starting..', extra={'TELEGRAM': 'STARTUP'})

def sentMessage(queue_message):
    for message in queue_message:
        logger.info(f'{message}', extra={'TELEGRAM': 'COIN_ANNOUNCEMENT'})

def buy():
    while not globals.stop_threads:
        logger.debug('Waiting for buy_ready event')
        globals.buy_ready.wait()
        logger.debug('buy_ready event triggered')
        if globals.stop_threads:
            break
        announcement_coin = globals.latest_listing
        queue_message = [f'{datetime.now().strftime("%H:%M:%S")} New announcement detected: {announcement_coin}']
        global supported_currencies
        if announcement_coin and \
                announcement_coin not in order and \
                announcement_coin not in sold_coins and \
                announcement_coin not in globals.old_coins:

            if not supported_currencies:
                supported_currencies = get_all_currencies(single=True)
            if supported_currencies:
                if announcement_coin in supported_currencies:
                    # queue_message.append(
                    #     f'{datetime.now().strftime("%H:%M:%S")} Starting get_last_price')

                    # get latest price object
                    obj = get_last_price(announcement_coin, globals.pairing, False)
                    price = obj.price

                    queue_message.append(
                        f'{datetime.now().strftime("%H:%M:%S")} Latest price {announcement_coin} is {price}')

                    if float(price) <= 0:
                        continue  # wait for positive price

                    # TODO
                    # check current price is pump with 1 minute ago
                    one_minute_price = get_previous_price(f'{announcement_coin}_{globals.pairing}', 2, '1m')

                    queue_message.append(
                        f'{datetime.now().strftime("%H:%M:%S")} Highest price {announcement_coin} is {one_minute_price[0][3]}')

                    # queue_message.append(
                    #     f'{datetime.now().strftime("%H:%M:%S")} Lowest {announcement_coin} is {price}')
                    #
                    # queue_message.append(
                    #     f'{datetime.now().strftime("%H:%M:%S")} Closed {announcement_coin} is {price}')
                    #
                    # queue_message.append(
                    #     f'{datetime.now().strftime("%H:%M:%S")} '
                    #     f'{announcement_coin}_{globals.pairing} | '
                    #     f'Highest: {one_minute_price[0][3]} | '
                    #     f'Open: {one_minute_price[0][5]} | '
                    #     f'Lowest:{one_minute_price[0][4]} | '
                    #     f'Closed: {one_minute_price[0][2]}')

                    previous_price = one_minute_price[0][3]
                    pump_warning_price = float(price) + (float(price) * 30 / 100)

                    if float(previous_price) >= pump_warning_price:
                        queue_message.append(
                            f'{datetime.now().strftime("%H:%M:%S")} Current price has been pump over {30}%. '
                            f'Previous price:{previous_price} '
                            f' Current price {float(price)}')
                        sentMessage(queue_message)
                        break

                    if announcement_coin not in session:
                        session[announcement_coin] = {}
                        session[announcement_coin].update({'total_volume': 0})
                        session[announcement_coin].update({'total_amount': 0})
                        session[announcement_coin].update({'total_fees': 0})
                        session[announcement_coin]['orders'] = list()

                    # initialize order object
                    if announcement_coin not in order:
                        volume = globals.quantity - session[announcement_coin]['total_volume']

                        order[announcement_coin] = {}
                        order[announcement_coin]['_amount'] = f'{volume / float(price)}'
                        order[announcement_coin]['_left'] = f'{volume / float(price)}'
                        order[announcement_coin]['_fee'] = f'{0}'
                        order[announcement_coin]['_tp'] = f'{0}'
                        order[announcement_coin]['_sl'] = f'{0}'
                        order[announcement_coin]['_status'] = 'unknown'
                        if announcement_coin in session:
                            if len(session[announcement_coin]['orders']) == 0:
                                order[announcement_coin]['_status'] = 'test_partial_fill_order'
                            else:
                                order[announcement_coin]['_status'] = 'cancelled'

                    amount = float(order[announcement_coin]['_amount'])
                    left = float(order[announcement_coin]['_left'])
                    status = order[announcement_coin]['_status']

                    if left - amount != 0:
                        # partial fill.
                        amount = left

                    queue_message.append(
                        f'{datetime.now().strftime("%H:%M:%S")} Starting buy place_order with : {announcement_coin=} | {globals.pairing=} | {volume=} | {amount=} x {price=} | side = buy | {status=}')

                    try:
                        # Run a test trade if true
                        if not globals.test_mode:
                            # just in case...stop buying more than our config amount
                            assert amount * float(price) <= float(volume)

                            order[announcement_coin] = place_order(announcement_coin, globals.pairing, volume, 'buy',
                                                                   price)
                            order[announcement_coin] = order[announcement_coin].__dict__
                            order[announcement_coin].pop("local_vars_configuration")
                            order[announcement_coin]['_tp'] = globals.tp
                            order[announcement_coin]['_sl'] = globals.sl
                            order[announcement_coin]['_ttp'] = globals.ttp
                            order[announcement_coin]['_tsl'] = globals.tsl

                            queue_message.append(
                                f'{datetime.now().strftime("%H:%M:%S")} Finished order({announcement_coin} , {globals.pairing} , {volume} , {"buy"} , {price}')

                    except Exception as e:
                        logger.error(e)

                        queue_message.append(
                            f'{datetime.now().strftime("%H:%M:%S")} Buy order error, exception: {e}')

                    else:
                        order_status = order[announcement_coin]['_status']

                        queue_message.append(
                            f'{datetime.now().strftime("%H:%M:%S")} Order created on {announcement_coin} at a price of {price} each.  {order_status=}')

                        if order_status == "closed":
                            order[announcement_coin]['_amount_filled'] = order[announcement_coin]['_amount']
                            session[announcement_coin]['total_volume'] += (
                                    float(order[announcement_coin]['_amount']) * float(
                                order[announcement_coin]['_price']))
                            session[announcement_coin]['total_amount'] += float(order[announcement_coin]['_amount'])
                            session[announcement_coin]['total_fees'] += float(order[announcement_coin]['_fee'])
                            session[announcement_coin]['orders'].append(copy.deepcopy(order[announcement_coin]))

                            # update order to sum all amounts and all fees
                            # this will set up our sell order for sale of all filled buy orders
                            tf = session[announcement_coin]['total_fees']
                            ta = session[announcement_coin]['total_amount']
                            order[announcement_coin]['_fee'] = f'{tf}'
                            order[announcement_coin]['_amount'] = f'{ta}'

                            store_order('order.json', order)
                            store_order('session.json', session)

                            # We're done. Stop buying and finish up the selling.
                            globals.sell_ready.set()
                            globals.buy_ready.clear()

                            queue_message.append(
                                f'{datetime.now().strftime("%H:%M:%S")} Order on {announcement_coin} closed')
                        else:
                            if order_status == "cancelled" and float(order[announcement_coin]['_amount']) > float(
                                    order[announcement_coin]['_left']) and float(order[announcement_coin]['_left']) > 0:
                                # partial order. Change qty and fee_total in order and finish any remaining balance
                                partial_amount = float(order[announcement_coin]['_amount']) - float(
                                    order[announcement_coin]['_left'])
                                partial_fee = float(order[announcement_coin]['_fee'])
                                order[announcement_coin]['_amount_filled'] = f'{partial_amount}'
                                session[announcement_coin]['total_volume'] += (
                                        partial_amount * float(order[announcement_coin]['_price']))
                                session[announcement_coin]['total_amount'] += partial_amount
                                session[announcement_coin]['total_fees'] += partial_fee

                                session[announcement_coin]['orders'].append(copy.deepcopy(order[announcement_coin]))

                                queue_message.append(
                                    f'{datetime.now().strftime("%H:%M:%S")} Partial fill order detected.  {order_status=} | {partial_amount=} out of {amount=} | {partial_fee=} | {price=}')
                                # FUTURE: We'll probably want to start attempting to sell in the future immediately after ordering any amount
                                # It would require at least a minor refactor, since order is getting cleared and
                                # it seems that this function depends on order being empty, but sell() depends on order not being empty.
                                # globals.sell_ready.set()

                            # order not filled, try again.
                            queue_message.append(
                                f"{datetime.now().strftime('%H:%M:%S')} Clearing order with a status of {order_status}.  Waiting for 'closed' status")

                            order.pop(announcement_coin)  # reset for next iteration
                else:
                    queue_message.append(
                        f'{datetime.now().strftime("%H:%M:%S")} {announcement_coin=} is not supported on gate io')
                    queue_message.append(
                        f'{datetime.now().strftime("%H:%M:%S")} Adding {announcement_coin} to old_coins.json')
                    globals.old_coins.append(announcement_coin)
                    store_old_coins(globals.old_coins)
            else:
                queue_message.append(
                    f'{datetime.now().strftime("%H:%M:%S")} Supported_currencies is not initialized')
        else:
            queue_message.append(
                'This coin is in order, or coin has already been bought/sold. Checking more frequently in case '
                'TP and SL need updating')

        # Sent telegram notice
        sentMessage(queue_message)

        time.sleep(3)


def sell():
    while not globals.stop_threads:
        logger.debug('Waiting for sell_ready event')
        globals.sell_ready.wait()
        logger.debug('sell_ready event triggered')
        if globals.stop_threads:
            break
        # check if the order file exists and load the current orders
        # basically the sell block and update TP and SL logic
        if len(order) > 0:
            for coin in list(order):

                if float(order[coin]['_tp']) == 0:
                    st = order[coin]['_status']
                    logger.Info(f"Order is initialized but not ready. Continuing. | Status={st}")
                    continue

                # store some necessary trade info for a sell
                coin_tp = order[coin]['_tp']
                coin_sl = order[coin]['_sl']

                volume = order[coin]['_amount']
                stored_price = float(order[coin]['_price'])
                symbol = order[coin]['_fee_currency']

                # avoid div by zero error
                if float(stored_price) == 0:
                    continue

                logger.debug(
                    f'Data for sell: {coin=} | {stored_price=} | {coin_tp=} | {coin_sl=} | {volume=} | {symbol=} ')

                logger.info(f'get_last_price existing coin: {coin}')
                obj = get_last_price(symbol, globals.pairing, False)
                last_price = obj.price
                logger.info("Finished get_last_price")

                top_position_price = stored_price + (stored_price * coin_tp / 100)
                stop_loss_price = stored_price + (stored_price * coin_sl / 100)

                # need positive price or continue and wait
                if float(last_price) == 0:
                    continue

                logger.info(
                    f'{symbol=}-{last_price=}\t[STOP: ${"{:,.5f}".format(stop_loss_price)} or {"{:,.2f}".format(coin_sl)}%]\t[TOP: ${"{:,.5f}".format(top_position_price)} or {"{:,.2f}".format(coin_tp)}%]\t[BUY: ${"{:,.5f}".format(stored_price)} (+/-): {"{:,.2f}".format(((float(last_price) - stored_price) / stored_price) * 100)}%]')

                # update stop loss and take profit values if threshold is reached
                if float(last_price) > stored_price + (
                        stored_price * coin_tp / 100) and globals.enable_tsl:
                    # increase as absolute value for TP
                    new_tp = float(last_price) + (float(last_price) * globals.ttp / 100)
                    # convert back into % difference from when the coin was bought
                    new_tp = float((new_tp - stored_price) / stored_price * 100)

                    # same deal as above, only applied to trailing SL
                    new_sl = float(last_price) + (float(last_price) * globals.tsl / 100)
                    new_sl = float((new_sl - stored_price) / stored_price * 100)

                    # new values to be added to the json file
                    order[coin]['_tp'] = new_tp
                    order[coin]['_sl'] = new_sl
                    store_order('order.json', order)

                    new_top_position_price = stored_price + (stored_price * new_tp / 100)
                    new_stop_loss_price = stored_price + (stored_price * new_sl / 100)

                    logger.info(f'updated tp: {round(new_tp, 3)}% / ${"{:,.3f}".format(new_top_position_price)}')
                    logger.info(f'updated sl: {round(new_sl, 3)}% / ${"{:,.3f}".format(new_stop_loss_price)}')


                # close trade if tsl is reached or trail option is not enabled
                elif float(last_price) < stored_price + (
                        stored_price * coin_sl / 100) or float(last_price) > stored_price + (
                        stored_price * coin_tp / 100) and not globals.enable_tsl:
                    try:
                        fees = float(order[coin]['_fee'])
                        sell_volume_adjusted = float(volume) - fees

                        logger.info(
                            f'Starting sell place_order with :{symbol} | {globals.pairing} | {volume} | {sell_volume_adjusted} | {fees} | {float(sell_volume_adjusted) * float(last_price)} | side=sell | last={last_price}',
                            extra={'TELEGRAM': 'SELL_START'})

                        # sell for real if test mode is set to false
                        if not globals.test_mode:
                            sell = place_order(symbol, globals.pairing, float(sell_volume_adjusted) * float(last_price),
                                               'sell', last_price)
                            logger.info("Finish sell place_order")

                            # check for completed sell order
                            if sell._status != 'closed':

                                # change order to sell remaining
                                if float(sell._left) > 0 and float(sell._amount) > float(sell._left):
                                    # adjust down order _amount and _fee
                                    order[coin]['_amount'] = sell._left
                                    order[coin]['_fee'] = f'{fees - (float(sell._fee) / float(sell._price))}'

                                    # add sell order sold.json (handled better in session.json now)
                                    id = f"{coin}_{id}"
                                    sold_coins[id] = sell
                                    sold_coins[id] = sell.__dict__
                                    sold_coins[id].pop("local_vars_configuration")
                                    logger.info(
                                        f"Sell order did not close! {sell._left} of {coin} remaining. Adjusted order _amount and _fee to perform sell of remaining balance")

                                    # add to session orders
                                    try:
                                        if len(session) > 0:
                                            dp = copy.deepcopy(sold_coins[id])
                                            session[coin]['orders'].append(dp)
                                    except Exception as e:
                                        print(e)
                                    pass

                                # keep going.  Not finished until status is 'closed'
                                continue

                        logger.info(
                            f'Sold {coin} with {round((float(last_price) - stored_price) * float(volume), 3)} profit | {round((float(last_price) - stored_price) / float(stored_price) * 100, 3)}% PNL',
                            extra={'TELEGRAM': 'SELL_FILLED'})

                        # remove order from json file
                        order.pop(coin)
                        store_order('order.json', order)
                        logger.debug('Order saved in order.json')
                        globals.sell_ready.clear()

                    except Exception as e:
                        logger.error(e)

                    # store sold trades data
                    else:
                        if not globals.test_mode:
                            sold_coins[coin] = sell
                            sold_coins[coin] = sell.__dict__
                            sold_coins[coin].pop("local_vars_configuration")
                            sold_coins[coin]['profit'] = f'{float(last_price) - stored_price}'
                            sold_coins[coin][
                                'relative_profit_%'] = f'{(float(last_price) - stored_price) / stored_price * 100}%'

                        else:
                            sold_coins[coin] = {
                                'symbol': coin,
                                'price': last_price,
                                'volume': volume,
                                'time': datetime.timestamp(datetime.now()),
                                'profit': f'{float(last_price) - stored_price}',
                                'relative_profit_%': f'{(float(last_price) - stored_price) / stored_price * 100}%',
                                'id': 'test-order',
                                'text': 'test-order',
                                'create_time': datetime.timestamp(datetime.now()),
                                'update_time': datetime.timestamp(datetime.now()),
                                'currency_pair': f'{symbol}_{globals.pairing}',
                                'status': 'closed',
                                'type': 'limit',
                                'account': 'spot',
                                'side': 'sell',
                                'iceberg': '0',
                            }

                            logger.info('Sold coins:\r\n' + str(sold_coins[coin]))

                        # add to session orders
                        try:
                            if len(session) > 0:
                                dp = copy.deepcopy(sold_coins[coin])
                                session[coin]['orders'].append(dp)
                                store_order('session.json', session)
                                logger.debug('Session saved in session.json')
                        except Exception as e:
                            print(e)
                            pass

                        store_order('sold.json', sold_coins)
                        logger.info('Order saved in sold.json')
        else:
            logger.debug("Size of order is 0")
        time.sleep(3)


def main():
    """
    Sells, adjusts TP and SL according to trailing values
    and buys new coins
    """

    # Protection from stale announcement
    latest_coin = get_last_coin()
    if latest_coin:
        globals.latest_listing = latest_coin

    # store config deets
    globals.quantity = config['TRADE_OPTIONS']['QUANTITY']
    globals.tp = config['TRADE_OPTIONS']['TP']
    globals.sl = config['TRADE_OPTIONS']['SL']
    globals.enable_tsl = config['TRADE_OPTIONS']['ENABLE_TSL']
    globals.tsl = config['TRADE_OPTIONS']['TSL']
    globals.ttp = config['TRADE_OPTIONS']['TTP']
    globals.pairing = config['TRADE_OPTIONS']['PAIRING']
    globals.test_mode = config['TRADE_OPTIONS']['TEST']

    globals.stop_threads = False
    globals.buy_ready.clear()

    if not globals.test_mode:
        logger.info(f'!!! LIVE MODE !!!')

    t_get_currencies_thread = threading.Thread(target=get_all_currencies)
    t_get_currencies_thread.start()
    t_buy_thread = threading.Thread(target=buy)
    t_buy_thread.start()

    t_sell_thread = threading.Thread(target=sell)
    t_sell_thread.start()

    try:
        search_and_update()
    except KeyboardInterrupt:
        logger.info('Stopping Threads')
        globals.stop_threads = True
        globals.buy_ready.set()
        globals.sell_ready.set()
        t_get_currencies_thread.join()
        t_buy_thread.join()
        t_sell_thread.join()


if __name__ == '__main__':
    logger.info('working...')
    main()
