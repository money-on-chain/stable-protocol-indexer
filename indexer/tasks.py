
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
    FastBtcBridge
from .scan_raw_transactions import ScanRawTxs
from .scan_logs_transactions import ScanLogsTransactions
from .scan_transactions_status import ScanTxStatus

__VERSION__ = '4.0.0'

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

        self.filter_contracts_addresses = [v.lower() for k, v in self.contracts_addresses.items()]

    def schedule_tasks(self):

        log.info("Starting adding indexer tasks...")

        # set max workers
        self.max_workers = 1

        # # 1. Scan Raw Transactions
        # if 'scan_raw_transactions' in self.config['tasks']:
        #     log.info("Jobs add: 1. Scan Raw Transactions")
        #     interval = self.config['tasks']['scan_raw_transactions']['interval']
        #     scan_raw_txs = ScanRawTxs(self.config, self.connection_helper, self.filter_contracts_addresses)
        #     self.add_task(scan_raw_txs.on_task,
        #                   args=[],
        #                   wait=interval,
        #                   timeout=180,
        #                   task_name='1. Scan Raw Transactions')

        # 2. Scan Logs Txs
        if 'scan_logs' in self.config['tasks']:
            log.info("Jobs add: 2. Scan Logs Transactions")
            interval = self.config['tasks']['scan_logs']['interval']
            scan_events_txs = ScanLogsTransactions(
                self.config,
                self.connection_helper,
                self.contracts_loaded,
                self.contracts_addresses,
                self.filter_contracts_addresses)
            self.add_task(scan_events_txs.on_task,
                          args=[],
                          wait=interval,
                          timeout=180,
                          task_name='2. Scan Logs Transactions')

        # # 3. Scan TX Status
        # if 'scan_tx_status' in self.config['tasks']:
        #     log.info("Jobs add: 3. Scan Transactions Status")
        #     interval = self.config['tasks']['scan_tx_status']['interval']
        #     scan_tx_status = ScanTxStatus(self.config, self.connection_helper)
        #     self.add_task(scan_tx_status.on_task,
        #                   args=[],
        #                   wait=interval,
        #                   timeout=180,
        #                   task_name='3. Scan Transactions Status')

        # # 4. Scan events not processed
        # if 'scan_events_not_processed' in self.config['tasks']:
        #     log.info("Jobs add: 4. Scan events not processed")
        #     interval = self.config['tasks']['scan_events_not_processed']['interval']
        #     scan_events_not_processed = ScanEventsTransactions(
        #         self.config,
        #         self.connection_helper,
        #         self.contracts_decode_events,
        #         self.contracts_addresses,
        #         self.filter_contracts_addresses)
        #     self.add_task(scan_events_not_processed.on_task_not_processed,
        #                   args=[],
        #                   wait=interval,
        #                   timeout=180,
        #                   task_name='4. Scan events not processed')

        # Set max tasks
        self.max_tasks = len(self.tasks)
