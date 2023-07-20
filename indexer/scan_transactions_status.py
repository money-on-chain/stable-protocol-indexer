import time
import datetime
from web3 import Web3
from web3.exceptions import TransactionNotFound

from .logger import log


class ScanTxStatus:

    def __init__(self, options, connection_helper):
        self.options = options
        self.connection_helper = connection_helper
        self.confirm_blocks = self.options['scan_tx_status']['confirm_blocks']

        # update block info
        self.last_block = connection_helper.connection_manager.block_number
        self.block_ts = connection_helper.connection_manager.block_timestamp(self.last_block)

        self.block_info = dict(
            last_block=self.last_block,
            block_ts=self.block_ts,
            confirm_blocks=self.confirm_blocks
        )

    def update_info_last_block(self):

        collection_moc_indexer = self.connection_helper.mongo_collection('moc_indexer')
        indexer = collection_moc_indexer.find_one(sort=[("updatedAt", -1)])
        if indexer:
            if 'last_block_number' in indexer:
                self.last_block = indexer['last_block_number']
                self.block_ts = indexer['last_block_ts']
                self.block_info = dict(
                    last_block=self.last_block,
                    block_ts=self.block_ts,
                    confirm_blocks=self.confirm_blocks
                )

    def is_confirmed_block(self, block_height, block_height_last, block_height_last_ts):

        confirm_blocks = self.options['scan_tx_status']['confirm_blocks']
        if block_height_last - block_height > confirm_blocks:
            status = 'confirmed'
            confirmation_time = block_height_last_ts
            confirming_percent = 100
        else:
            status = 'confirming'
            confirmation_time = None
            confirming_percent = (block_height_last - block_height) * 10

        return status, confirmation_time, confirming_percent

    def scan_transaction_status_block(self, block_height, block_height_ts):

        web3 = self.connection_helper.connection_manager.web3
        collection_tx = self.connection_helper.mongo_collection('Transaction')
        seconds_not_in_chain_error = self.options['scan_tx_status']['seconds_not_in_chain_error']

        # Get confirming tx and check for confirming, confirmed or failed
        tx_pendings = collection_tx.find({'status': 'confirming'})
        for tx_pending in tx_pendings:

            try:
                tx_receipt = web3.eth.get_transaction_receipt(tx_pending['transactionHash'])
            except TransactionNotFound:
                tx_receipt = None

            if tx_receipt:
                d_tx_up = dict()
                if tx_receipt['status'] == 1:
                    d_tx_up['status'], d_tx_up['confirmationTime'], d_tx_up['confirmingPercent'] = \
                        self.is_confirmed_block(
                            tx_receipt['blockNumber'],
                            block_height,
                            block_height_ts)
                    # if d_tx_up['status'] == 'confirming':
                    #    # is already on confirming status
                    #    # not write to db
                    #    continue
                elif tx_receipt.status == 0:
                    d_tx_up['status'] = 'failed'
                    d_tx_up['confirmationTime'] = block_height_ts
                else:
                    continue

                collection_tx.find_one_and_update(
                    {"_id": tx_pending["_id"]},
                    {"$set": d_tx_up})

                log.info("[5. Scan Moc Status] Setting TX STATUS: {0} hash: {1}".format(
                    d_tx_up['status'],
                    tx_pending['transactionHash']))
            else:
                # no receipt from tx
                # here problem with eternal confirming
                created_at = tx_pending['createdAt']
                if created_at:
                    dte = created_at + datetime.timedelta(seconds=seconds_not_in_chain_error)
                    if dte < block_height_ts:
                        d_tx_up = dict()
                        d_tx_up['status'] = 'failed'
                        d_tx_up['errorCode'] = 'staleTransaction'
                        d_tx_up['confirmationTime'] = block_height_ts

                        collection_tx.find_one_and_update(
                            {"_id": tx_pending["_id"]},
                            {"$set": d_tx_up})

                        log.info("[5. Scan Moc Status] Setting TX STATUS: {0} hash: {1}".format(
                            d_tx_up['status'],
                            tx_pending['transactionHash']))

    def scan_transactions_status(self, task=None):

        # update block information
        self.update_info_last_block()

        # get last block from node
        last_block = self.last_block  # network_manager.block_number

        # get block time from node
        last_block_ts = self.block_ts  # network_manager.block_timestamp(last_block)

        collection_moc_indexer = self.connection_helper.mongo_collection('moc_indexer')
        moc_index = collection_moc_indexer.find_one(sort=[("updatedAt", -1)])
        last_moc_status_block = 0
        if moc_index:
            if 'last_moc_status_block' in moc_index:
                last_moc_status_block = int(moc_index['last_moc_status_block'])

        if last_block <= last_moc_status_block:
            log.info("[5. Scan Moc Status] Its not time to run Scan Transactions status")
            return

        log.info("[5. Scan Moc Status] Starting to Scan Transactions status last block: {0} ".format(last_block))

        start_time = time.time()

        collection_moc_indexer.update_one({},
                                          {'$set': {'last_moc_status_block': last_block,
                                                    'updatedAt': datetime.datetime.now()}},
                                          upsert=True)

        self.scan_transaction_status_block(last_block, last_block_ts)

        duration = time.time() - start_time
        log.info("[5. Scan Moc Status] Done!  [{0}] [{1} seconds.]".format(last_block, duration))

    def on_task(self, task=None):
        self.scan_transactions_status(task=task)

