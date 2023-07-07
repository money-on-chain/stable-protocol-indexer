import time
import datetime

from .logger import log
from .events import EventMocCABagTCMinted, \
    EventMocCABagTCRedeemed, \
    EventMocCABagTPMinted, \
    EventMocCABagTPRedeemed, \
    EventMocCABagTPSwappedForTP, \
    EventMocCABagTPSwappedForTC, \
    EventMocCABagTCSwappedForTP, \
    EventMocCABagTCandTPRedeemed, \
    EventMocCABagTCandTPMinted, \
    EventTokenTransfer
from .models import DocumentRawTransactions, DocumentIndexer, DocumentTransactions


class ScanEventsTransactions:

    def __init__(self,
                 options,
                 connection_helper,
                 contracts_decode_events,
                 contracts_addresses,
                 filter_contracts_addresses):
        self.options = options
        self.connection_helper = connection_helper
        self.contracts_decode_events = contracts_decode_events
        self.contracts_addresses = contracts_addresses
        self.filter_contracts_addresses = filter_contracts_addresses
        self.confirm_blocks = self.options['scan_raw_transactions']['confirm_blocks']
        self.map_events_contracts = self.map_events()

        # update block info
        self.last_block = connection_helper.connection_manager.block_number
        self.block_ts = connection_helper.connection_manager.block_timestamp(self.last_block)

    def update_info_last_block(self):

        indexer = DocumentIndexer.objects.order_by('-updatedAt').first()
        if indexer:
            if 'last_block_number' in indexer:
                self.last_block = indexer['last_block_number']
                self.block_ts = indexer['last_block_ts']

    def map_events(self):

        d_event = dict()
        d_event[self.contracts_addresses["MocCABag"]] = {
            "TCMinted": EventMocCABagTCMinted(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses),
            "TCRedeemed": EventMocCABagTCRedeemed(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses),
            "TPMinted": EventMocCABagTPMinted(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses),
            "TPRedeemed": EventMocCABagTPRedeemed(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses),
            "TPSwappedForTP": EventMocCABagTPSwappedForTP(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses),
            "TPSwappedForTC": EventMocCABagTPSwappedForTC(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses),
            "TCSwappedForTP": EventMocCABagTCSwappedForTP(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses),
            "TCandTPRedeemed": EventMocCABagTCandTPRedeemed(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses),
            "TCandTPMinted": EventMocCABagTCandTPMinted(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses)
        }

        d_event[self.contracts_addresses["TC"]] = {
            "Transfer": EventTokenTransfer(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses)
        }

        d_event[self.contracts_addresses["TP_0"]] = {
            "Transfer": EventTokenTransfer(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses)
        }

        d_event[self.contracts_addresses["TP_1"]] = {
            "Transfer": EventTokenTransfer(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses)
        }

        d_event[self.contracts_addresses["CA_0"]] = {
            "Transfer": EventTokenTransfer(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses)
        }

        d_event[self.contracts_addresses["CA_1"]] = {
            "Transfer": EventTokenTransfer(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses)
        }

        return d_event

    def on_init(self):
        pass

    def parse_tx_receipt(self, tx_receipt, event_name, log_index=1):

        parse_info = dict()
        parse_info['blockNumber'] = tx_receipt['blockNumber']
        parse_info['hash'] = tx_receipt['hash']
        parse_info['gas'] = tx_receipt['gas']
        parse_info['gasPrice'] = int(tx_receipt['gasPrice'])
        parse_info['gasUsed'] = tx_receipt['gasUsed']
        parse_info['timestamp'] = tx_receipt['timestamp']
        parse_info['createdAt'] = tx_receipt['createdAt']
        parse_info['eventName'] = event_name
        parse_info['logIndex'] = log_index

        return parse_info

    def process_logs(self, raw_tx):

        if raw_tx["status"] == 0:
            # reverted by EVM

            DocumentTransactions.objects(
                hash=raw_tx['hash'],
                blockNumber=raw_tx['blockNumber']
            ).update_one(
                hash=raw_tx['hash'],
                blockNumber=raw_tx['blockNumber'],
                gas=raw_tx['gas'],
                gasPrice=str(raw_tx['gasPrice']),
                gasUsed=raw_tx['gasUsed'],
                confirmations=self.connection_helper.connection_manager.block_number - raw_tx['blockNumber'],
                timestamp=raw_tx['timestamp'],
                createdAt=raw_tx["createdAt"],
                lastUpdatedAt=datetime.datetime.now(),
                upsert=True
            )
            # end
            return

        if raw_tx["logs"]:
            for tx_log in raw_tx["logs"]:
                log_address = str.lower(tx_log['address'])
                if log_address in self.contracts_decode_events:
                    decoded_event = self.contracts_decode_events[log_address].decode_log(tx_log)
                    if decoded_event['name'] in self.map_events_contracts[log_address]:
                        log_index = tx_log['logIndex']
                        parsed_receipt = self.parse_tx_receipt(raw_tx, decoded_event['name'], log_index=log_index)
                        parsed_event = self.map_events_contracts[log_address][decoded_event['name']].parse_event_and_save(
                            parsed_receipt,
                            decoded_event['event']
                        )
                        print(parsed_event)
                    else:
                        log.warning("Event name not recognized. Event: {0}".format(decoded_event['name']))

    def scan_events_txs(self, task=None):

        start_time = time.time()

        # update block information
        self.update_info_last_block()

        raw_txs = DocumentRawTransactions.objects(processed=False, not_found=False).order_by('blockNumber') #transactionIndex

        count = 0
        if raw_txs:
            for raw_tx in raw_txs:

                # update block information
                self.update_info_last_block()

                count += 1
                self.process_logs(raw_tx)

                DocumentRawTransactions.objects(
                    hash=raw_tx["hash"],
                    blockNumber=raw_tx["blockNumber"]
                ).update_one(
                    processed=True,
                    upsert=False
                )

        duration = time.time() - start_time
        log.info("[2. Scan Events Txs] Processed: [{0}] Done! [{1} seconds]".format(count, duration))

    def on_task(self, task=None):
        self.scan_events_txs(task=task)

