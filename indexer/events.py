import datetime
from collections import OrderedDict
from web3 import Web3

from .logger import log


def sanitize_address(address):
    return Web3.to_checksum_address(address.replace("0x000000000000000000000000", "0x"))


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


class EventFastBtcBridgeNewBitcoinTransfer(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection transaction
        collection_bridge = self.connection_helper.mongo_collection('FastBtcBridge')

        tx_hash = parsed['hash']

        d_tx = dict()
        d_tx["transactionHash"] = tx_hash
        d_tx["transactionHashLastUpdated"] = tx_hash
        d_tx["blockNumber"] = parsed["blockNumber"]
        d_tx["type"] = 'PEG_OUT'
        d_tx["transferId"] = str(parsed["transferId"])
        d_tx["btcAddress"] = parsed["btcAddress"]
        d_tx["nonce"] = parsed["nonce"]
        d_tx["amountSatoshi"] = str(parsed["amountSatoshi"])
        d_tx["feeSatoshi"] = str(parsed["feeSatoshi"])
        d_tx["rskAddress"] = sanitize_address(parsed["rskAddress"])
        d_tx["status"] = 0
        d_tx["timestamp"] = parsed["timestamp"]
        d_tx["updated"] = parsed["timestamp"]
        d_tx["processLogs"] = True

        post_id = collection_bridge.find_one_and_update(
            {"transferId": d_tx["transferId"]},
            {"$set": d_tx},
            upsert=True)
        d_tx['post_id'] = post_id

        log.info("EVENT::NewBitcoinTransfer::{0}".format(d_tx["transferId"]))
        log.info(d_tx)

        return parsed


class EventFastBtcBridgeBitcoinTransferStatusUpdated(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # get collection transaction
        collection_bridge = self.connection_helper.mongo_collection('FastBtcBridge')

        d_tx = dict()
        d_tx["transactionHashLastUpdated"] = parsed["hash"]
        d_tx["status"] = parsed["newStatus"]
        d_tx["transferId"] = str(parsed["transferId"])
        d_tx["updated"] = parsed["timestamp"]

        post_id = collection_bridge.find_one_and_update(
            {"transferId": d_tx["transferId"]},
            {"$set": d_tx},
            upsert=False)
        d_tx['post_id'] = post_id

        log.info("EVENT::BitcoinTransferStatusUpdated::{0}".format(d_tx["transferId"]))
        log.info(d_tx)

        return parsed


# ---------------------------------------------------------------------------
# Lending and Borrowing events (MocLendingManager / MocLendingQueue)
# ---------------------------------------------------------------------------

# lending_user_operations status (same codes as indexer v3)
TX_STATUS_QUEUE_ERROR = -1  # queued but errored before execution
TX_STATUS_QUEUED = 0        # waiting in the lending queue
TX_STATUS_EXECUTED = 1      # executed

LENDING_OPER_TYPE = {0: 'NONE', 1: 'BORROW', 2: 'REMOVE_AC_FROM_VAULT', 3: 'REPAY_WITH_AC'}
# Final lending event emitted when a queued operation of this type executes
LENDING_OPER_TYPE_EVENT_NAME = {1: 'Borrow', 2: 'RemoveACfromVault', 3: 'RepayWithAC'}


class EventLendingDeposit(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_Deposit')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["recipient"] = sanitize_address(parsed["recipient"]).lower()
        d_event["tpToken"] = sanitize_address(parsed["tpToken"])
        d_event["tpAmount"] = str(parsed["tpAmount"])
        d_event["depositUnits"] = str(parsed["depositUnits"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
        user_ops_col.find_one_and_update(
            {"id_event": id_event},
            {"$set": {
                "id_event": id_event,
                "hash": tx_hash,
                "blockNumber": d_event["blockNumber"],
                "eventName": "Deposit",
                "user": d_event["user"],
                "tpToken": d_event["tpToken"],
                "createdAt": d_event["createdAt"],
                "lastUpdatedAt": d_event["lastUpdatedAt"],
                "status": TX_STATUS_EXECUTED,
                "extra": {
                    "recipient": d_event["recipient"],
                    "tpAmount": d_event["tpAmount"],
                    "depositUnits": d_event["depositUnits"],
                },
            }},
            upsert=True)

        log.info("Event :: Lending_Deposit :: id: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingWithdraw(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_Withdraw')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["recipient"] = sanitize_address(parsed["recipient"]).lower()
        d_event["tpToken"] = sanitize_address(parsed["tpToken"])
        d_event["depositUnits"] = str(parsed["depositUnits"])
        d_event["tpAmount"] = str(parsed["tpAmount"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
        user_ops_col.find_one_and_update(
            {"id_event": id_event},
            {"$set": {
                "id_event": id_event,
                "hash": tx_hash,
                "blockNumber": d_event["blockNumber"],
                "eventName": "Withdraw",
                "user": d_event["user"],
                "tpToken": d_event["tpToken"],
                "createdAt": d_event["createdAt"],
                "lastUpdatedAt": d_event["lastUpdatedAt"],
                "status": TX_STATUS_EXECUTED,
                "extra": {
                    "recipient": d_event["recipient"],
                    "depositUnits": d_event["depositUnits"],
                    "tpAmount": d_event["tpAmount"],
                },
            }},
            upsert=True)

        log.info("Event :: Lending_Withdraw :: id: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingAddACtoVault(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_AddACtoVault')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["recipient"] = sanitize_address(parsed["recipient"]).lower()
        d_event["tpToken"] = sanitize_address(parsed["tpToken"])
        d_event["mocBucket"] = sanitize_address(parsed["mocBucket"])
        d_event["acAmount"] = str(parsed["acAmount"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
        user_ops_col.find_one_and_update(
            {"id_event": id_event},
            {"$set": {
                "id_event": id_event,
                "hash": tx_hash,
                "blockNumber": d_event["blockNumber"],
                "eventName": "AddACtoVault",
                "user": d_event["user"],
                "tpToken": d_event["tpToken"],
                "createdAt": d_event["createdAt"],
                "lastUpdatedAt": d_event["lastUpdatedAt"],
                "status": TX_STATUS_EXECUTED,
                "extra": {
                    "recipient": d_event["recipient"],
                    "mocBucket": d_event["mocBucket"],
                    "acAmount": d_event["acAmount"],
                },
            }},
            upsert=True)

        log.info("Event :: Lending_AddACtoVault :: id: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingRemoveACfromVault(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_RemoveACfromVault')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["recipient"] = sanitize_address(parsed["recipient"]).lower()
        d_event["tpToken"] = sanitize_address(parsed["tpToken"])
        d_event["mocBucket"] = sanitize_address(parsed["mocBucket"])
        d_event["acAmount"] = str(parsed["acAmount"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
        user_ops_col.find_one_and_update(
            {"id_event": id_event},
            {"$set": {
                "id_event": id_event,
                "hash": tx_hash,
                "blockNumber": d_event["blockNumber"],
                "eventName": "RemoveACfromVault",
                "user": d_event["user"],
                "tpToken": d_event["tpToken"],
                "createdAt": d_event["createdAt"],
                "lastUpdatedAt": d_event["lastUpdatedAt"],
                "status": TX_STATUS_EXECUTED,
                "extra": {
                    "recipient": d_event["recipient"],
                    "mocBucket": d_event["mocBucket"],
                    "acAmount": d_event["acAmount"],
                },
            }},
            upsert=True)

        log.info("Event :: Lending_RemoveACfromVault :: id: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingBorrow(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_Borrow')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["recipient"] = sanitize_address(parsed["recipient"]).lower()
        d_event["tpToken"] = sanitize_address(parsed["tpToken"])
        d_event["mocBucket"] = sanitize_address(parsed["mocBucket"])
        d_event["tpAmount"] = str(parsed["tpAmount"])
        d_event["creditUnits"] = str(parsed["creditUnits"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
        user_ops_col.find_one_and_update(
            {"id_event": id_event},
            {"$set": {
                "id_event": id_event,
                "hash": tx_hash,
                "blockNumber": d_event["blockNumber"],
                "eventName": "Borrow",
                "user": d_event["user"],
                "tpToken": d_event["tpToken"],
                "createdAt": d_event["createdAt"],
                "lastUpdatedAt": d_event["lastUpdatedAt"],
                "status": TX_STATUS_EXECUTED,
                "extra": {
                    "recipient": d_event["recipient"],
                    "mocBucket": d_event["mocBucket"],
                    "tpAmount": d_event["tpAmount"],
                    "creditUnits": d_event["creditUnits"],
                },
            }},
            upsert=True)

        log.info("Event :: Lending_Borrow :: id: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingRepay(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_Repay')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["recipient"] = sanitize_address(parsed["recipient"]).lower()
        d_event["tpToken"] = sanitize_address(parsed["tpToken"])
        d_event["mocBucket"] = sanitize_address(parsed["mocBucket"])
        d_event["creditUnits"] = str(parsed["creditUnits"])
        d_event["tpAmount"] = str(parsed["tpAmount"])
        d_event["tpToFeeFlow"] = str(parsed["tpToFeeFlow"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
        user_ops_col.find_one_and_update(
            {"id_event": id_event},
            {"$set": {
                "id_event": id_event,
                "hash": tx_hash,
                "blockNumber": d_event["blockNumber"],
                "eventName": "Repay",
                "user": d_event["user"],
                "tpToken": d_event["tpToken"],
                "createdAt": d_event["createdAt"],
                "lastUpdatedAt": d_event["lastUpdatedAt"],
                "status": TX_STATUS_EXECUTED,
                "extra": {
                    "recipient": d_event["recipient"],
                    "mocBucket": d_event["mocBucket"],
                    "creditUnits": d_event["creditUnits"],
                    "tpAmount": d_event["tpAmount"],
                    "tpToFeeFlow": d_event["tpToFeeFlow"],
                },
            }},
            upsert=True)

        log.info("Event :: Lending_Repay :: id: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingRepayWithAC(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_RepayWithAC')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["tpToken"] = sanitize_address(parsed["tpToken"])
        d_event["mocBucket"] = sanitize_address(parsed["mocBucket"])
        d_event["creditUnits"] = str(parsed["creditUnits"])
        d_event["acSold"] = str(parsed["acSold"])
        d_event["tpAmount"] = str(parsed["tpAmount"])
        d_event["tpToFeeFlow"] = str(parsed["tpToFeeFlow"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
        user_ops_col.find_one_and_update(
            {"id_event": id_event},
            {"$set": {
                "id_event": id_event,
                "hash": tx_hash,
                "blockNumber": d_event["blockNumber"],
                "eventName": "RepayWithAC",
                "user": d_event["user"],
                "tpToken": d_event["tpToken"],
                "createdAt": d_event["createdAt"],
                "lastUpdatedAt": d_event["lastUpdatedAt"],
                "status": TX_STATUS_EXECUTED,
                "extra": {
                    "mocBucket": d_event["mocBucket"],
                    "creditUnits": d_event["creditUnits"],
                    "acSold": d_event["acSold"],
                    "tpAmount": d_event["tpAmount"],
                    "tpToFeeFlow": d_event["tpToFeeFlow"],
                },
            }},
            upsert=True)

        log.info("Event :: Lending_RepayWithAC :: id: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingLiquidate(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_Liquidate')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["liquidator"] = sanitize_address(parsed["liquidator"]).lower()
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["tpToken"] = sanitize_address(parsed["tpToken"])
        d_event["mocBucket"] = sanitize_address(parsed["mocBucket"])
        d_event["acSwapped"] = str(parsed["acSwapped"])
        d_event["tpPaid"] = str(parsed["tpPaid"])
        d_event["tpToFeeFlow"] = str(parsed["tpToFeeFlow"])
        d_event["isComplete"] = bool(parsed["isComplete"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
        user_ops_col.find_one_and_update(
            {"id_event": id_event},
            {"$set": {
                "id_event": id_event,
                "hash": tx_hash,
                "blockNumber": d_event["blockNumber"],
                "eventName": "Liquidate",
                "user": d_event["user"],
                "tpToken": d_event["tpToken"],
                "createdAt": d_event["createdAt"],
                "lastUpdatedAt": d_event["lastUpdatedAt"],
                "status": TX_STATUS_EXECUTED,
                "extra": {
                    "liquidator": d_event["liquidator"],
                    "mocBucket": d_event["mocBucket"],
                    "acSwapped": d_event["acSwapped"],
                    "tpPaid": d_event["tpPaid"],
                    "tpToFeeFlow": d_event["tpToFeeFlow"],
                    "isComplete": d_event["isComplete"],
                },
            }},
            upsert=True)

        log.info("Event :: Lending_Liquidate :: id: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingTPInjection(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_TPInjection')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["tpToken"] = sanitize_address(parsed["tpToken"])
        d_event["tpAmount"] = str(parsed["tpAmount"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        log.info("Event :: Lending_TPInjection :: id: {0}".format(d_event["id_event"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingOperationQueued(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_OperationQueued')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        oper_type_int = int(parsed["operType"])

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["operId"] = int(parsed["operId"])
        d_event["operType"] = oper_type_int
        d_event["operTypeName"] = LENDING_OPER_TYPE.get(oper_type_int, 'UNKNOWN')
        d_event["user"] = sanitize_address(parsed["user"]).lower()
        d_event["recipient"] = sanitize_address(parsed["recipient"]).lower()
        d_event["tpToken"] = sanitize_address(parsed["tpToken"])
        d_event["mocBucket"] = sanitize_address(parsed["mocBucket"])
        d_event["amount"] = str(parsed["amount"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        # Pending row in user history. OperationExecuted removes it (the final lending
        # event writes its own row); OperationError marks it as failed.
        executed_col = self.connection_helper.mongo_collection('event_Lending_OperationExecuted')
        if executed_col.find_one({"operId": d_event["operId"]}):
            log.warning("Event :: Lending_OperationQueued :: operId: {0} Skipping user operation, already executed".format(
                d_event["operId"]))
        else:
            user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
            user_ops_col.find_one_and_update(
                {"id_event": id_event},
                {"$set": {
                    "id_event": id_event,
                    "hash": tx_hash,
                    "blockNumber": d_event["blockNumber"],
                    "eventName": LENDING_OPER_TYPE_EVENT_NAME.get(oper_type_int, d_event["operTypeName"]),
                    "user": d_event["user"],
                    "tpToken": d_event["tpToken"],
                    "operId": d_event["operId"],
                    "createdAt": d_event["createdAt"],
                    "lastUpdatedAt": d_event["lastUpdatedAt"],
                    "extra": {
                        "recipient": d_event["recipient"],
                        "mocBucket": d_event["mocBucket"],
                        "operType": d_event["operType"],
                        "operTypeName": d_event["operTypeName"],
                        "amount": d_event["amount"],
                    },
                },
                    # only on insert: don't reset a row already marked as error on re-scan
                    "$setOnInsert": {"status": TX_STATUS_QUEUED}},
                upsert=True)

        log.info("Event :: Lending_OperationQueued :: operId: {0} type: {1}".format(
            d_event["operId"], d_event["operTypeName"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingOperationError(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_OperationError')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["operId"] = int(parsed["operId"])
        d_event["reason"] = parsed["reason"].hex() if isinstance(parsed["reason"], (bytes, bytearray)) else str(parsed["reason"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        # Mark the pending row in user history as failed
        user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
        user_ops_col.update_one(
            {"operId": d_event["operId"], "status": TX_STATUS_QUEUED},
            {"$set": {
                "status": TX_STATUS_QUEUE_ERROR,
                "errorHash": tx_hash,
                "reason": d_event["reason"],
                "lastUpdatedAt": d_event["lastUpdatedAt"],
            }})

        log.info("Event :: Lending_OperationError :: operId: {0}".format(d_event["operId"]))
        log.info(d_event)

        return d_event, parsed


class EventLendingOperationExecuted(BaseEvent):

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        collection = self.connection_helper.mongo_collection('event_Lending_OperationExecuted')

        tx_hash = parsed['hash']
        log_index = parsed['logIndex']
        id_event = "{0}:{1}".format(tx_hash, log_index)

        d_event = dict()
        d_event["hash"] = tx_hash
        d_event["id_event"] = id_event
        d_event["blockNumber"] = int(parsed["blockNumber"])
        d_event["executor"] = sanitize_address(parsed["executor"]).lower()
        d_event["operId"] = int(parsed["operId"])
        d_event["createdAt"] = parsed["createdAt"]
        d_event["lastUpdatedAt"] = datetime.datetime.now()

        remove_query = {"hash": d_event["hash"], "id_event": {"$exists": False}}
        if collection.find(remove_query):
            collection.delete_many(remove_query)

        collection.find_one_and_update(
            {"id_event": d_event["id_event"]},
            {"$set": d_event},
            upsert=True)

        # The final lending event (Borrow, RemoveACfromVault, RepayWithAC) in this tx
        # already has its own row, so drop the pending one
        user_ops_col = self.connection_helper.mongo_collection('lending_user_operations')
        user_ops_col.delete_many({"operId": d_event["operId"], "status": TX_STATUS_QUEUED})

        log.info("Event :: Lending_OperationExecuted :: operId: {0}".format(d_event["operId"]))
        log.info(d_event)

        return d_event, parsed
