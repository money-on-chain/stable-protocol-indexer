import time
import datetime
from web3 import Web3
from web3.exceptions import TransactionNotFound

from .logger import log
from .models import DocumentRawTransactions, DocumentIndexer, DocumentTransactions


class ScanEventsTransactions:

    def __init__(self, options, connection_helper):
        self.options = options
        self.connection_helper = connection_helper
        self.confirm_blocks = self.options['scan_raw_transactions']['confirm_blocks']

        # update block info
        self.last_block = connection_helper.connection_manager.block_number
        self.block_ts = connection_helper.connection_manager.block_timestamp(self.last_block)

    def update_info_last_block(self):

        indexer = DocumentIndexer.objects.order_by('-updatedAt').first()
        if indexer:
            if 'last_block_number' in indexer:
                self.last_block = indexer['last_block_number']
                self.block_ts = indexer['last_block_ts']

    def scan_transactions_status(self, task=None):

        start_time = time.time()

        web3 = self.connection_helper.connection_manager.web3

        # update block information
        self.update_info_last_block()

        transactions = DocumentTransactions.objects(confirmations__lt=10).order_by('blockNumber') #transactionIndex

        count = 0
        if transactions:
            for tx in transactions:

                # update block information
                self.update_info_last_block()

                count += 1

                try:
                    tx_dict = web3.eth.get_transaction(Web3.to_hex(tx['hash']))
                except TransactionNotFound:
                    log.error("No transaction receipt for hash: [{0}]".format(
                        Web3.to_hex(tx['hash'])))
                    tx_dict = None

                if tx_dict:
                    DocumentTransactions.objects(
                        hash=tx["hash"],
                        blockNumber=tx["blockNumber"]
                    ).update_one(

                        upsert=False
                    )

        duration = time.time() - start_time
        log.info("[2. Scan Events Txs] Processed: [{0}] Done! [{1} seconds]".format(count, duration))

    def on_task(self, task=None):
        self.scan_transactions_status(task=task)

