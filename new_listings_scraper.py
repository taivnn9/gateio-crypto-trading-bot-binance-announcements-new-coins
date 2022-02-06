import ast
import os.path
import os
import random
import re
import string
import time
import re

import globals

import requests
from gate_api import ApiClient, SpotApi

from auth.gateio_auth import *
from logger import logger
from store_order import *
from load_config import *

config = load_config('config.yml')
client = load_gateio_creds('auth/auth.yml')
spot_api = SpotApi(ApiClient(client))

global supported_currencies

previously_found_coins = set()


def get_announcement():
    """
    Retrieves new coin listing announcements

    """
    logger.debug("Pulling announcement page")
    # Generate random query/params to help prevent caching
    rand_page_size = random.randint(1, 200)
    letters = string.ascii_letters
    random_string = ''.join(random.choice(letters) for i in range(random.randint(10, 20)))
    random_number = random.randint(1, 99999999999999999999)
    queries = ["type=1", "catalogId=48", "pageNo=1", f"pageSize={str(rand_page_size)}", f"rnd={str(time.time())}",
               f"{random_string}={str(random_number)}"]
    random.shuffle(queries)
    logger.debug(f"Queries: {queries}")
    request_url = f"https://www.binance.com/gateway-api/v1/public/cms/article/list/query" \
                  f"?{queries[0]}&{queries[1]}&{queries[2]}&{queries[3]}&{queries[4]}&{queries[5]}"
    latest_announcement = requests.get(request_url)
    try:
        logger.debug(f'X-Cache: {latest_announcement.headers["X-Cache"]}')
    except KeyError:
        # No X-Cache header was found - great news, we're hitting the source.
        pass

    latest_announcement = latest_announcement.json()
    logger.debug("Finished pulling announcement page")
    return latest_announcement['data']['catalogs'][0]['articles'][0]['title']


def listToString(s):
    # initialize an empty string
    str1 = ""

    # traverse in the string
    for ele in s:
        str1 += " " + ele

        # return string
    return str1

def get_last_coin():
    """
     Returns new Symbol when appropriate
    """
    # scan Binance Announcement
    latest_announcement = get_announcement()

    found_coin = re.findall('\(([^)]+)', latest_announcement)
    uppers = None

    if len(found_coin) > 0:
        uppers = found_coin[0]
        previously_found_coins.add(uppers)

    # logger.info('New coin detected: ' + listToString(found_coin))

    return uppers


def store_new_listing(listing):
    """
    Only store a new listing if different from existing value
    """
    if listing and not listing == globals.latest_listing:
        logger.info(f"New listing detected {listing}")
        globals.latest_listing = listing
        globals.buy_ready.set()


def search_and_update():
    """
    Pretty much our main func
    """
    minute = 0
    while not globals.stop_threads:
        sleep_time = 3
        minute += sleep_time
        for x in range(sleep_time):
            time.sleep(1)
            if globals.stop_threads:
                break
        try:
            latest_coin = get_last_coin()
            if latest_coin:
                store_new_listing(latest_coin)
            if minute == 60:
                logger.info(f"Checking for coin announcements every {str(sleep_time)} seconds (in a separate thread)")
                minute = 0
        except Exception as e:
            logger.info('search_and_update Exception')
            logger.info(e)
    else:
        logger.info("while loop in search_and_update() has stopped.")


def get_all_currencies(single=False):
    """
    Get a list of all currencies supported on gate io
    :return:
    """
    global supported_currencies
    while not globals.stop_threads:
        logger.info("Getting the list of supported currencies from gate io")
        all_currencies = ast.literal_eval(str(spot_api.list_currencies()))
        currency_list = [currency['currency'] for currency in all_currencies]
        with open('currencies.json', 'w') as f:
            json.dump(currency_list, f, indent=4)
            logger.info("List of gate io currencies saved to currencies.json. Waiting 5 "
                        "minutes before refreshing list...")
        supported_currencies = currency_list
        if single:
            return supported_currencies
        else:
            for x in range(300):
                time.sleep(1)
                if globals.stop_threads:
                    break
    else:
        logger.info("while loop in get_all_currencies() has stopped.")


def load_old_coins():
    if os.path.isfile('old_coins.json'):
        with open('old_coins.json') as json_file:
            data = json.load(json_file)
            logger.debug("Loaded old_coins from file")
            return data
    else:
        return []


def store_old_coins(old_coin_list):
    with open('old_coins.json', 'w') as f:
        json.dump(old_coin_list, f, indent=2)
        logger.debug('Wrote old_coins to file')
