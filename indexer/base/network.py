"""
                    GNU AFFERO GENERAL PUBLIC LICENSE
                       Version 3, 19 November 2007

 Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
 Everyone is permitted to copy and distribute verbatim copies
 of this license document, but changing it is not allowed.

 THIS IS A PART OF MONEY ON CHAIN PACKAGE
 by Martin Mulone (martin.mulone@moneyonchain.com)

"""

from web3 import Web3, Account
from web3._utils.threads import Timeout
from web3.exceptions import TimeExhausted
import json
import os
import datetime
import logging


class BaseConnectionManager(object):

    log = logging.getLogger()


class ConnectionManager(BaseConnectionManager):

    log = logging.getLogger()

    default_account = 0  # index of the account
    index_uri = 0
    accounts = None

    def __init__(self,
                 uris=None,
                 request_timeout=180,
                 chain_id=31
                 ):

        # Parameters
        self.uris = uris
        self.request_timeout = request_timeout
        self.chain_id = chain_id

        # connect to node
        self.web3 = self.connect_node()

        # scan accounts
        self.scan_accounts()

    def connect_node(self, index_uri=0):
        """Connect to the node"""

        uri = self.uris
        if not uri:
            uri = ["https://public-node.testnet.rsk.co"]
        if isinstance(uri, list):
            current_uri = uri[index_uri]
        elif isinstance(uri, str):
            current_uri = uri
        else:
            raise Exception("Not valid uri")

        self.index_uri = index_uri
        return Web3(Web3.HTTPProvider(current_uri,
                                      request_kwargs={'timeout': self.request_timeout}))

    def scan_accounts(self):
        """ Accounts from config or environment"""

        accounts = list()

        if 'ACCOUNT_PK_SECRET' in os.environ:
            # obtain from enviroment if exist instead
            private_key = os.environ['ACCOUNT_PK_SECRET']

            l_priv = private_key.split(',')
            if len(l_priv) > 1:
                # this is a method:
                # ACCOUNT_PK_SECRET=PK1,PK2,PK3
                for a_priv in l_priv:
                    account = Account().from_key(a_priv)
                    accounts.append(account)
            else:
                # Simple PK: ACCOUNT_PK_SECRET=PK
                account = Account().from_key(private_key)
                accounts.append(account)

            # scan 10 accounts like this:
            # ACCOUNT_PK_SECRET_1, ACCOUNT_PK_SECRET_2 .. ACCOUNT_PK_SECRET_9
            for numb in range(1, 10):
                env_pk = 'ACCOUNT_PK_SECRET_{}'.format(numb)
                if env_pk in os.environ:
                    private_key = os.environ[env_pk]
                    account = Account().from_key(private_key)
                    accounts.append(account)

        self.accounts = accounts

    def set_default_account(self, index):
        """ Default index account from config.json accounts """

        self.default_account = index

    def block_timestamp(self, block):
        """ Block timestamp """
        block_timestamp = self.web3.eth.get_block(block).timestamp
        dt_object = datetime.datetime.fromtimestamp(block_timestamp)
        return dt_object

    @property
    def is_connected(self):
        """ Is connected to the node """
        if not self.web3:
            return False

        return self.web3.is_connected()

    @property
    def gas_price(self):
        """ Gas Price """
        return self.web3.eth.gas_price

    @property
    def minimum_gas_price(self):
        """ Gas Price """
        return Web3.to_int(hexstr=self.web3.eth.get_block('latest').minimumGasPrice)

    @property
    def block_number(self):
        """ Las block number """
        return self.web3.eth.block_number

    def balance(self, address):
        """ Balance of the address """
        return self.web3.eth.get_balance(Web3.to_checksum_address(address))

    def balance_block_number(self, address, block_number=0):
        """ Balance of the address """
        return self.web3.eth.get_balance(Web3.to_checksum_address(address), block_number)

    def get_block(self, *args, **kargs):
        """ Get the block"""
        return self.web3.eth.get_block(*args, **kargs)

    def get_transaction_receipt(self, transaction_hash):
        """ Transaction receipt """
        return self.web3.eth.get_transaction_receipt(transaction_hash)

    def get_transaction_by_hash(self, transaction_hash):
        """ Transaction by hash """
        return self.web3.eth.get_transaction(transaction_hash)

    def load_json_contract(self, json_filename, deploy_address=None):
        """ Load the abi from json file """

        network = self.network

        with open(json_filename) as f:
            info_json = json.load(f)
        abi = info_json["abi"]

        # Get from json if we dont know the address
        if not deploy_address:
            deploy_address = info_json["networks"][str(self.options['networks'][network]['chain_id'])]['address']

        sc = self.web3.eth.contract(address=self.web3.to_checksum_address(deploy_address), abi=abi)

        return sc

    def load_abi_contract_file(self, abi_filename, contract_address):
        """ Load the abi """

        with open(abi_filename) as f:
            abi = json.load(f)

        sc = self.web3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)

        return sc

    def load_contract(self, abi, contract_address):
        """ Load contract """

        sc = self.web3.eth.contract(address=Web3.to_checksum_address(contract_address), abi=abi)

        return sc

    def load_bytecode_contract_file(self, abi_filename, bin_filename):
        """ Load abi and bin content from files """

        with open(abi_filename) as f:
            content_abi = json.load(f)

        with open(bin_filename) as f:
            content_bin = f.read()

        return self.load_bytecode_contract( content_abi, content_bin)

    def load_bytecode_contract(self, content_abi, content_bin):
        """ Load abi and bin content """

        sc = self.web3.eth.contract(abi=content_abi, bytecode=content_bin)

        return sc, content_abi, content_bin

    def load_bytecode_contract_file_json(self, json_filename, link_library=None):
        """ Get the json content from json compiled """

        with open(json_filename) as f:
            json_content = json.load(f)

        bytecode = json_content["bytecode"]
        if link_library:
            for lib_name, lib_address in link_library:
                bytecode = bytecode.replace(lib_name, lib_address)

        sc = self.web3.eth.contract(abi=json_content["abi"], bytecode=bytecode)

        return sc

    @staticmethod
    def all_events_from(sc, events_functions=None, from_block=0, to_block='latest'):

        if events_functions:
            if not isinstance(events_functions, list):
                raise Exception(
                    'events_functions must be a list of event functions like ["Event Name 1", "Event Name 2"]'
                )
        else:
            events_functions = list()
            for fn_events in sc.events:
                events_functions.append(fn_events.__name__)

        r_events = dict()
        for fn_events in sc.events:

            if fn_events.__name__ in events_functions:
                l_event = list()
                event_filter = fn_events.createFilter(fromBlock=from_block, toBlock=to_block)
                event_entries = event_filter.get_all_entries()
                for event_entry in event_entries:
                    if event_entry['event'] == fn_events.__name__:
                        l_event.append(event_entry)
                r_events[fn_events.__name__] = l_event
        return r_events

    def logs_from(self, sc, events_functions, from_block, to_block, block_steps=2880):

        last_block_number = int(self.block_number)

        if to_block <= 0:
            to_block = last_block_number  # last block number in the node

        current_block = from_block

        l_events = dict()
        while current_block <= to_block:

            step_end = current_block + block_steps
            if step_end > to_block:
                step_end = to_block

            self.log.info("Scanning blocks steps from {0} to {1}".format(current_block, step_end))

            events = self.all_events_from(sc,
                                          events_functions=events_functions,
                                          from_block=current_block,
                                          to_block=step_end)

            # Adjust current blocks to the next step
            current_block = current_block + block_steps

            # add to the list
            for fnx_name in events_functions:
                if fnx_name in events:
                    if events[fnx_name]:
                        if fnx_name not in l_events:
                            l_events[fnx_name] = list()
                        l_events[fnx_name].append(events[fnx_name])

        return l_events


if __name__ == '__main__':
    print("init")