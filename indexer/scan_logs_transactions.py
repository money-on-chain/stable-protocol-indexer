import time
import datetime
from collections import OrderedDict

from .logger import log
from .events import EventMoCExchangeRiskProMint, \
    EventMoCExchangeRiskProRedeem,\
    EventTokenTransfer, \
    EventMoCExchangeRiskProxMint, \
    EventMoCExchangeRiskProxRedeem, \
    EventMoCExchangeStableTokenMint, \
    EventMoCExchangeStableTokenRedeem, \
    EventMoCExchangeFreeStableTokenRedeem, \
    EventLendingDeposit, \
    EventLendingWithdraw, \
    EventLendingAddACtoVault, \
    EventLendingRemoveACfromVault, \
    EventLendingBorrow, \
    EventLendingRepay, \
    EventLendingRepayWithAC, \
    EventLendingLiquidate, \
    EventLendingTPInjection, \
    EventLendingOperationQueued, \
    EventLendingOperationError, \
    EventLendingOperationExecuted, \
    EventOMOCIncentiveV2ClaimOK, \
    EventOMOCVestingFactoryVestingCreated, \
    EventOMOCDelayMachinePaymentCancel, \
    EventOMOCDelayMachinePaymentDeposit, \
    EventOMOCDelayMachinePaymentWithdraw, \
    EventOMOCSupportersAddStake, \
    EventOMOCSupportersCancelEarnings, \
    EventOMOCSupportersPayEarnings, \
    EventOMOCSupportersWithdraw, \
    EventOMOCSupportersWithdrawStake, \
    EventOMOCVotingMachinePreVoteEvent, \
    EventOMOCVotingMachineVoteEvent, \
    EventOMOCVotingMachinePreVoteStepEvent, \
    EventOMOCVotingMachineVoteStepEvent, \
    EventOMOCVotingMachineAcceptedStepEvent, \
    EventOMOCVotingMachineUnregisterEvent, \
    EventOMOCOracleManagerOracleRegistered, \
    EventOMOCOracleManagerOracleStakeAdded, \
    EventOMOCOracleManagerOracleSubscribed, \
    EventOMOCOracleManagerOracleUnsubscribed, \
    EventOMOCOracleManagerOracleRemoved, \
    EventOMOCCoinPairPricePricePublished, \
    EventOMOCCoinPairPriceEmergencyPricePublished, \
    EventOMOCCoinPairPriceForcedPriceQueryModeSet, \
    EventOMOCCoinPairPriceOracleRewardTransfer, \
    EventOMOCCoinPairPriceNewRound, \
    EventOMOCCoinPairPriceOracleAutoUnsubscribed, \
    EventOMOCTasksRunnerTaskExecuted, \
    EventOMOCTaskTriggerOrderTriggerOrdersReverted

from .base.decoder import LogDecoder, UnknownEvent


class ScanLogsTransactions:

    def __init__(self,
                 options,
                 connection_helper,
                 contracts_loaded,
                 contracts_addresses,
                 filter_contracts_addresses):
        self.options = options
        self.connection_helper = connection_helper
        self.contracts_loaded = contracts_loaded
        self.contracts_addresses = contracts_addresses
        self.filter_contracts_addresses = filter_contracts_addresses
        self.confirm_blocks = self.options['scan_logs']['confirm_blocks']

        # init log decoder
        self.contracts_log_decoder = self.init_log_decoder()

        # update block info
        self.last_block = connection_helper.connection_manager.block_number
        self.block_ts = connection_helper.connection_manager.block_timestamp(self.last_block)
        self.block_info = dict(
            last_block=self.last_block,
            block_ts=self.block_ts,
            confirm_blocks=self.confirm_blocks
        )

        self.map_events_contracts = self.map_events()

    def init_log_decoder(self):

        contracts_log_decoder = dict()
        # contracts_log_decoder[self.contracts_addresses['MoCState'].lower()] = LogDecoder(
        #     self.contracts_loaded['MoCState'].sc
        # )
        # contracts_log_decoder[self.contracts_addresses['MoCInrate'].lower()] = LogDecoder(
        #     self.contracts_loaded['MoCInrate'].sc
        # )
        # contracts_log_decoder[self.contracts_addresses['MoCSettlement'].lower()] = LogDecoder(
        #     self.contracts_loaded['MoCSettlement'].sc
        # )
        contracts_log_decoder[self.contracts_addresses['MoCExchange'].lower()] = LogDecoder(
            self.contracts_loaded['MoCExchange'].sc
        )

        if self.options['app_mode'] != "MoC":
            contracts_log_decoder[self.contracts_addresses['ReserveToken'].lower()] = LogDecoder(
                self.contracts_loaded['ReserveToken'].sc
            )
        contracts_log_decoder[self.contracts_addresses['TC'].lower()] = LogDecoder(
            self.contracts_loaded['TC'].sc
        )
        contracts_log_decoder[self.contracts_addresses['TP'].lower()] = LogDecoder(
            self.contracts_loaded['TP'].sc
        )
        contracts_log_decoder[self.contracts_addresses['TG'].lower()] = LogDecoder(
            self.contracts_loaded['TG'].sc
        )

        # OMOC (only when governance / staking contracts are loaded)
        if 'DelayMachine' in self.contracts_addresses:

            if 'IncentiveV2' in self.contracts_addresses:
                contracts_log_decoder[self.contracts_addresses['IncentiveV2'].lower()] = LogDecoder(
                    self.contracts_loaded['IncentiveV2'].sc
                )

            contracts_log_decoder[self.contracts_addresses['VestingFactory'].lower()] = LogDecoder(
                self.contracts_loaded['VestingFactory'].sc
            )

            contracts_log_decoder[self.contracts_addresses['DelayMachine'].lower()] = LogDecoder(
                self.contracts_loaded['DelayMachine'].sc
            )

            contracts_log_decoder[self.contracts_addresses['Supporters'].lower()] = LogDecoder(
                self.contracts_loaded['Supporters'].sc
            )

            contracts_log_decoder[self.contracts_addresses['VotingMachine'].lower()] = LogDecoder(
                self.contracts_loaded['VotingMachine'].sc
            )

        # OMOC decentralized oracles
        if 'OracleManager' in self.contracts_addresses:

            contracts_log_decoder[self.contracts_addresses['OracleManager'].lower()] = LogDecoder(
                self.contracts_loaded['OracleManager'].sc
            )

            for cp_index, cp_address in enumerate(self.contracts_addresses['CoinPairPrice']):
                contracts_log_decoder[cp_address.lower()] = LogDecoder(
                    self.contracts_loaded['CoinPairPrice'][cp_index].sc
                )

        # TasksRunner / TaskTriggerOrder: registered last and merged, because the
        # OMOC deployment also lists TasksRunner in OracleManager as a coin pair,
        # so its address already carries a CoinPairPrice decoder above. Merge the
        # topic maps so both ABIs' events decode from the shared address instead of
        # the last registration winning.
        for key in ('TasksRunner', 'TaskTriggerOrder'):
            if key in self.contracts_addresses:
                addr = self.contracts_addresses[key].lower()
                extra = LogDecoder(self.contracts_loaded[key].sc)
                if addr in contracts_log_decoder:
                    contracts_log_decoder[addr].topic_map.update(extra.topic_map)
                else:
                    contracts_log_decoder[addr] = extra

        if 'MocLendingManager' in self.contracts_loaded:
            contracts_log_decoder[self.contracts_addresses['MocLendingManager'].lower()] = LogDecoder(
                self.contracts_loaded['MocLendingManager'].sc
            )

        return contracts_log_decoder

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

    def map_events(self):

        d_event = dict()
        d_event[self.contracts_addresses["MoCExchange"].lower()] = {
            "RiskProMint": EventMoCExchangeRiskProMint(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses,
                self.block_info),
            "RiskProRedeem": EventMoCExchangeRiskProRedeem(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses,
                self.block_info),
            "RiskProxMint": EventMoCExchangeRiskProxMint(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses,
                self.block_info),
            "RiskProxRedeem": EventMoCExchangeRiskProxRedeem(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses,
                self.block_info),
            "StableTokenMint": EventMoCExchangeStableTokenMint(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses,
                self.block_info),
            "StableTokenRedeem": EventMoCExchangeStableTokenRedeem(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses,
                self.block_info),
            "FreeStableTokenRedeem": EventMoCExchangeFreeStableTokenRedeem(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses,
                self.block_info),

        }

        d_event[self.contracts_addresses["TP"].lower()] = {
            "Transfer": EventTokenTransfer(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses,
                self.block_info,
                'STABLE')
        }

        d_event[self.contracts_addresses["TC"].lower()] = {
            "Transfer": EventTokenTransfer(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses,
                self.block_info,
                'RISKPRO')
        }

        d_event[self.contracts_addresses["TG"].lower()] = {
            "Transfer": EventTokenTransfer(
                self.options,
                self.connection_helper,
                self.filter_contracts_addresses,
                self.block_info,
                'TG')
        }

        if self.options['app_mode'] == "RRC20":
            d_event[self.contracts_addresses["ReserveToken"].lower()] = {
                "Transfer": EventTokenTransfer(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info,
                    'RESERVE')
            }

        # OMOC (only when governance / staking contracts are loaded)
        if 'DelayMachine' in self.contracts_addresses:

            if 'IncentiveV2' in self.contracts_addresses:
                d_event[self.contracts_addresses['IncentiveV2'].lower()] = {
                    "ClaimOK": EventOMOCIncentiveV2ClaimOK(
                        self.options,
                        self.connection_helper,
                        self.filter_contracts_addresses,
                        self.block_info)
                }

            d_event[self.contracts_addresses['VestingFactory'].lower()] = {
                "VestingCreated": EventOMOCVestingFactoryVestingCreated(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info)
            }

            d_event[self.contracts_addresses['DelayMachine'].lower()] = {
                "PaymentCancel": EventOMOCDelayMachinePaymentCancel(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "PaymentDeposit": EventOMOCDelayMachinePaymentDeposit(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "PaymentWithdraw": EventOMOCDelayMachinePaymentWithdraw(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info)
            }

            d_event[self.contracts_addresses['Supporters'].lower()] = {
                "AddStake": EventOMOCSupportersAddStake(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "CancelEarnings": EventOMOCSupportersCancelEarnings(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "PayEarnings": EventOMOCSupportersPayEarnings(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "Withdraw": EventOMOCSupportersWithdraw(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "WithdrawStake": EventOMOCSupportersWithdrawStake(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info)
            }

            d_event[self.contracts_addresses['VotingMachine'].lower()] = {
                "PreVoteEvent": EventOMOCVotingMachinePreVoteEvent(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "VoteEvent": EventOMOCVotingMachineVoteEvent(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "PreVoteStepEvent": EventOMOCVotingMachinePreVoteStepEvent(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "VoteStepEvent": EventOMOCVotingMachineVoteStepEvent(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "AcceptedStepEvent": EventOMOCVotingMachineAcceptedStepEvent(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "UnregisterEvent": EventOMOCVotingMachineUnregisterEvent(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info)
            }

        # OMOC decentralized oracles
        if 'OracleManager' in self.contracts_addresses:

            d_event[self.contracts_addresses['OracleManager'].lower()] = {
                "OracleRegistered": EventOMOCOracleManagerOracleRegistered(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "OracleStakeAdded": EventOMOCOracleManagerOracleStakeAdded(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "OracleSubscribed": EventOMOCOracleManagerOracleSubscribed(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "OracleUnsubscribed": EventOMOCOracleManagerOracleUnsubscribed(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "OracleRemoved": EventOMOCOracleManagerOracleRemoved(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info)
            }

            for cp_index, cp_address in enumerate(self.contracts_addresses['CoinPairPrice']):
                coin_pair = getattr(self.contracts_loaded['CoinPairPrice'][cp_index], 'coin_pair', None)
                d_event[cp_address.lower()] = {
                    "PricePublished": EventOMOCCoinPairPricePricePublished(
                        self.options,
                        self.connection_helper,
                        self.filter_contracts_addresses,
                        self.block_info,
                        coin_pair,
                        cp_address),
                    "EmergencyPricePublished": EventOMOCCoinPairPriceEmergencyPricePublished(
                        self.options,
                        self.connection_helper,
                        self.filter_contracts_addresses,
                        self.block_info,
                        coin_pair,
                        cp_address),
                    "ForcedPriceQueryModeSet": EventOMOCCoinPairPriceForcedPriceQueryModeSet(
                        self.options,
                        self.connection_helper,
                        self.filter_contracts_addresses,
                        self.block_info,
                        coin_pair,
                        cp_address),
                    "OracleRewardTransfer": EventOMOCCoinPairPriceOracleRewardTransfer(
                        self.options,
                        self.connection_helper,
                        self.filter_contracts_addresses,
                        self.block_info,
                        coin_pair,
                        cp_address),
                    "NewRound": EventOMOCCoinPairPriceNewRound(
                        self.options,
                        self.connection_helper,
                        self.filter_contracts_addresses,
                        self.block_info,
                        coin_pair,
                        cp_address),
                    "OracleAutoUnsubscribed": EventOMOCCoinPairPriceOracleAutoUnsubscribed(
                        self.options,
                        self.connection_helper,
                        self.filter_contracts_addresses,
                        self.block_info,
                        coin_pair,
                        cp_address)
                }

        # TasksRunner / TaskTriggerOrder: registered last and merged into whatever
        # is already mapped for the address. TasksRunner is also listed in
        # OracleManager as a coin pair, so its address already holds the
        # CoinPairPrice handlers (NewRound / OracleRewardTransfer, which it does
        # emit as a RoundManager); this just adds TaskExecuted on top.
        if 'TasksRunner' in self.contracts_addresses:
            d_event.setdefault(self.contracts_addresses['TasksRunner'].lower(), {})["TaskExecuted"] = \
                EventOMOCTasksRunnerTaskExecuted(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info)

        if 'TaskTriggerOrder' in self.contracts_addresses:
            d_event.setdefault(self.contracts_addresses['TaskTriggerOrder'].lower(), {})["TriggerOrdersReverted"] = \
                EventOMOCTaskTriggerOrderTriggerOrdersReverted(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info)

        if 'MocLendingManager' in self.contracts_loaded:
            d_event[self.contracts_addresses['MocLendingManager'].lower()] = {
                "Deposit": EventLendingDeposit(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "Withdraw": EventLendingWithdraw(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "AddACtoVault": EventLendingAddACtoVault(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "RemoveACfromVault": EventLendingRemoveACfromVault(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "Borrow": EventLendingBorrow(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "Repay": EventLendingRepay(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "RepayWithAC": EventLendingRepayWithAC(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "Liquidate": EventLendingLiquidate(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "TPInjection": EventLendingTPInjection(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "OperationQueued": EventLendingOperationQueued(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "OperationError": EventLendingOperationError(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
                "OperationExecuted": EventLendingOperationExecuted(
                    self.options,
                    self.connection_helper,
                    self.filter_contracts_addresses,
                    self.block_info),
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

            collection_tx = self.connection_helper.mongo_collection('Transaction')

            d_tx = OrderedDict()
            d_tx["hash"] = raw_tx["hash"]
            d_tx["blockNumber"] = raw_tx["blockNumber"]
            d_tx["address"] = raw_tx["from"]
            d_tx["event"] = 'ERROR'
            d_tx["gas"] = raw_tx["gas"]
            d_tx["gasPrice"] = str(raw_tx["gasPrice"])
            d_tx["confirmations"] = self.connection_helper.connection_manager.block_number - raw_tx['blockNumber']
            d_tx["timestamp"] = raw_tx["timestamp"]
            d_tx["createdAt"] = raw_tx["createdAt"]
            d_tx["lastUpdatedAt"] = datetime.datetime.now()

            post_id = collection_tx.find_one_and_update(
                {"transactionHash": d_tx['hash'],
                 "address": d_tx["address"],
                 "event": d_tx["event"]},
                {"$set": d_tx},
                upsert=True)
            d_tx['post_id'] = post_id

            log.info("Tx (REVERT) {0} From: [{1}] Tx Hash: {2}".format(
                d_tx["event"],
                d_tx["address"],
                raw_tx['hash'],))

            return

        if raw_tx["logs"]:
            for tx_log in raw_tx["logs"]:
                log_address = str.lower(tx_log['address'])
                if log_address in self.contracts_log_decoder:
                    try:
                        decoded_event = self.contracts_log_decoder[log_address].decode_log(tx_log)
                    except UnknownEvent:
                        log.error("Skipping. Not known event in ABI. Contract address: {0} Info: {1}".format(
                            log_address, tx_log))
                        continue
                    if decoded_event['name'] in self.map_events_contracts[log_address]:
                        log_index = tx_log['logIndex']
                        parsed_receipt = self.parse_tx_receipt(raw_tx, decoded_event['name'], log_index=log_index)
                        parsed_event = self.map_events_contracts[log_address][decoded_event['name']]\
                            .parse_event_and_save(
                                parsed_receipt,
                                decoded_event['data']
                            )
                    else:
                        log.warning("Event name not recognized. Event: {0}".format(decoded_event['name']))

    def scan_events_txs(self, task=None):

        start_time = time.time()

        # update block information
        self.update_info_last_block()

        collection_raw_transactions = self.connection_helper.mongo_collection('raw_transactions')
        raw_txs = collection_raw_transactions.find({"processed": False}, sort=[("blockNumber", 1)])

        count = 0
        if raw_txs:
            for raw_tx in raw_txs:
                # update block information
                self.update_info_last_block()

                count += 1
                self.process_logs(raw_tx)

                collection_raw_transactions.find_one_and_update(
                    {"hash": raw_tx["hash"], "blockNumber": raw_tx["blockNumber"]},
                    {"$set": {"processed": True}},
                    upsert=False)

        duration = time.time() - start_time
        log.info("[2. Scan Events Txs] Processed: [{0}] Done! [{1} seconds]".format(count, duration))

    def scan_events_not_processed_txs(self, task=None):
        """ Trying to reindex when there is a problem with events"""

        start_time = time.time()

        collection_transactions = self.connection_helper.mongo_collection('Transaction')

        collection_raw_transactions = self.connection_helper.mongo_collection('raw_transactions')

        collection_moc_indexer = self.connection_helper.mongo_collection('moc_indexer')
        moc_index = collection_moc_indexer.find_one(sort=[("updatedAt", -1)])

        # we need to query tx with processLogs=None and in the last 24hs
        only_last_tx = datetime.datetime.now() - datetime.timedelta(minutes=1440)
        txs = collection_transactions.find({
            "processLogs": None,
            "createdAt": {"$gte": only_last_tx}}, sort=[("createdAt", 1)])

        count = 0
        if txs:
            for tx in txs:
                # no process when no status
                if 'status' not in tx:
                    continue

                # only status confirmed and confirming
                if tx["status"] not in ["confirmed", "confirming"]:
                    continue

                raw_tx = collection_raw_transactions.find_one({"hash": tx["transactionHash"]})

                if not raw_tx:
                    log.info("[8. Scan Blocks not processed] Not exist RAW Tx for hash: {0}".format(tx["transactionHash"]))
                    continue

                dt_older_than = moc_index["last_block_ts"] - datetime.timedelta(minutes=5)
                if tx["createdAt"] >= dt_older_than:
                    continue

                log.info("[8. Scan Blocks not processed] Reindexing with hash: {0}".format(tx["transactionHash"]))

                # update block information
                self.update_info_last_block()

                count += 1
                self.process_logs(raw_tx)

        duration = time.time() - start_time
        log.info("[8. Scan Blocks not processed] Done! Processed: [{0}] [{1} seconds]".format(count, duration))

    def on_task(self, task=None):
        self.scan_events_txs(task=task)

    def on_task_not_processed(self, task=None):
        self.scan_events_not_processed_txs(task=task)

