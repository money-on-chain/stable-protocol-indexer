import datetime
import time
from web3 import Web3
from web3.exceptions import TransactionNotFound
from hexbytes import HexBytes
from collections import OrderedDict

from indexer.logger import log


LOCAL_TIMEZONE = datetime.datetime.now().astimezone().tzinfo


def filter_transactions(transactions, filter_addresses):
    l_transactions = list()
    d_index_transactions = dict()
    for transaction in transactions:
        tx_to = None
        tx_from = None
        if 'to' in transaction:
            if transaction['to']:
                tx_to = str.lower(transaction['to'])

        if 'from' in transaction:
            if transaction['from']:
                tx_from = str.lower(transaction['from'])

        if tx_to in filter_addresses or tx_from in filter_addresses:
            l_transactions.append(transaction)
            d_index_transactions[
                Web3.to_hex(transaction['hash'])] = transaction

    return l_transactions, d_index_transactions


def transactions_receipt(
        connection_helper,
        transactions,
        index_status=0,
        index_min_confirmation=1):
    """ Get transaction receipt by default only confirmed and 1 block confirmation"""

    web3 = connection_helper.connection_manager.web3

    l_tx_receipt = list()
    for tx in transactions:
        try:
            tx_receipt = web3.eth.get_transaction_receipt(Web3.to_hex(tx['hash']))
        except TransactionNotFound:
            log.error("No transaction receipt for hash: [{0}]".format(
                Web3.to_hex(tx['hash'])))
            tx_receipt = None
        if tx_receipt:
            if tx_receipt['status'] >= index_status and \
                    connection_helper.connection_manager.block_number \
                    - tx_receipt['blockNumber'] >= index_min_confirmation:
                l_tx_receipt.append({**tx, **tx_receipt})

    return l_tx_receipt


def block_filtered_transactions(
        connection_helper,
        block_number: int,
        full_transactions=True,
        filter_tx=None,
        index_min_confirmation=1):
    """ Get only interested transactions"""

    web3 = connection_helper.connection_manager.web3

    # get block and full transactions
    f_block = web3.eth.get_block(block_number, full_transactions=full_transactions)

    # Filter to only tx
    fil_transactions, d_fil_transactions = filter_transactions(f_block['transactions'], filter_tx)

    # get transactions receipts
    fil_transactions_receipts = transactions_receipt(
        connection_helper,
        fil_transactions,
        index_min_confirmation=index_min_confirmation)

    txs = dict()
    txs['txs'] = fil_transactions
    txs['d_txs'] = d_fil_transactions
    txs['receipts'] = fil_transactions_receipts
    txs['block_number'] = f_block['number']
    txs['block_ts'] = datetime.datetime.fromtimestamp(f_block['timestamp'], LOCAL_TIMEZONE)

    return txs


def index_raw_tx(
        connection_helper,
        block_number,
        last_block_number,
        filter_tx=None,
        debug_mode=True,
        processed=0,
        confirm_mode=False):
    """ Receipts from blockchain to Database"""

    collection_raw_transactions = connection_helper.mongo_collection('raw_transactions')

    fil_txs = block_filtered_transactions(connection_helper, block_number, filter_tx=filter_tx)
    receipts = fil_txs["receipts"]

    if receipts:
        for tx_rcp in receipts:
            if confirm_mode:
                raw_tx = collection_raw_transactions.find_one({
                    "hash": str(HexBytes(tx_rcp['hash']).hex()),
                    "blockNumber": tx_rcp['blockNumber']
                })
                if raw_tx:
                    # In confirm mode if exist skip it, not write again
                    continue

            d_tx = OrderedDict()
            d_tx["hash"] = str(HexBytes(tx_rcp['hash']).hex())
            d_tx["blockNumber"] = tx_rcp['blockNumber']
            d_tx["blockHash"] = str(HexBytes(tx_rcp['blockHash']).hex())
            d_tx["from"] = tx_rcp['from']
            d_tx["to"] = tx_rcp['to']
            d_tx["value"] = str(tx_rcp['value'])
            d_tx["gas"] = tx_rcp['gas']
            d_tx["gasPrice"] = str(tx_rcp['gasPrice'])
            d_tx["gasUsed"] = tx_rcp['gasUsed']
            d_tx["input"] = str(tx_rcp['input'])
            d_tx["receipt"] = True
            d_tx["processed"] = False
            #d_tx["gas_used"] = tx_rcp['gasUsed']
            d_tx["confirmations"] = connection_helper.connection_manager.block_number - tx_rcp['blockNumber']
            d_tx["timestamp"] = fil_txs["block_ts"]
            d_tx["logs"] = tx_rcp['logs']
            d_tx["status"] = tx_rcp['status']
            d_tx["createdAt"] = fil_txs["block_ts"]
            d_tx["lastUpdatedAt"] = datetime.datetime.now()

            post_id = collection_raw_transactions.find_one_and_update(
                {"hash": str(HexBytes(tx_rcp['hash']).hex()), "blockNumber": tx_rcp['blockNumber']},
                {"$set": d_tx},
                upsert=True)

            processed += 1

    d_info = dict()
    d_info["processed"] = processed
    d_info["block_number"] = fil_txs["block_number"]
    d_info["block_ts"] = fil_txs["block_ts"]

    return d_info


def scan_raw_txs(options, connection_helper, filter_contracts, task=None):

    start_time = time.time()

    # get the block recession is a margin of problems to not get the immediate new instead
    config_blocks_recession = options['scan_raw_transactions']['blocks_recession']
    debug_mode = options['debug']

    collection_moc_indexer = connection_helper.mongo_collection('moc_indexer')
    protocol_index = collection_moc_indexer.find_one(sort=[("updatedAt", -1)])

    last_block_indexed = 0
    if protocol_index:
        if 'last_raw_tx_block' in protocol_index:
            last_block_indexed = protocol_index['last_raw_tx_block']

    # get last block from node compare 1 blocks older than new
    last_block = connection_helper.connection_manager.block_number - config_blocks_recession

    from_block = options['scan_raw_transactions']['from_block']

    if last_block_indexed > 0:
        from_block = last_block_indexed + 1

    to_block = last_block
    if options['scan_raw_transactions']['to_block'] > 0:
        to_block = options['scan_raw_transactions']['to_block']

    # only process a max of numer of blocks in one iteration of this task
    to_block = min(to_block, from_block + options['scan_raw_transactions']['max_blocks_to_process'])

    if from_block > to_block:
        if debug_mode:
            log.info("[1. Scan Raw Txs] Its not the time to run indexer no new blocks available!")
        return

    # start with from block
    current_block = from_block

    if debug_mode:
        log.info("[1. Scan Raw Txs] Starting to Scan Transactions [{0} / {1}]".format(from_block, to_block))

    processed = 0
    while current_block <= to_block:

        # index our contracts only
        block_processed = index_raw_tx(
            connection_helper,
            current_block,
            last_block,
            filter_tx=filter_contracts,
            debug_mode=debug_mode,
            processed=processed)

        if debug_mode:
            log.info("[1. Scan Raw Txs] OK [{0}] / [{1}]".format(current_block, to_block))

        collection_moc_indexer.update_one({},
                                          {'$set': {'last_raw_tx_block': current_block,
                                                    'updatedAt': datetime.datetime.now(),
                                                    'last_block_number': block_processed['block_number'],
                                                    'last_block_ts': block_processed['block_ts']}},
                                          upsert=True)
        processed = block_processed["processed"]

        # Go to next block
        current_block += 1

    duration = time.time() - start_time
    log.info("[1. Scan Raw Txs] Done! Processed: [{0}] in [{1} seconds]".format(processed, duration))


def scan_raw_txs_confirming(options, connection_helper, filter_contracts, task=None):

    start_time = time.time()

    config_blocks_recession = options['scan_raw_transactions_confirming']['blocks_recession']
    debug_mode = options['debug']
    confirm_blocks = options['scan_raw_transactions_confirming']['confirm_blocks']

    collection_moc_indexer = connection_helper.mongo_collection('moc_indexer')
    protocol_index = collection_moc_indexer.find_one(sort=[("updatedAt", -1)])

    last_block_indexed = 0
    if protocol_index:
        if 'last_raw_tx_confirming_block' in protocol_index:
            last_block_indexed = protocol_index['last_raw_tx_confirming_block']

    # get last block from node compare 1 blocks older than new
    last_block = connection_helper.connection_manager.block_number - config_blocks_recession

    from_block = options['scan_raw_transactions_confirming']['from_block']

    if last_block_indexed > 0:
        from_block = last_block_indexed + 1

    to_block = last_block - confirm_blocks
    if options['scan_raw_transactions_confirming']['to_block'] > 0:
        to_block = options['scan_raw_transactions_confirming']['to_block']

    # only process a max of numer of blocks in one iteration of this task
    to_block = min(to_block, from_block + options['scan_raw_transactions_confirming']['max_blocks_to_process'])

    if from_block > to_block:
        if debug_mode:
            log.info("[5. Scan Raw Txs Confirming] Its not the time to run indexer no new blocks available!")
        return

    # start with from block
    current_block = from_block

    if debug_mode:
        log.info("[5. Scan Raw Txs Confirming] Starting to Scan Transactions [{0} / {1}]".format(from_block, to_block))

    processed = 0
    while current_block <= to_block:

        # index our contracts only
        block_processed = index_raw_tx(
            connection_helper,
            current_block,
            last_block,
            filter_tx=filter_contracts,
            debug_mode=debug_mode,
            processed=processed,
            confirm_mode=True)

        if debug_mode:
            log.info("[5. Scan Raw Txs Confirming] OK [{0}] / [{1}]".format(current_block, to_block))

        collection_moc_indexer.update_one({},
                                          {'$set': {'last_raw_tx_confirming_block': current_block}},
                                          upsert=True)
        processed = block_processed["processed"]

        # Go to next block
        current_block += 1

    duration = time.time() - start_time

    if processed > 0:
        log.warning("[5. Scan Raw Txs Confirming] Reindexing [{0}] in [{1} seconds]".format(processed, duration))
    else:
        log.info("[5. Scan Raw Txs Confirming] Done! Processed: [{0}] in [{1} seconds]".format(processed, duration))


class ScanRawTxs:

    def __init__(self, options, connection_helper, filter_contracts):
        self.options = options
        self.connection_helper = connection_helper
        self.filter_contracts = filter_contracts

    def on_init(self):
        pass

    def on_task(self, task=None):
        scan_raw_txs(self.options, self.connection_helper, self.filter_contracts, task=task)

    def on_task_confirming(self, task=None):
        scan_raw_txs_confirming(self.options, self.connection_helper, self.filter_contracts, task=task)
