import yaml
import os
from gate_api import ApiClient, Configuration, Order, SpotApi


def load_gateio_creds(file):
    with open(file) as file:
        auth = yaml.load(file, Loader=yaml.FullLoader)
    # print(os.getenv('GATEIO_API'))
    # print(os.environ.get('GATEIO_SECRET'))
    return Configuration(key=os.environ['GATEIO_API'], secret=os.environ['GATEIO_SECRET'])
