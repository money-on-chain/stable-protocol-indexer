from pymongo import ASCENDING, DESCENDING

from .base.main import ConnectionHelperMongo
from .base.token import ERC20Token
from .tasks_manager import TasksManager
from .logger import log
from .contracts import Multicall2, \
    MoC, \
    MoCConnector, \
    MoCState, \
    MoCInrate, \
    MoCSettlement, \
    MoCExchange, \
    MoCRRC20, \
    MoCConnectorRRC20, \
    MoCStateRRC20, \
    MoCInrateRRC20, \
    MoCSettlementRRC20, \
    MoCExchangeRRC20, \
    FastBtcBridge, \
    MocLendingManager
from .scan_raw_transactions import ScanRawTxs
from .scan_logs_transactions import ScanLogsTransactions
from .scan_transactions_status import ScanTxStatus

__VERSION__ = '4.0.4'

log.info("Starting Protocol Indexer version {0}".format(__VERSION__))


class StableIndexerTasks(TasksManager):

    def __init__(self, config):

        TasksManager.__init__(self)

        self.config = config
        self.connection_helper = ConnectionHelperMongo(config)

        self.contracts_loaded = dict()
        self.contracts_addresses = dict()
        self.filter_contracts_addresses = dict()

        # load contracts
        self.load_contracts()

        # Add tasks
        self.schedule_tasks()

    def load_contracts(self):
        """ Get contract address to use later """

        log.info("Loading contracts...")

        self.contracts_loaded["Multicall2"] = Multicall2(
            self.connection_helper.connection_manager,
            contract_address=self.config['addresses']['Multicall2'])
        #self.contracts_addresses['Multicall2'] = self.contracts_loaded["Multicall2"].address().lower()

        if self.config['app_mode'] == 'MoC':
            self.contracts_loaded["MoC"] = MoC(
                self.connection_helper.connection_manager,
                contract_address=self.config['addresses']['MoC'])
            self.contracts_addresses['MoC'] = self.contracts_loaded["MoC"].address().lower()
        else:
            self.contracts_loaded["MoC"] = MoCRRC20(
                self.connection_helper.connection_manager,
                contract_address=self.config['addresses']['MoC'])
            self.contracts_addresses['MoC'] = self.contracts_loaded["MoC"].address().lower()

        self.contracts_addresses['MoCConnector'] = self.contracts_loaded["MoC"].sc.functions.connector().call()

        if self.config['app_mode'] == 'MoC':
            self.contracts_loaded["MoCConnector"] = MoCConnector(
                self.connection_helper.connection_manager,
                contract_address=self.contracts_addresses['MoCConnector'])
            self.contracts_addresses['MoCConnector'] = self.contracts_loaded["MoCConnector"].address().lower()
        else:
            self.contracts_loaded["MoCConnector"] = MoCConnectorRRC20(
                self.connection_helper.connection_manager,
                contract_address=self.contracts_addresses['MoCConnector'])
            self.contracts_addresses['MoCConnector'] = self.contracts_loaded["MoCConnector"].address().lower()

        # get address fom moc connector
        self.contracts_addresses['MoCState'] = self.contracts_loaded["MoCConnector"].sc.functions.mocState().call()
        self.contracts_addresses['MoCSettlement'] = self.contracts_loaded["MoCConnector"].sc.functions.mocSettlement().call()
        self.contracts_addresses['MoCExchange'] = self.contracts_loaded["MoCConnector"].sc.functions.mocExchange().call()
        self.contracts_addresses['MoCInrate'] = self.contracts_loaded["MoCConnector"].sc.functions.mocInrate().call()

        if self.config['app_mode'] == 'MoC':
            self.contracts_addresses['TP'] = self.contracts_loaded["MoCConnector"].sc.functions.docToken().call()
            self.contracts_addresses['TC'] = self.contracts_loaded["MoCConnector"].sc.functions.bproToken().call()
            self.contracts_addresses['MoCBProxManager'] = self.contracts_loaded["MoCConnector"].sc.functions.bproxManager().call()
        else:
            self.contracts_addresses['TP'] = self.contracts_loaded["MoCConnector"].sc.functions.stableToken().call()
            self.contracts_addresses['TC'] = self.contracts_loaded["MoCConnector"].sc.functions.riskProToken().call()
            self.contracts_addresses['MoCBProxManager'] = self.contracts_loaded["MoCConnector"].sc.functions.riskProxManager().call()
            self.contracts_addresses['ReserveToken'] = self.contracts_loaded["MoCConnector"].sc.functions.reserveToken().call()

        if self.config['app_mode'] == 'MoC':
            # MoCState
            self.contracts_loaded["MoCState"] = MoCState(
                self.connection_helper.connection_manager,
                contract_address=self.contracts_addresses['MoCState'])
            # # MoCInrate
            # self.contracts_loaded["MoCInrate"] = MoCInrate(
            #     self.connection_helper.connection_manager,
            #     contract_address=self.contracts_addresses['MoCInrate'])
            # # MoCSettlement
            # self.contracts_loaded["MoCSettlement"] = MoCSettlement(
            #     self.connection_helper.connection_manager,
            #     contract_address=self.contracts_addresses['MoCSettlement'])
            # MoCExchange
            self.contracts_loaded["MoCExchange"] = MoCExchange(
                self.connection_helper.connection_manager,
                contract_address=self.contracts_addresses['MoCExchange'])
        else:
            # RRC20
            # MoCState
            self.contracts_loaded["MoCState"] = MoCStateRRC20(
                self.connection_helper.connection_manager,
                contract_address=self.contracts_addresses['MoCState'])
            # # MoCInrate
            # self.contracts_loaded["MoCInrate"] = MoCInrateRRC20(
            #     self.connection_helper.connection_manager,
            #     contract_address=self.contracts_addresses['MoCInrate'])
            # # MoCSettlement
            # self.contracts_loaded["MoCSettlement"] = MoCSettlementRRC20(
            #     self.connection_helper.connection_manager,
            #     contract_address=self.contracts_addresses['MoCSettlement'])
            # MoCExchange
            self.contracts_loaded["MoCExchange"] = MoCExchangeRRC20(
                self.connection_helper.connection_manager,
                contract_address=self.contracts_addresses['MoCExchange'])
            # RESERVE TOKEN
            self.contracts_loaded["ReserveToken"] = ERC20Token(
                self.connection_helper.connection_manager,
                contract_address=self.contracts_addresses['ReserveToken'])

        # Getting MoC token (aka Govern Token)
        self.contracts_addresses['TG'] = self.contracts_loaded["MoCState"].sc.functions.getMoCToken().call()

        # Token TC
        self.contracts_loaded["TC"] = ERC20Token(
            self.connection_helper.connection_manager,
            contract_address=self.contracts_addresses['TC'])
        # Token TP
        self.contracts_loaded["TP"] = ERC20Token(
            self.connection_helper.connection_manager,
            contract_address=self.contracts_addresses['TP'])
        # Token TG
        self.contracts_loaded["TG"] = ERC20Token(
            self.connection_helper.connection_manager,
            contract_address=self.contracts_addresses['TG'])
        # FastBTCBridge
        self.contracts_loaded["FastBtcBridge"] = FastBtcBridge(
            self.connection_helper.connection_manager,
            contract_address=self.config['addresses']['FastBtcBridge'])
        self.contracts_addresses['FastBtcBridge'] = self.config['addresses']['FastBtcBridge']

        # MocLendingManager (optional — only loaded when address is provided in config)
        if self.config['addresses'].get('MocLendingManager'):
            lending_address = self.config['addresses']['MocLendingManager']
            log.info("MocLendingManager using address: {0}".format(lending_address.lower()))
            self.contracts_loaded["MocLendingManager"] = MocLendingManager(
                self.connection_helper.connection_manager,
                contract_address=lending_address)
            self.contracts_addresses['MocLendingManager'] = self.contracts_loaded[
                "MocLendingManager"].address().lower()

        self.filter_contracts_addresses = [v.lower() for k, v in self.contracts_addresses.items()]

    def create_mongo_index(self):

        # Lending user operations collection
        self.connection_helper.create_index('lending_user_operations', [('id_event', ASCENDING)], unique=True)
        self.connection_helper.create_index(
            'lending_user_operations', [('user', ASCENDING), ('blockNumber', DESCENDING)], unique=False)
        self.connection_helper.create_index('lending_user_operations', [('blockNumber', DESCENDING)], unique=False)
        self.connection_helper.create_index('lending_user_operations', [('operId', ASCENDING)], unique=False)

        # Lending event collections: id_event / hash back the indexer's upserts,
        # blockNumber (alone and paired with each API filter field) backs the
        # API listings sorted by blockNumber desc.
        lending_filter_fields = {
            'event_Lending_Deposit': ['user', 'recipient'],
            'event_Lending_Withdraw': ['user', 'recipient'],
            'event_Lending_AddACtoVault': ['user', 'recipient'],
            'event_Lending_RemoveACfromVault': ['user', 'recipient'],
            'event_Lending_Borrow': ['user', 'recipient'],
            'event_Lending_Repay': ['user', 'recipient'],
            'event_Lending_RepayWithAC': ['user'],
            'event_Lending_Liquidate': ['user', 'liquidator'],
            'event_Lending_TPInjection': [],
            'event_Lending_OperationQueued': ['user', 'recipient'],
            'event_Lending_OperationError': ['operId'],
            'event_Lending_OperationExecuted': ['operId'],
        }
        for collection_name, filter_fields in lending_filter_fields.items():
            self.connection_helper.create_index(collection_name, [('id_event', ASCENDING)], unique=False)
            self.connection_helper.create_index(collection_name, [('hash', ASCENDING)], unique=False)
            self.connection_helper.create_index(collection_name, [('blockNumber', DESCENDING)], unique=False)
            for field in filter_fields:
                self.connection_helper.create_index(
                    collection_name, [(field, ASCENDING), ('blockNumber', DESCENDING)], unique=False)

    def schedule_tasks(self):

        log.info("Starting adding indexer tasks...")

        # set max workers
        self.max_workers = 1

        log.info("Creating mongo collection index...")
        self.create_mongo_index()

        # 1. Scan Raw Transactions
        if 'scan_raw_transactions' in self.config['tasks']:
            log.info("Jobs add: 1. Scan Raw Transactions")
            interval = self.config['tasks']['scan_raw_transactions']['interval']
            scan_raw_txs = ScanRawTxs(self.config, self.connection_helper, self.filter_contracts_addresses)
            self.add_task(scan_raw_txs.on_task,
                          args=[],
                          wait=interval,
                          timeout=180,
                          task_name='1. Scan Raw Transactions')

        # 2. Scan Logs Txs
        if 'scan_logs' in self.config['tasks']:
            log.info("Jobs add: 2. Scan Logs Transactions")
            interval = self.config['tasks']['scan_logs']['interval']
            scan_logs_txs = ScanLogsTransactions(
                self.config,
                self.connection_helper,
                self.contracts_loaded,
                self.contracts_addresses,
                self.filter_contracts_addresses)
            self.add_task(scan_logs_txs.on_task,
                          args=[],
                          wait=interval,
                          timeout=180,
                          task_name='2. Scan Logs Transactions')

        # 3. Scan TX Status
        if 'scan_tx_status' in self.config['tasks']:
            log.info("Jobs add: 3. Scan Transactions Status")
            interval = self.config['tasks']['scan_tx_status']['interval']
            scan_tx_status = ScanTxStatus(self.config, self.connection_helper)
            self.add_task(scan_tx_status.on_task,
                          args=[],
                          wait=interval,
                          timeout=180,
                          task_name='3. Scan Transactions Status')

        # 4. Scan events not processed
        if 'scan_logs_not_processed' in self.config['tasks']:
            log.info("Jobs add: 4. Scan logs not processed")
            interval = self.config['tasks']['scan_logs_not_processed']['interval']
            scan_logs_not_processed = ScanLogsTransactions(
                self.config,
                self.connection_helper,
                self.contracts_loaded,
                self.contracts_addresses,
                self.filter_contracts_addresses)
            self.add_task(scan_logs_not_processed.on_task_not_processed,
                          args=[],
                          wait=interval,
                          timeout=180,
                          task_name='4. Scan Logs not processed')

        # 5. Scan Raw Transactions Confirming
        if 'scan_raw_transactions_confirming' in self.config['tasks']:
            log.info("Jobs add: 5. Scan Raw Transactions Confirming")
            interval = self.config['tasks']['scan_raw_transactions_confirming']['interval']
            scan_raw_txs_confirming = ScanRawTxs(self.config, self.connection_helper, self.filter_contracts_addresses)
            self.add_task(scan_raw_txs_confirming.on_task_confirming,
                          args=[],
                          wait=interval,
                          timeout=180,
                          task_name='5. Scan Raw Transactions Confirming')

        # Set max tasks
        self.max_tasks = len(self.tasks)
