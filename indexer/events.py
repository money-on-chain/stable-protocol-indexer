import datetime
from collections import OrderedDict
from eth_typing import HexStr
from web3 import Web3

from .logger import log


def sanitize_address(address):
    return Web3.to_checksum_address(address.replace("0x000000000000000000000000", "0x"))


def oper_id_to_int(oper_id):

    if str(oper_id).startswith("0x"):
        return Web3.to_int(hexstr=HexStr(oper_id))
    else:
        return int(oper_id)


def bytes32_to_hex(value):
    """ Normalize a bytes32 log value to a 0x-prefixed hex string """
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    if isinstance(value, str) and not value.startswith("0x"):
        return "0x" + value
    return value


def bytes32_to_text(value):
    """ Best-effort decode of a bytes32 coin pair (e.g. b'BTCUSD\\x00..') to text """
    try:
        if isinstance(value, str):
            value = bytes.fromhex(value[2:] if value.startswith("0x") else value)
        return bytes(value).decode("utf-8").rstrip("\x00")
    except Exception:
        return None


class BaseEvent:

    name = 'Name'
    precision = 10 ** 18

    def __init__(self, options, connection_helper, filter_contracts_addresses, block_info):

        self.options = options
        self.connection_helper = connection_helper
        self.filter_contracts_addresses = filter_contracts_addresses
        self.block_info = block_info

    def parse_event(self, parsed_receipt, decoded_event):
        fields = dict()
        for field in decoded_event:
            fields[field['name']] = field['value']

        return dict(**parsed_receipt, **fields)

    def status_tx(self, parse_receipt):

        if self.block_info["last_block"] - parse_receipt['blockNumber'] > self.block_info['confirm_blocks']:
            status = 'confirmed'
            confirmation_time = self.block_info['block_ts']
        else:
            status = 'confirming'
            confirmation_time = None

        return status, confirmation_time

    def confirming_percent(self, parse_receipt):

        if self.block_info["last_block"] - parse_receipt['blockNumber'] > self.block_info['confirm_blocks']:
            status = 'confirmed'
            confirmation_time = self.block_info['block_ts']
            confirming_percent = 100
        else:
            status = 'confirming'
            confirmation_time = None
            confirming_percent = (self.block_info['last_block'] - parse_receipt["blockNumber"]) * 10

        return status, confirmation_time, confirming_percent


class EventMoCExchangeRiskProMint(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # status of tx
        status, confirmation_time, confirming_percent = self.confirming_percent(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        d_tx = OrderedDict()
        d_tx["address"] = sanitize_address(parsed["account"])
        d_tx["blockNumber"] = parsed_receipt["blockNumber"]
        d_tx["event"] = 'RiskProMint'
        d_tx["transactionHash"] = tx_hash
        d_tx["RBTCAmount"] = str(parsed["reserveTotal"])
        usd_amount = Web3.from_wei(parsed["reserveTotal"],
                                   'ether') * Web3.from_wei(parsed["reservePrice"],
                                                            'ether')
        d_tx["USDAmount"] = str(int(usd_amount * self.precision))
        d_tx["amount"] = str(parsed["amount"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx['confirmingPercent'] = confirming_percent
        d_tx["isPositive"] = True
        d_tx["lastUpdatedAt"] = datetime.datetime.now()

        if "reserveTokenMarkup" in parsed:
            rbtc_commission = parsed["commission"] + parsed["reserveTokenMarkup"]
        else:
            rbtc_commission = parsed["commission"] + parsed["btcMarkup"]

        moc_commission = parsed["mocCommissionValue"] + parsed["mocMarkup"]
        if rbtc_commission > 0:
            usd_commission = Web3.from_wei(rbtc_commission, 'ether') * Web3.from_wei(parsed["reservePrice"], 'ether')
        else:
            usd_commission = Web3.from_wei(moc_commission, 'ether') * Web3.from_wei(parsed["mocPrice"], 'ether')
        d_tx["rbtcCommission"] = str(rbtc_commission)

        d_tx["USDCommission"] = str(int(usd_commission * self.precision))
        d_tx["status"] = status
        d_tx["tokenInvolved"] = 'RISKPRO'
        d_tx["reservePrice"] = str(parsed["reservePrice"])

        d_tx["mocCommissionValue"] = str(moc_commission)
        d_tx["mocPrice"] = str(parsed["mocPrice"])

        gas_fee = parsed_receipt['gasUsed'] * Web3.from_wei(parsed_receipt["gasPrice"], 'ether')
        # gas_fee = self.tx_receipt.gasUsed * Web3.fromWei(moc_tx['gasPrice'],
        #                                               'ether')
        d_tx["gasFeeRBTC"] = str(int(gas_fee * self.precision))
        if self.options['app_mode'] != "RRC20":
            d_tx["gasFeeUSD"] = str(int(
                gas_fee * Web3.from_wei(parsed["reservePrice"],
                                        'ether') * self.precision))
        rbtc_total = parsed["reserveTotal"] + parsed["commission"] + int(
            gas_fee * self.precision)
        d_tx["RBTCTotal"] = str(rbtc_total)
        usd_total = Web3.from_wei(rbtc_total, 'ether') * Web3.from_wei(
            parsed["reservePrice"], 'ether')
        d_tx["USDTotal"] = str(int(usd_total * self.precision))
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed_receipt['createdAt']
        d_tx["gas"] = parsed['gas']
        d_tx["gasPrice"] = str(parsed['gasPrice'])
        d_tx["gasUsed"] = parsed['gasUsed']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)
        d_tx['post_id'] = post_id

        log.info("Tx {0} From: [{1}] Amount: {2} Tx Hash: {3}".format(
            d_tx["event"],
            d_tx["address"],
            d_tx["amount"],
            tx_hash))

        return parsed


class EventMoCExchangeRiskProRedeem(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # status of tx
        status, confirmation_time, confirming_percent = self.confirming_percent(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        d_tx = OrderedDict()
        d_tx["event"] = 'RiskProRedeem'
        d_tx["blockNumber"] = parsed_receipt["blockNumber"]
        d_tx["transactionHash"] = tx_hash
        d_tx["address"] = sanitize_address(parsed["account"])
        d_tx["tokenInvolved"] = 'RISKPRO'
        d_tx["userAmount"] = str(Web3.from_wei(parsed["amount"], 'ether'))
        d_tx["lastUpdatedAt"] = datetime.datetime.now()
        d_tx["status"] = status
        d_tx["RBTCAmount"] = str(parsed["reserveTotal"])
        usd_amount = Web3.from_wei(parsed["reserveTotal"],
                                   'ether') * Web3.from_wei(parsed["reservePrice"],
                                                            'ether')
        d_tx["USDAmount"] = str(int(usd_amount * self.precision))
        d_tx["amount"] = str(parsed["amount"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx['confirmingPercent'] = confirming_percent
        if "reserveTokenMarkup" in parsed:
            rbtc_commission = parsed["commission"] + parsed["reserveTokenMarkup"]
        else:
            rbtc_commission = parsed["commission"] + parsed["btcMarkup"]
        moc_commission = parsed["mocCommissionValue"] + parsed["mocMarkup"]
        if rbtc_commission > 0:
            usd_commission = Web3.from_wei(rbtc_commission, 'ether') * Web3.from_wei(parsed["reservePrice"], 'ether')
        else:
            usd_commission = Web3.from_wei(moc_commission, 'ether') * Web3.from_wei(parsed["mocPrice"], 'ether')
        d_tx["rbtcCommission"] = str(rbtc_commission)
        d_tx["USDCommission"] = str(int(usd_commission * self.precision))
        d_tx["isPositive"] = False
        d_tx["reservePrice"] = str(parsed["reservePrice"])
        d_tx["mocCommissionValue"] = str(moc_commission)
        d_tx["mocPrice"] = str(parsed["mocPrice"])
        gas_fee = parsed_receipt["gasUsed"] * Web3.from_wei(parsed_receipt["gasPrice"], 'ether')
        d_tx["gasFeeRBTC"] = str(int(gas_fee * self.precision))
        if self.options['app_mode'] != "RRC20":
            d_tx["gasFeeUSD"] = str(int(
                gas_fee * Web3.from_wei(parsed["reservePrice"],
                                        'ether') * self.precision))
        rbtc_total = parsed["reserveTotal"] - int(gas_fee * self.precision)
        d_tx["RBTCTotal"] = str(rbtc_total)
        rbtc_total_ether = Web3.from_wei(abs(rbtc_total), 'ether')
        if rbtc_total < 0:
            rbtc_total_ether = -rbtc_total_ether
        usd_total = rbtc_total_ether * Web3.from_wei(parsed["reservePrice"],
                                                     'ether')
        d_tx["USDTotal"] = str(int(usd_total * self.precision))
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed_receipt['createdAt']
        d_tx["gas"] = parsed['gas']
        d_tx["gasPrice"] = str(parsed['gasPrice'])
        d_tx["gasUsed"] = parsed['gasUsed']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)
        d_tx['post_id'] = post_id

        log.info("Tx {0} From: [{1}] Amount: {2} Tx Hash: {3}".format(
            d_tx["event"],
            d_tx["address"],
            d_tx["amount"],
            tx_hash))

        return parsed


class EventMoCExchangeRiskProxMint(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # status of tx
        status, confirmation_time, confirming_percent = self.confirming_percent(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        d_tx = OrderedDict()
        d_tx["transactionHash"] = tx_hash
        d_tx["blockNumber"] = parsed["blockNumber"]
        d_tx["address"] = sanitize_address(parsed["account"])
        d_tx["status"] = status
        d_tx["event"] = 'RiskProxMint'
        d_tx["tokenInvolved"] = 'RISKPROX'
        d_tx["userAmount"] = str(Web3.from_wei(parsed["amount"], 'ether'))
        d_tx["lastUpdatedAt"] = datetime.datetime.now()
        d_tx["RBTCAmount"] = str(parsed["reserveTotal"])
        usd_amount = Web3.from_wei(parsed["reserveTotal"],
                                   'ether') * Web3.from_wei(parsed["reservePrice"],
                                                            'ether')
        d_tx["USDAmount"] = str(int(usd_amount * self.precision))
        d_tx["amount"] = str(parsed["amount"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx['confirmingPercent'] = confirming_percent
        d_tx["isPositive"] = True
        d_tx["leverage"] = str(parsed["leverage"])
        if "reserveTokenMarkup" in parsed:
            rbtc_commission = parsed["commission"] + parsed["reserveTokenMarkup"]
        else:
            rbtc_commission = parsed["commission"] + parsed["btcMarkup"]
        moc_commission = parsed["mocCommissionValue"] + parsed["mocMarkup"]
        if rbtc_commission > 0:
            usd_commission = Web3.from_wei(rbtc_commission, 'ether') * Web3.from_wei(parsed["reservePrice"], 'ether')
        else:
            usd_commission = Web3.from_wei(moc_commission, 'ether') * Web3.from_wei(parsed["mocPrice"], 'ether')
        d_tx["rbtcCommission"] = str(rbtc_commission)
        d_tx["USDCommission"] = str(int(usd_commission * self.precision))
        d_tx["rbtcInterests"] = str(parsed["interests"])
        usd_interest = Web3.from_wei(parsed["interests"], 'ether') * Web3.from_wei(
            parsed["reservePrice"], 'ether')
        d_tx["USDInterests"] = str(int(usd_interest * self.precision))
        d_tx["reservePrice"] = str(parsed["reservePrice"])
        d_tx["mocCommissionValue"] = str(moc_commission)
        d_tx["mocPrice"] = str(parsed["mocPrice"])
        gas_fee = parsed["gasUsed"] * Web3.from_wei(parsed["gasPrice"], 'ether')
        d_tx["gasFeeRBTC"] = str(int(gas_fee * self.precision))
        if self.options['app_mode'] != "RRC20":
            d_tx["gasFeeUSD"] = str(int(
                gas_fee * Web3.from_wei(parsed["reservePrice"],
                                        'ether') * self.precision))
        rbtc_total = parsed["reserveTotal"] + parsed["commission"] + parsed["interests"] + int(
            gas_fee * self.precision)
        d_tx["RBTCTotal"] = str(rbtc_total)
        usd_total = Web3.from_wei(rbtc_total, 'ether') * Web3.from_wei(
            parsed["reservePrice"], 'ether')
        d_tx["USDTotal"] = str(int(usd_total * self.precision))
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed['createdAt']
        d_tx["gas"] = parsed['gas']
        d_tx["gasPrice"] = str(parsed['gasPrice'])
        d_tx["gasUsed"] = parsed['gasUsed']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)
        d_tx['post_id'] = post_id

        log.info("Tx {0} From: [{1}] Amount: {2} Tx Hash: {3}".format(
            d_tx["event"],
            d_tx["address"],
            d_tx["amount"],
            tx_hash))

        return parsed


class EventMoCExchangeRiskProxRedeem(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # status of tx
        status, confirmation_time, confirming_percent = self.confirming_percent(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        d_tx = OrderedDict()
        d_tx["transactionHash"] = tx_hash
        d_tx["blockNumber"] = parsed["blockNumber"]
        d_tx["address"] = sanitize_address(parsed["account"])
        d_tx["status"] = status
        d_tx["event"] = 'RiskProxRedeem'
        d_tx["tokenInvolved"] = 'RISKPROX'
        d_tx["userAmount"] = str(Web3.from_wei(parsed["amount"], 'ether'))
        d_tx["lastUpdatedAt"] = datetime.datetime.now()
        d_tx["RBTCAmount"] = str(parsed["reserveTotal"])
        usd_amount = Web3.from_wei(parsed["reserveTotal"],
                                   'ether') * Web3.from_wei(parsed["reservePrice"],
                                                            'ether')
        d_tx["USDAmount"] = str(int(usd_amount * self.precision))
        d_tx["amount"] = str(parsed["amount"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx['confirmingPercent'] = confirming_percent
        d_tx["leverage"] = str(parsed["leverage"])
        if "reserveTokenMarkup" in parsed:
            rbtc_commission = parsed["commission"] + parsed["reserveTokenMarkup"]
        else:
            rbtc_commission = parsed["commission"] + parsed["btcMarkup"]
        moc_commission = parsed["mocCommissionValue"] + parsed["mocMarkup"]
        if rbtc_commission > 0:
            usd_commission = Web3.from_wei(rbtc_commission, 'ether') * Web3.from_wei(parsed["reservePrice"], 'ether')
        else:
            usd_commission = Web3.from_wei(moc_commission, 'ether') * Web3.from_wei(parsed["mocPrice"], 'ether')
        d_tx["rbtcCommission"] = str(rbtc_commission)
        d_tx["USDCommission"] = str(int(usd_commission * self.precision))
        d_tx["rbtcInterests"] = str(parsed["interests"])
        usd_interest = Web3.from_wei(parsed["interests"], 'ether') * Web3.from_wei(
            parsed["reservePrice"], 'ether')
        d_tx["USDInterests"] = str(int(usd_interest * self.precision))
        d_tx["isPositive"] = False
        d_tx["reservePrice"] = str(parsed["reservePrice"])
        d_tx["mocCommissionValue"] = str(moc_commission)
        d_tx["mocPrice"] = str(parsed["mocPrice"])
        gas_fee = parsed["gasUsed"] * Web3.from_wei(parsed["gasPrice"], 'ether')
        d_tx["gasFeeRBTC"] = str(int(gas_fee * self.precision))
        if self.options['app_mode'] != "RRC20":
            d_tx["gasFeeUSD"] = str(int(
                gas_fee * Web3.from_wei(parsed["reservePrice"],
                                        'ether') * self.precision))
        rbtc_total = parsed["reserveTotal"] + parsed["interests"] - int(
            gas_fee * self.precision)
        d_tx["RBTCTotal"] = str(rbtc_total)
        rbtc_total_ether = Web3.from_wei(abs(rbtc_total), 'ether')
        if rbtc_total < 0:
            rbtc_total_ether = -rbtc_total_ether
        usd_total = rbtc_total_ether * Web3.from_wei(parsed["reservePrice"],
                                                     'ether')
        d_tx["USDTotal"] = str(int(usd_total * self.precision))
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed['createdAt']
        d_tx["gas"] = parsed['gas']
        d_tx["gasPrice"] = str(parsed['gasPrice'])
        d_tx["gasUsed"] = parsed['gasUsed']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)
        d_tx['post_id'] = post_id

        log.info("Tx {0} From: [{1}] Amount: {2} Tx Hash: {3}".format(
            d_tx["event"],
            d_tx["address"],
            d_tx["amount"],
            tx_hash))

        return parsed


class EventMoCExchangeStableTokenMint(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # status of tx
        status, confirmation_time, confirming_percent = self.confirming_percent(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        d_tx = OrderedDict()
        d_tx["transactionHash"] = tx_hash
        d_tx["blockNumber"] = parsed["blockNumber"]
        d_tx["address"] = sanitize_address(parsed["account"])
        d_tx["status"] = status
        d_tx["event"] = 'StableTokenMint'
        d_tx["tokenInvolved"] = 'STABLE'
        # WARNING something to investigate, commented think is correct
        # d_tx["userAmount"] = str(Web3.fromWei(tx_event.amount, 'ether'))
        d_tx["userAmount"] = str(Web3.from_wei(parsed["reserveTotal"], 'ether'))
        d_tx["lastUpdatedAt"] = datetime.datetime.now()
        d_tx["RBTCAmount"] = str(parsed["reserveTotal"])
        usd_amount = Web3.from_wei(parsed["reserveTotal"],
                                   'ether') * Web3.from_wei(parsed["reservePrice"],
                                                            'ether')
        d_tx["USDAmount"] = str(int(usd_amount * self.precision))
        if "reserveTokenMarkup" in parsed:
            rbtc_commission = parsed["commission"] + parsed["reserveTokenMarkup"]
        else:
            rbtc_commission = parsed["commission"] + parsed["btcMarkup"]
        moc_commission = parsed["mocCommissionValue"] + parsed["mocMarkup"]
        if rbtc_commission > 0:
            usd_commission = Web3.from_wei(rbtc_commission, 'ether') * Web3.from_wei(parsed["reservePrice"], 'ether')
        else:
            usd_commission = Web3.from_wei(moc_commission, 'ether') * Web3.from_wei(parsed["mocPrice"], 'ether')
        d_tx["USDCommission"] = str(int(usd_commission * self.precision))
        d_tx["amount"] = str(parsed["amount"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx['confirmingPercent'] = confirming_percent
        d_tx["isPositive"] = True
        d_tx["rbtcCommission"] = str(rbtc_commission)
        d_tx["reservePrice"] = str(parsed["reservePrice"])
        d_tx["mocCommissionValue"] = str(moc_commission)
        d_tx["mocPrice"] = str(parsed["mocPrice"])
        gas_fee = parsed["gasUsed"] * Web3.from_wei(parsed["gasPrice"], 'ether')
        d_tx["gasFeeRBTC"] = str(int(gas_fee * self.precision))
        if self.options['app_mode'] != "RRC20":
            d_tx["gasFeeUSD"] = str(int(
                gas_fee * Web3.from_wei(parsed["reservePrice"],
                                        'ether') * self.precision))
        rbtc_total = parsed["reserveTotal"] + parsed["commission"] + int(
            gas_fee * self.precision)
        d_tx["RBTCTotal"] = str(rbtc_total)
        usd_total = Web3.from_wei(rbtc_total, 'ether') * Web3.from_wei(
            parsed["reservePrice"], 'ether')
        d_tx["USDTotal"] = str(int(usd_total * self.precision))
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed['createdAt']
        d_tx["gas"] = parsed['gas']
        d_tx["gasPrice"] = str(parsed['gasPrice'])
        d_tx["gasUsed"] = parsed['gasUsed']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)
        d_tx['post_id'] = post_id

        log.info("Tx {0} From: [{1}] Amount: {2} Tx Hash: {3}".format(
            d_tx["event"],
            d_tx["address"],
            d_tx["amount"],
            tx_hash))

        return parsed


class EventMoCExchangeStableTokenRedeem(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # status of tx
        status, confirmation_time, confirming_percent = self.confirming_percent(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        d_tx = OrderedDict()
        d_tx["address"] = sanitize_address(parsed["account"])
        d_tx["blockNumber"] = parsed["blockNumber"]
        d_tx["event"] = 'StableTokenRedeem'
        d_tx["transactionHash"] = tx_hash
        d_tx["RBTCAmount"] = str(parsed["reserveTotal"])
        usd_amount = Web3.from_wei(parsed["reserveTotal"],
                                   'ether') * Web3.from_wei(parsed["reservePrice"],
                                                            'ether')
        d_tx["USDAmount"] = str(int(usd_amount * self.precision))
        d_tx["amount"] = str(parsed["amount"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx['confirmingPercent'] = confirming_percent
        d_tx["lastUpdatedAt"] = datetime.datetime.now()
        d_tx["status"] = status
        d_tx["tokenInvolved"] = 'STABLE'
        if "reserveTokenMarkup" in parsed:
            rbtc_commission = parsed["commission"] + parsed["reserveTokenMarkup"]
        else:
            rbtc_commission = parsed["commission"] + parsed["btcMarkup"]
        moc_commission = parsed["mocCommissionValue"] + parsed["mocMarkup"]
        if rbtc_commission > 0:
            usd_commission = Web3.from_wei(rbtc_commission, 'ether') * Web3.from_wei(parsed["reservePrice"], 'ether')
        else:
            usd_commission = Web3.from_wei(moc_commission, 'ether') * Web3.from_wei(parsed["mocPrice"], 'ether')
        d_tx["rbtcCommission"] = str(rbtc_commission)
        d_tx["USDCommission"] = str(int(usd_commission * self.precision))
        d_tx["isPositive"] = False
        d_tx["reservePrice"] = str(parsed["reservePrice"])
        d_tx["mocCommissionValue"] = str(moc_commission)
        d_tx["mocPrice"] = str(parsed["mocPrice"])
        gas_fee = parsed["gasUsed"] * Web3.from_wei(parsed["gasPrice"], 'ether')
        # d_tx["gasFeeRBTC"] = str(int(gas_fee * self.precision))
        # if self.app_mode != "RRC20":
        #    d_tx["gasFeeUSD"] = str(int(gas_fee * Web3.fromWei(tx_event.reservePrice, 'ether') * self.precision))
        rbtc_total = parsed["reserveTotal"] - int(gas_fee * self.precision)
        d_tx["RBTCTotal"] = str(rbtc_total)
        rbtc_total_ether = Web3.from_wei(abs(rbtc_total), 'ether')
        if rbtc_total < 0:
            rbtc_total_ether = -rbtc_total_ether
        usd_total = rbtc_total_ether * Web3.from_wei(parsed["reservePrice"],
                                                     'ether')
        d_tx["USDTotal"] = str(int(usd_total * self.precision))
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed['createdAt']
        d_tx["gas"] = parsed['gas']
        d_tx["gasPrice"] = str(parsed['gasPrice'])
        d_tx["gasUsed"] = parsed['gasUsed']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)
        d_tx['post_id'] = post_id

        log.info("Tx {0} From: [{1}] Amount: {2} Tx Hash: {3}".format(
            d_tx["event"],
            d_tx["address"],
            d_tx["amount"],
            tx_hash))

        return parsed


class EventMoCExchangeFreeStableTokenRedeem(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # status of tx
        status, confirmation_time, confirming_percent = self.confirming_percent(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        d_tx = OrderedDict()
        d_tx["transactionHash"] = tx_hash
        d_tx["blockNumber"] = parsed["blockNumber"]
        d_tx["address"] = sanitize_address(parsed["account"])
        d_tx["status"] = status
        d_tx["event"] = 'FreeStableTokenRedeem'
        d_tx["tokenInvolved"] = 'STABLE'
        d_tx["userAmount"] = str(Web3.from_wei(parsed["amount"], 'ether'))
        d_tx["lastUpdatedAt"] = datetime.datetime.now()
        d_tx["RBTCAmount"] = str(parsed["reserveTotal"])
        usd_amount = Web3.from_wei(parsed["reserveTotal"],
                                   'ether') * Web3.from_wei(parsed["reservePrice"],
                                                            'ether')
        d_tx["USDAmount"] = str(int(usd_amount * self.precision))
        d_tx["amount"] = str(parsed["amount"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx['confirmingPercent'] = confirming_percent
        if "reserveTokenMarkup" in parsed:
            rbtc_commission = parsed["commission"] + parsed["reserveTokenMarkup"]
        else:
            rbtc_commission = parsed["commission"] + parsed["btcMarkup"]
        moc_commission = parsed["mocCommissionValue"] + parsed["mocMarkup"]
        if rbtc_commission > 0:
            usd_commission = Web3.from_wei(rbtc_commission, 'ether') * Web3.from_wei(parsed["reservePrice"], 'ether')
        else:
            usd_commission = Web3.from_wei(moc_commission, 'ether') * Web3.from_wei(parsed["mocPrice"], 'ether')
        d_tx["rbtcCommission"] = str(rbtc_commission)
        d_tx["USDCommission"] = str(int(usd_commission * self.precision))
        d_tx["rbtcInterests"] = str(parsed["interests"])
        usd_interest = Web3.from_wei(parsed["interests"], 'ether') * Web3.from_wei(
            parsed["reservePrice"], 'ether')
        d_tx["USDInterests"] = str(int(usd_interest * self.precision))
        d_tx["isPositive"] = False
        d_tx["reservePrice"] = str(parsed["reservePrice"])
        d_tx["mocCommissionValue"] = str(moc_commission)
        d_tx["mocPrice"] = str(parsed["mocPrice"])
        gas_fee = parsed["gasUsed"] * Web3.from_wei(parsed["gasPrice"], 'ether')
        d_tx["gasFeeRBTC"] = str(int(gas_fee * self.precision))
        if self.options['app_mode'] != "RRC20":
            d_tx["gasFeeUSD"] = str(int(
                gas_fee * Web3.from_wei(parsed["reservePrice"],
                                        'ether') * self.precision))
        rbtc_total = parsed["reserveTotal"] - parsed["commission"] - int(
            gas_fee * self.precision)
        d_tx["RBTCTotal"] = str(rbtc_total)
        rbtc_total_ether = Web3.from_wei(abs(rbtc_total), 'ether')
        if rbtc_total < 0:
            rbtc_total_ether = -rbtc_total_ether
        usd_total = rbtc_total_ether * Web3.from_wei(parsed["reservePrice"],
                                                     'ether')
        d_tx["USDTotal"] = str(int(usd_total * self.precision))
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed['createdAt']
        d_tx["gas"] = parsed['gas']
        d_tx["gasPrice"] = str(parsed['gasPrice'])
        d_tx["gasUsed"] = parsed['gasUsed']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)
        d_tx['post_id'] = post_id

        log.info("Tx {0} From: [{1}] Amount: {2} Tx Hash: {3}".format(
            d_tx["event"],
            d_tx["address"],
            d_tx["amount"],
            tx_hash))

        return parsed


class EventTokenTransfer(BaseEvent):

    def __init__(self, options, connection_helper, filter_contracts_addresses, block_info, token_involved):

        self.options = options
        self.connection_helper = connection_helper
        self.filter_contracts_addresses = filter_contracts_addresses
        self.block_info = block_info
        self.token_involved = token_involved

        super().__init__(options, connection_helper, filter_contracts_addresses, block_info)

    # def parse_event(self, parsed_receipt, decoded_event):
    #
    #     # decode event to support write in mongo
    #     parsed_receipt['from'] = decoded_event['from'].lower()
    #     parsed_receipt['to'] = decoded_event['to'].lower()
    #     parsed_receipt['value'] = str(decoded_event['value'])
    #
    #     return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        address_from_contract = '0x0000000000000000000000000000000000000000'
        address_not_allowed = [str.lower(address_from_contract), self.filter_contracts_addresses]

        if sanitize_address(parsed['from']) in address_not_allowed or \
                sanitize_address(parsed['to']) in address_not_allowed:
            # skip transfers to our contracts
            return parsed

        # status of tx
        status, confirmation_time, confirming_percent = self.confirming_percent(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        # FROM
        d_tx = OrderedDict()
        d_tx["address"] = sanitize_address(parsed["from"])
        d_tx["blockNumber"] = parsed_receipt["blockNumber"]
        d_tx["event"] = 'Transfer'
        d_tx["transactionHash"] = tx_hash
        d_tx["amount"] = str(parsed["value"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx['confirmingPercent'] = confirming_percent
        d_tx["isPositive"] = False
        d_tx["lastUpdatedAt"] = datetime.datetime.now()
        d_tx["otherAddress"] = sanitize_address(parsed["to"])
        d_tx["status"] = status
        d_tx["tokenInvolved"] = self.token_involved
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed_receipt['createdAt']
        d_tx["gas"] = parsed['gas']
        d_tx["gasPrice"] = str(parsed['gasPrice'])
        d_tx["gasUsed"] = parsed['gasUsed']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)

        # TO
        d_tx = OrderedDict()
        d_tx["address"] = sanitize_address(parsed["to"])
        d_tx["blockNumber"] = parsed_receipt["blockNumber"]
        d_tx["event"] = 'Transfer'
        d_tx["transactionHash"] = tx_hash
        d_tx["amount"] = str(parsed["value"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx['confirmingPercent'] = confirming_percent
        d_tx["isPositive"] = True
        d_tx["lastUpdatedAt"] = datetime.datetime.now()
        d_tx["otherAddress"] = sanitize_address(parsed["from"])
        d_tx["status"] = status
        d_tx["tokenInvolved"] = self.token_involved
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed_receipt['createdAt']
        d_tx["gas"] = parsed['gas']
        d_tx["gasPrice"] = str(parsed['gasPrice'])
        d_tx["gasUsed"] = parsed['gasUsed']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)

        log.info("Tx {0} From: [{1}] Amount: {2} Tx Hash: {3}".format(
            d_tx["event"],
            d_tx["address"],
            d_tx["amount"],
            tx_hash))

        return parsed


class EventOMOCIncentiveV2ClaimOK(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_IncentiveV2_ClaimOK')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["recipient"] = sanitize_address(parsed["recipient"]).lower()
        d_event["origin"] = sanitize_address(parsed["origin"]).lower()
        d_event["value"] = str(parsed["value"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: IncentiveV2_ClaimOK :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCVestingFactoryVestingCreated(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_VestingFactory_VestingCreated')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["vesting"] = sanitize_address(parsed["vesting"]).lower()
        d_event["holder"] = sanitize_address(parsed["holder"]).lower()
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: VestingFactory_VestingCreated :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCDelayMachinePaymentCancel(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_DelayMachine_PaymentCancel')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["id"] = oper_id_to_int(parsed["id"])
        d_event["source"] = sanitize_address(parsed["source"]).lower()
        d_event["destination"] = sanitize_address(parsed["destination"]).lower()
        d_event["amount"] = str(parsed["amount"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: DelayMachine_PaymentCancel :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        # Write to Omoc Operation collection
        collection = self.connection_helper.mongo_collection('omoc_operations')
        d_oper = OrderedDict()
        d_oper["hash"] = tx_hash
        d_oper["id_event"] = id_event
        d_oper["blockNumber"] = int(parsed["blockNumber"])
        d_oper["operation"] = 'DelayMachine_PaymentCancel'
        d_oper["id"] = oper_id_to_int(parsed["id"])
        d_oper["source"] = sanitize_address(parsed["source"]).lower()
        d_oper["destination"] = sanitize_address(parsed["destination"]).lower()
        d_oper["amount"] = str(parsed["amount"])
        d_oper["createdAt"] = parsed["createdAt"]
        d_oper["lastUpdatedAt"] = datetime.datetime.now()
        d_oper["last_block_indexed"] = int(parsed["blockNumber"])

        collection.find_one_and_update(
            {"id_event": d_oper["id_event"]},
            {"$set": d_oper},
            upsert=True)

        return d_event, parsed


class EventOMOCDelayMachinePaymentDeposit(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_DelayMachine_PaymentDeposit')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["id"] = oper_id_to_int(parsed["id"])
        d_event["source"] = sanitize_address(parsed["source"]).lower()
        d_event["destination"] = sanitize_address(parsed["destination"]).lower()
        d_event["amount"] = str(parsed["amount"])
        d_event["expiration"] = int(parsed["expiration"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: DelayMachine_PaymentDeposit :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        # Write to Omoc Operation collection
        collection = self.connection_helper.mongo_collection('omoc_operations')
        d_oper = OrderedDict()
        d_oper["hash"] = tx_hash
        d_oper["id_event"] = id_event
        d_oper["blockNumber"] = int(parsed["blockNumber"])
        d_oper["operation"] = 'DelayMachine_PaymentDeposit'
        d_oper["id"] = oper_id_to_int(parsed["id"])
        d_oper["source"] = sanitize_address(parsed["source"]).lower()
        d_oper["destination"] = sanitize_address(parsed["destination"]).lower()
        d_oper["amount"] = str(parsed["amount"])
        d_oper["expiration"] = int(parsed["expiration"])
        d_oper["createdAt"] = parsed["createdAt"]
        d_oper["lastUpdatedAt"] = datetime.datetime.now()
        d_oper["last_block_indexed"] = int(parsed["blockNumber"])

        collection.find_one_and_update(
            {"id_event": d_oper["id_event"]},
            {"$set": d_oper},
            upsert=True)

        return d_event, parsed


class EventOMOCDelayMachinePaymentWithdraw(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_DelayMachine_PaymentWithdraw')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["id"] = oper_id_to_int(parsed["id"])
        d_event["source"] = sanitize_address(parsed["source"]).lower()
        d_event["destination"] = sanitize_address(parsed["destination"]).lower()
        d_event["amount"] = str(parsed["amount"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: DelayMachine_PaymentWithdraw :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        # Write to Omoc Operation collection
        collection = self.connection_helper.mongo_collection('omoc_operations')
        d_oper = OrderedDict()
        d_oper["hash"] = tx_hash
        d_oper["id_event"] = id_event
        d_oper["blockNumber"] = int(parsed["blockNumber"])
        d_oper["operation"] = 'DelayMachine_PaymentWithdraw'
        d_oper["id"] = oper_id_to_int(parsed["id"])
        d_oper["source"] = sanitize_address(parsed["source"]).lower()
        d_oper["destination"] = sanitize_address(parsed["destination"]).lower()
        d_oper["amount"] = str(parsed["amount"])
        d_oper["createdAt"] = parsed["createdAt"]
        d_oper["lastUpdatedAt"] = datetime.datetime.now()
        d_oper["last_block_indexed"] = int(parsed["blockNumber"])

        collection.find_one_and_update(
            {"id_event": d_oper["id_event"]},
            {"$set": d_oper},
            upsert=True)

        return d_event, parsed


class EventOMOCSupportersAddStake(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_Supporters_AddStake')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["subaccount"] = sanitize_address(parsed["subaccount"]).lower()
        d_event["sender"] = sanitize_address(parsed["sender"]).lower()
        d_event["amount"] = str(parsed["amount"])
        d_event["mocs"] = str(parsed["mocs"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: Supporters_AddStake {0}".format(d_event["id_event"]))

        # Write to Omoc Operation collection
        collection = self.connection_helper.mongo_collection('omoc_operations')
        d_oper = OrderedDict()
        d_oper["hash"] = tx_hash
        d_oper["id_event"] = id_event
        d_oper["blockNumber"] = int(parsed["blockNumber"])
        d_oper["operation"] = 'Supporters_AddStake'
        d_oper["user"] = sanitize_address(parsed["user"]).lower()
        d_oper["subaccount"] = sanitize_address(parsed["subaccount"]).lower()
        d_oper["sender"] = sanitize_address(parsed["sender"]).lower()
        d_oper["amount"] = str(parsed["amount"])
        d_oper["mocs"] = str(parsed["mocs"])
        d_oper["createdAt"] = parsed["createdAt"]
        d_oper["lastUpdatedAt"] = datetime.datetime.now()
        d_oper["last_block_indexed"] = int(parsed["blockNumber"])

        collection.find_one_and_update(
            {"id_event": d_oper["id_event"]},
            {"$set": d_oper},
            upsert=True)

        return d_event, parsed


class EventOMOCSupportersCancelEarnings(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_Supporters_CancelEarnings')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["earnings"] = str(parsed["earnings"])
        d_event["start"] = int(parsed["start"])
        d_event["end"] = int(parsed["end"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: Supporters_CancelEarnings :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCSupportersPayEarnings(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_Supporters_PayEarnings')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["earnings"] = str(parsed["earnings"])
        d_event["start"] = int(parsed["start"])
        d_event["end"] = int(parsed["end"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: Supporters_PayEarnings :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCSupportersWithdraw(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_Supporters_Withdraw')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["msgSender"] = sanitize_address(parsed["msgSender"]).lower()
        d_event["subaccount"] = sanitize_address(parsed["subaccount"]).lower()
        d_event["receiver"] = sanitize_address(parsed["receiver"]).lower()
        d_event["mocs"] = str(parsed["mocs"])
        d_event["blockNum"] = int(parsed["blockNumber"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: Supporters_Withdraw :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        # Write to Omoc Operation collection
        collection = self.connection_helper.mongo_collection('omoc_operations')
        d_oper = OrderedDict()
        d_oper["hash"] = tx_hash
        d_oper["id_event"] = id_event
        d_oper["blockNumber"] = int(parsed["blockNumber"])
        d_oper["operation"] = 'Supporters_Withdraw'
        d_oper["msgSender"] = sanitize_address(parsed["msgSender"]).lower()
        d_oper["subaccount"] = sanitize_address(parsed["subaccount"]).lower()
        d_oper["receiver"] = sanitize_address(parsed["receiver"]).lower()
        d_oper["amount"] = str(parsed["mocs"])
        d_oper["mocs"] = str(parsed["mocs"])
        d_oper["blockNum"] = int(parsed["blockNumber"])
        d_oper["createdAt"] = parsed["createdAt"]
        d_oper["lastUpdatedAt"] = datetime.datetime.now()
        d_oper["last_block_indexed"] = int(parsed["blockNumber"])

        collection.find_one_and_update(
            {"id_event": d_oper["id_event"]},
            {"$set": d_oper},
            upsert=True)

        return d_event, parsed


class EventOMOCSupportersWithdrawStake(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_Supporters_WithdrawStake')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["subaccount"] = sanitize_address(parsed["subaccount"]).lower()
        d_event["destination"] = sanitize_address(parsed["destination"]).lower()
        d_event["amount"] = str(parsed["amount"])
        d_event["mocs"] = str(parsed["mocs"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: Supporters_WithdrawStake :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        # Write to Omoc Operation collection
        collection = self.connection_helper.mongo_collection('omoc_operations')
        d_oper = OrderedDict()
        d_oper["hash"] = tx_hash
        d_oper["id_event"] = id_event
        d_oper["blockNumber"] = int(parsed["blockNumber"])
        d_oper["operation"] = 'Supporters_WithdrawStake'
        d_oper["user"] = sanitize_address(parsed["user"]).lower()
        d_oper["subaccount"] = sanitize_address(parsed["subaccount"]).lower()
        d_oper["destination"] = sanitize_address(parsed["destination"]).lower()
        d_oper["amount"] = str(parsed["amount"])
        d_oper["mocs"] = str(parsed["mocs"])
        d_oper["createdAt"] = parsed["createdAt"]
        d_oper["lastUpdatedAt"] = datetime.datetime.now()
        d_oper["last_block_indexed"] = int(parsed["blockNumber"])

        collection.find_one_and_update(
            {"id_event": d_oper["id_event"]},
            {"$set": d_oper},
            upsert=True)

        return d_event, parsed


class EventOMOCVotingMachinePreVoteEvent(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_VotingMachine_PreVoteEvent')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["proposal"] = sanitize_address(parsed["proposal"]).lower()
        d_event["stake"] = str(parsed["stake"])
        d_event["round"] = int(parsed["round"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: VotingMachine_PreVoteEvent :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCVotingMachineVoteEvent(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_VotingMachine_VoteEvent')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["proposal"] = sanitize_address(parsed["proposal"]).lower()
        d_event["inFavorAgainst"] = bool(parsed["inFavorAgainst"])
        d_event["stake"] = str(parsed["stake"])
        d_event["round"] = int(parsed["round"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: VotingMachine_VoteEvent :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCVotingMachinePreVoteStepEvent(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_VotingMachine_PreVoteStepEvent')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["proposal"] = sanitize_address(parsed["proposal"]).lower()
        d_event["votesInFavor"] = str(parsed["votesInFavor"])
        d_event["round"] = int(parsed["round"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: VotingMachine_PreVoteStepEvent :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCVotingMachineVoteStepEvent(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_VotingMachine_VoteStepEvent')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["proposal"] = sanitize_address(parsed["proposal"]).lower()
        d_event["round"] = int(parsed["round"])
        d_event["result"] = int(parsed["result"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: VotingMachine_VoteStepEvent :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCVotingMachineAcceptedStepEvent(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_VotingMachine_AcceptedStepEvent')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["proposal"] = sanitize_address(parsed["proposal"]).lower()
        d_event["round"] = int(parsed["round"])
        d_event["success"] = bool(parsed["success"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: VotingMachine_AcceptedStepEvent :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCVotingMachineUnregisterEvent(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection
        collection = self.connection_helper.mongo_collection('event_VotingMachine_UnregisterEvent')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["proposal"] = sanitize_address(parsed["proposal"]).lower()
        d_event["round"] = int(parsed["round"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        # remove old document with only hash as id and replace with id_event as unique id
        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: VotingMachine_UnregisterEvent :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCOracleManagerOracleRegistered(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_OracleManager_OracleRegistered')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["caller"] = sanitize_address(parsed["caller"]).lower()
        d_event["addr"] = sanitize_address(parsed["addr"]).lower()
        d_event["internetName"] = parsed["internetName"]
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: OracleManager_OracleRegistered :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCOracleManagerOracleStakeAdded(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_OracleManager_OracleStakeAdded')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["caller"] = sanitize_address(parsed["caller"]).lower()
        d_event["addr"] = sanitize_address(parsed["addr"]).lower()
        d_event["stake"] = str(parsed["stake"])
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: OracleManager_OracleStakeAdded :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCOracleManagerOracleSubscribed(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_OracleManager_OracleSubscribed')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["caller"] = sanitize_address(parsed["caller"]).lower()
        d_event["coinpair"] = bytes32_to_hex(parsed["coinpair"])
        d_event["coinPairName"] = bytes32_to_text(parsed["coinpair"])
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: OracleManager_OracleSubscribed :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCOracleManagerOracleUnsubscribed(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_OracleManager_OracleUnsubscribed')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["caller"] = sanitize_address(parsed["caller"]).lower()
        d_event["coinpair"] = bytes32_to_hex(parsed["coinpair"])
        d_event["coinPairName"] = bytes32_to_text(parsed["coinpair"])
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: OracleManager_OracleUnsubscribed :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCOracleManagerOracleRemoved(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_OracleManager_OracleRemoved')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["caller"] = sanitize_address(parsed["caller"]).lower()
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: OracleManager_OracleRemoved :: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class BaseCoinPairPriceEvent(BaseEvent):
    """ CoinPairPrice has one deployment per coin pair; keep track of which one emitted """

    def __init__(self, options, connection_helper, filter_contracts_addresses, block_info,
                 coin_pair=None, contract_address=None):

        self.coin_pair = coin_pair
        self.contract_address = (contract_address or "").lower()

        super().__init__(options, connection_helper, filter_contracts_addresses, block_info)

    def parse_event(self, parsed_receipt, decoded_event):
        """ Like BaseEvent.parse_event, but event params win over colliding receipt keys
        instead of raising: PricePublished / EmergencyPricePublished carry their own
        ``blockNumber``. Handlers still read receipt-level values from ``parsed_receipt``. """
        fields = {field['name']: field['value'] for field in decoded_event}
        return {**parsed_receipt, **fields}


class EventOMOCCoinPairPricePricePublished(BaseCoinPairPriceEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_CoinPairPrice_PricePublished')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["contractAddress"] = self.contract_address
        d_event["coinPair"] = self.coin_pair
        d_event["sender"] = sanitize_address(parsed["sender"]).lower()
        d_event["price"] = str(parsed["price"])
        d_event["votedOracle"] = sanitize_address(parsed["votedOracle"]).lower()
        d_event["priceBlockNumber"] = str(parsed["blockNumber"])
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: CoinPairPrice_PricePublished :: {0} :: {1}".format(self.coin_pair, d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCCoinPairPriceEmergencyPricePublished(BaseCoinPairPriceEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_CoinPairPrice_EmergencyPricePublished')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["contractAddress"] = self.contract_address
        d_event["coinPair"] = self.coin_pair
        d_event["sender"] = sanitize_address(parsed["sender"]).lower()
        d_event["price"] = str(parsed["price"])
        d_event["votedOracle"] = sanitize_address(parsed["votedOracle"]).lower()
        d_event["priceBlockNumber"] = str(parsed["blockNumber"])
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: CoinPairPrice_EmergencyPricePublished :: {0} :: {1}".format(
            self.coin_pair, d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCCoinPairPriceForcedPriceQueryModeSet(BaseCoinPairPriceEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_CoinPairPrice_ForcedPriceQueryModeSet')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["contractAddress"] = self.contract_address
        d_event["coinPair"] = self.coin_pair
        d_event["setter"] = sanitize_address(parsed["setter"]).lower()
        d_event["mode"] = int(parsed["mode"])
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: CoinPairPrice_ForcedPriceQueryModeSet :: {0} :: {1}".format(
            self.coin_pair, d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCCoinPairPriceOracleRewardTransfer(BaseCoinPairPriceEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_CoinPairPrice_OracleRewardTransfer')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["contractAddress"] = self.contract_address
        d_event["coinPair"] = self.coin_pair
        d_event["roundNumber"] = int(parsed["roundNumber"])
        d_event["oracleOwnerAddress"] = sanitize_address(parsed["oracleOwnerAddress"]).lower()
        d_event["toOwnerAddress"] = sanitize_address(parsed["toOwnerAddress"]).lower()
        d_event["amount"] = str(parsed["amount"])
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: CoinPairPrice_OracleRewardTransfer :: {0} :: {1}".format(
            self.coin_pair, d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCCoinPairPriceNewRound(BaseCoinPairPriceEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_CoinPairPrice_NewRound')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        selected_oracles = [sanitize_address(a).lower() for a in parsed.get("selectedOracles", [])]

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["contractAddress"] = self.contract_address
        d_event["coinPair"] = self.coin_pair
        d_event["caller"] = sanitize_address(parsed["caller"]).lower()
        d_event["number"] = int(parsed["number"])
        d_event["totalPoints"] = str(parsed["totalPoints"])
        d_event["startBlock"] = int(parsed["startBlock"])
        d_event["lockPeriodTimestamp"] = int(parsed["lockPeriodTimestamp"])
        d_event["selectedOracles"] = selected_oracles
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: CoinPairPrice_NewRound :: {0} :: {1}".format(self.coin_pair, d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventOMOCCoinPairPriceOracleAutoUnsubscribed(BaseCoinPairPriceEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_CoinPairPrice_OracleAutoUnsubscribed')

        tx_hash = parsed_receipt['hash']
        id_event = "{0}:{1}".format(tx_hash, parsed_receipt['logIndex'])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed_receipt["blockNumber"])
        d_event["contractAddress"] = self.contract_address
        d_event["coinPair"] = self.coin_pair
        d_event["oracleOwnerAddr"] = sanitize_address(parsed["oracleOwnerAddr"]).lower()
        d_event["coinPairId"] = bytes32_to_hex(parsed["coinPair"])
        d_event["roundNumber"] = int(parsed["roundNumber"])
        d_event["missedSignatureRounds"] = int(parsed["missedSignatureRounds"])
        d_event["createdAt"] = parsed_receipt["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: CoinPairPrice_OracleAutoUnsubscribed :: {0} :: {1}".format(
            self.coin_pair, d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed
