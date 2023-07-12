import datetime
from collections import OrderedDict
from web3 import Web3

from .logger import log
from .models import DocumentTransactions


class BaseEvent:

    name = 'Name'
    precision = 10 ** 18

    def __init__(self, options, connection_helper, filter_contracts_addresses, block_info):

        self.options = options
        self.connection_helper = connection_helper
        self.filter_contracts_addresses = filter_contracts_addresses
        self.block_info = block_info

    def parse_event(self, parsed_receipt, decoded_event):
        return dict(**parsed_receipt, **decoded_event)

    def status_tx(self, parse_receipt):

        if parse_receipt["blockNumber"] - self.block_info['last_block'] > self.block_info['confirm_blocks']:
            status = 'confirmed'
            confirmation_time = self.block_info['block_ts']
        else:
            status = 'confirming'
            confirmation_time = None

        return status, confirmation_time


class EventMoCExchangeRiskProMint(BaseEvent):

    # def parse_event(self, parsed_receipt, decoded_event):
    #
    #     # decode event to support write in mongo
    #     parsed_receipt['account'] = decoded_event['account']
    #     parsed_receipt['amount'] = Web3.from_wei(decoded_event['amount'], 'ether')
    #     parsed_receipt['reserveTotal'] = Web3.from_wei(decoded_event['reserveTotal'], 'ether')
    #     parsed_receipt['commission'] = Web3.from_wei(decoded_event['commission'], 'ether')
    #     parsed_receipt['reservePrice'] = Web3.from_wei(decoded_event['reservePrice'], 'ether')
    #     parsed_receipt['mocCommissionValue'] = Web3.from_wei(decoded_event['mocCommissionValue'], 'ether')
    #     parsed_receipt['mocPrice'] = Web3.from_wei(decoded_event['mocPrice'], 'ether')
    #     if self.options['app_mode'] != "RRC20":
    #         parsed_receipt['btcMarkup'] = Web3.from_wei(decoded_event['btcMarkup'], 'ether')
    #     else:
    #         parsed_receipt['reserveTokenMarkup'] = Web3.from_wei(decoded_event['reserveTokenMarkup'], 'ether')
    #     parsed_receipt['mocMarkup'] = Web3.from_wei(decoded_event['mocMarkup'], 'ether')
    #     parsed_receipt['vendorAccount'] = decoded_event['vendorAccount']
    #
    #     return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # DocumentTransactions.objects(
        #     hash=parsed['hash'],
        #     blockNumber=parsed['blockNumber']
        # ).update_one(
        #     hash=parsed['hash'],
        #     blockNumber=parsed['blockNumber'],
        #     gas=parsed['gas'],
        #     gasPrice=str(parsed['gasPrice']),
        #     gasUsed=parsed['gasUsed'],
        #     processed=True,
        #     confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
        #     timestamp=parsed['timestamp'],
        #     eventName=parsed['eventName'],
        #     sender_=parsed['sender_'],
        #     recipient_=parsed['recipient_'],
        #     qTC_=parsed['qTC_'],
        #     qAC_=parsed['qAC_'],
        #     qACfee_=parsed['qACfee_'],
        #     createdAt=parsed["createdAt"],
        #     lastUpdatedAt=datetime.datetime.now(),
        #     upsert=True
        # )

        print("DEBUG 6>>>:")
        print(parsed)

        # status of tx
        status, confirmation_time = self.status_tx(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        d_tx = OrderedDict()
        d_tx["address"] = parsed["account"]
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

        print("DEBUG 5>>>>")
        print(parsed_receipt)

        gas_fee = parsed_receipt['gas_used'] * Web3.from_wei(parsed_receipt["gas_price"], 'ether')
        # gas_fee = self.tx_receipt.gas_used * Web3.fromWei(moc_tx['gasPrice'],
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

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['account'] = decoded_event['account']
        parsed_receipt['amount'] = Web3.from_wei(decoded_event['amount'], 'ether')
        parsed_receipt['reserveTotal'] = Web3.from_wei(decoded_event['reserveTotal'], 'ether')
        parsed_receipt['commission'] = Web3.from_wei(decoded_event['commission'], 'ether')
        parsed_receipt['reservePrice'] = Web3.from_wei(decoded_event['reservePrice'], 'ether')
        parsed_receipt['mocCommissionValue'] = Web3.from_wei(decoded_event['mocCommissionValue'], 'ether')
        parsed_receipt['mocPrice'] = Web3.from_wei(decoded_event['mocPrice'], 'ether')
        parsed_receipt['btcMarkup'] = Web3.from_wei(decoded_event['btcMarkup'], 'ether')
        parsed_receipt['mocMarkup'] = Web3.from_wei(decoded_event['mocMarkup'], 'ether')
        parsed_receipt['vendorAccount'] = decoded_event['vendorAccount']

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        # DocumentTransactions.objects(
        #     hash=parsed['hash'],
        #     blockNumber=parsed['blockNumber']
        # ).update_one(
        #     hash=parsed['hash'],
        #     blockNumber=parsed['blockNumber'],
        #     gas=parsed['gas'],
        #     gasPrice=str(parsed['gasPrice']),
        #     gasUsed=parsed['gasUsed'],
        #     processed=True,
        #     confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
        #     timestamp=parsed['timestamp'],
        #     eventName=parsed['eventName'],
        #     sender_=parsed['sender_'],
        #     recipient_=parsed['recipient_'],
        #     qTC_=parsed['qTC_'],
        #     qAC_=parsed['qAC_'],
        #     qACfee_=parsed['qACfee_'],
        #     createdAt=parsed["createdAt"],
        #     lastUpdatedAt=datetime.datetime.now(),
        #     upsert=True
        # )

        # status of tx
        status, confirmation_time = self.status_tx(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        d_tx = OrderedDict()
        d_tx["event"] = 'RiskProRedeem'
        d_tx["blockNumber"] = parsed_receipt["blockNumber"]
        d_tx["transactionHash"] = tx_hash
        d_tx["address"] = parsed["account"]
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
        gas_fee = parsed_receipt["gas_used"] * Web3.from_wei(parsed_receipt["gas_price"], 'ether')
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

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['from'] = decoded_event['from'].lower()
        parsed_receipt['to'] = decoded_event['to'].lower()
        parsed_receipt['value'] = str(decoded_event['value'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        address_from_contract = '0x0000000000000000000000000000000000000000'
        address_not_allowed = [str.lower(address_from_contract), self.filter_contracts_addresses]

        if parsed['from'] in address_not_allowed or \
                parsed['to'] in address_not_allowed:
            # skip transfers to our contracts
            return parsed

        # status of tx
        status, confirmation_time = self.status_tx(parsed)

        # get collection transaction
        collection_tx = self.connection_helper.mongo_collection('Transaction')

        tx_hash = parsed['hash']

        # FROM
        d_tx = OrderedDict()
        d_tx["address"] = parsed["from"]
        d_tx["blockNumber"] = parsed_receipt["blockNumber"]
        d_tx["event"] = 'Transfer'
        d_tx["transactionHash"] = tx_hash
        d_tx["amount"] = str(parsed["value"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx["isPositive"] = False
        d_tx["lastUpdatedAt"] = datetime.datetime.now()
        d_tx["otherAddress"] = parsed["to"]
        d_tx["status"] = status
        d_tx["tokenInvolved"] = self.token_involved
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed_receipt['createdAt']
        d_tx["gas"] = parsed['gas']
        d_tx["gasPrice"] = str(parsed['gas'])
        d_tx["gasUsed"] = parsed['gasUsed']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)

        # TO
        d_tx = OrderedDict()
        d_tx["address"] = parsed["to"]
        d_tx["blockNumber"] = parsed_receipt["blockNumber"]
        d_tx["event"] = 'Transfer'
        d_tx["transactionHash"] = tx_hash
        d_tx["amount"] = str(parsed["value"])
        d_tx["confirmationTime"] = confirmation_time
        d_tx["isPositive"] = True
        d_tx["lastUpdatedAt"] = datetime.datetime.now()
        d_tx["otherAddress"] = parsed["from"]
        d_tx["status"] = status
        d_tx["tokenInvolved"] = self.token_involved
        d_tx["processLogs"] = True
        d_tx["createdAt"] = parsed_receipt['createdAt']

        post_id = collection_tx.find_one_and_update(
            {"transactionHash": tx_hash,
             "address": d_tx["address"],
             "event": d_tx["event"]},
            {"$set": d_tx},
            upsert=True)

        # DocumentTransactions.objects(
        #     hash=parsed['hash'],
        #     blockNumber=parsed['blockNumber']
        # ).update_one(
        #     hash=parsed['hash'],
        #     blockNumber=parsed['blockNumber'],
        #     gas=parsed['gas'],
        #     gasPrice=str(parsed['gasPrice']),
        #     gasUsed=parsed['gasUsed'],
        #     processed=True,
        #     confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
        #     timestamp=parsed['timestamp'],
        #     eventName=parsed['eventName'],
        #     from_=parsed['from_'],
        #     to_=parsed['to_'],
        #     value_=parsed['value_'],
        #     createdAt=parsed["createdAt"],
        #     lastUpdatedAt=datetime.datetime.now(),
        #     upsert=True
        # )

        return parsed
