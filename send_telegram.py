import requests
import logging
import yaml
import os
from load_config import *
from datetime import datetime

config = load_config('config.yml')
os_deploy = os.environ['OS_DEPLOY']

with open('auth/auth.yml') as file:
    try:
        creds = yaml.load(file, Loader=yaml.FullLoader)

        bot_token = os.environ['TELEGRAM_TOKEN']
        bot_chatID = str(os.environ['TELEGRAM_CHAT_ID'])
        valid_auth = True
    except KeyError:
        valid_auth = False
        pass


class TelegramLogFilter(logging.Filter):
    # filter for logRecords with TELEGRAM extra
    def filter(self, record):
        return hasattr(record, 'TELEGRAM')


class TelegramHandler(logging.Handler):
    # log to telegram if the TELEGRAM extra matches an enabled key
    def emit(self, record):

        if not valid_auth:
            return

        key = getattr(record, 'TELEGRAM')

        # unknown message key
        if not key in config['TELEGRAM']['NOTIFICATIONS']:
            return

        # message key disabled
        if not config['TELEGRAM']['NOTIFICATIONS'][key]:
            return
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        requests.get(
            'https://api.telegram.org/bot'
            + bot_token
            + '/sendMessage?chat_id='
            + bot_chatID
            + '&parse_mode=Markdown&text='
            + os_deploy
            + ' at '
            + current_time
            + ': '
            + record.message)
