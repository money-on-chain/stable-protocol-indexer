
import os
import json

from web3 import Web3

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
    OMOCIRegistry, \
    OMOCDelayMachine, \
    OMOCIncentiveV2, \
    OMOCSupporters, \
    OMOCVestingFactory, \
    OMOCVotingMachine, \
    OMOCOracleManager, \
    OMOCCoinPairPrice, \
    OMOCTasksRunner, \
    OMOCTaskTriggerOrder
from .scan_raw_transactions import ScanRawTxs
from .scan_logs_transactions import ScanLogsTransactions
from .scan_transactions_status import ScanTxStatus

__VERSION__ = '4.0.5'

log.info("Starting Protocol Indexer version {0}".format(__VERSION__))


def read_omoc_json_file(filename=None):
    """ Read Json File """

    if not filename:
        filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'omoc.json')

    with open(filename) as f:
        options = json.load(f)

    return options


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

        # OMOC (Governance / Staking / Oracles). Only loaded when an IRegistry address is configured
        if self.config['addresses'].get('IRegistry'):
            self.load_omoc_contracts()

        self.filter_contracts_addresses = []
        for k, v in self.contracts_addresses.items():
            if isinstance(v, list):
                self.filter_contracts_addresses.extend([a.lower() for a in v])
            else:
                self.filter_contracts_addresses.append(v.lower())

    def load_omoc_contracts(self):
        """ Load OMOC (governance / staking) contracts and resolve their addresses """

        omoc = read_omoc_json_file()

        # IRegistry
        log.info("IRegistry using address: {0}".format(self.config['addresses']['IRegistry'].lower()))
        self.contracts_loaded["IRegistry"] = OMOCIRegistry(
            self.connection_helper.connection_manager,
            contract_address=self.config['addresses']['IRegistry'])
        self.contracts_addresses['IRegistry'] = self.contracts_loaded["IRegistry"].address().lower()

        # Getting addresses from Registry
        self.contracts_addresses['DelayMachine'] = self.contracts_loaded["IRegistry"].sc.functions.getAddress(
            omoc['RegistryConstants']['MOC_DELAY_MACHINE']).call().lower()
        self.contracts_addresses['Supporters'] = self.contracts_loaded["IRegistry"].sc.functions.getAddress(
            omoc['RegistryConstants']['SUPPORTERS_ADDR']).call().lower()
        self.contracts_addresses['VestingFactory'] = self.contracts_loaded["IRegistry"].sc.functions.getAddress(
            omoc['RegistryConstants']['MOC_VESTING_MACHINE']).call().lower()
        self.contracts_addresses['VotingMachine'] = self.contracts_loaded["IRegistry"].sc.functions.getAddress(
            omoc['RegistryConstants']['MOC_VOTING_MACHINE']).call().lower()

        # IncentiveV2 (optional)
        if self.config['addresses'].get('IncentiveV2'):
            log.info("IncentiveV2 using address: {0}".format(self.config['addresses']['IncentiveV2'].lower()))
            self.contracts_loaded["IncentiveV2"] = OMOCIncentiveV2(
                self.connection_helper.connection_manager,
                contract_address=self.config['addresses']['IncentiveV2'])
            self.contracts_addresses['IncentiveV2'] = self.contracts_loaded["IncentiveV2"].address().lower()

        # TasksRunner (optional): no registry constant published, address comes from config
        if self.config['addresses'].get('TasksRunner'):
            log.info("TasksRunner using address: {0}".format(self.config['addresses']['TasksRunner'].lower()))
            self.contracts_loaded["TasksRunner"] = OMOCTasksRunner(
                self.connection_helper.connection_manager,
                contract_address=self.config['addresses']['TasksRunner'])
            self.contracts_addresses['TasksRunner'] = self.contracts_loaded["TasksRunner"].address().lower()

        # TaskTriggerOrder (optional): a mocFlow task run by TasksRunner, address comes from config
        if self.config['addresses'].get('TaskTriggerOrder'):
            log.info("TaskTriggerOrder using address: {0}".format(self.config['addresses']['TaskTriggerOrder'].lower()))
            self.contracts_loaded["TaskTriggerOrder"] = OMOCTaskTriggerOrder(
                self.connection_helper.connection_manager,
                contract_address=self.config['addresses']['TaskTriggerOrder'])
            self.contracts_addresses['TaskTriggerOrder'] = self.contracts_loaded["TaskTriggerOrder"].address().lower()

        # DelayMachine
        log.info("DelayMachine using address: {0}".format(self.contracts_addresses['DelayMachine'].lower()))
        self.contracts_loaded["DelayMachine"] = OMOCDelayMachine(
            self.connection_helper.connection_manager,
            contract_address=self.contracts_addresses['DelayMachine'])

        # Supporters
        log.info("Supporters using address: {0}".format(self.contracts_addresses['Supporters'].lower()))
        self.contracts_loaded["Supporters"] = OMOCSupporters(
            self.connection_helper.connection_manager,
            contract_address=self.contracts_addresses['Supporters'])

        # VestingFactory
        log.info("VestingFactory using address: {0}".format(self.contracts_addresses['VestingFactory'].lower()))
        self.contracts_loaded["VestingFactory"] = OMOCVestingFactory(
            self.connection_helper.connection_manager,
            contract_address=self.contracts_addresses['VestingFactory'])

        # VotingMachine
        log.info("VotingMachine using address: {0}".format(self.contracts_addresses['VotingMachine'].lower()))
        self.contracts_loaded["VotingMachine"] = OMOCVotingMachine(
            self.connection_helper.connection_manager,
            contract_address=self.contracts_addresses['VotingMachine'])
        self.contracts_addresses['VotingMachine'] = self.contracts_loaded["VotingMachine"].address().lower()

        # Decentralized Oracles
        self.load_omoc_oracle_contracts(omoc)

    def load_omoc_oracle_contracts(self, omoc):
        """ Load the OracleManager and every registered CoinPairPrice instance """

        # OracleManager
        oracle_manager_address = self.contracts_loaded["IRegistry"].sc.functions.getAddress(
            omoc['RegistryConstants']['ORACLE_MANAGER_ADDR']).call().lower()
        log.info("OracleManager using address: {0}".format(oracle_manager_address))
        self.contracts_loaded["OracleManager"] = OMOCOracleManager(
            self.connection_helper.connection_manager,
            contract_address=oracle_manager_address)
        self.contracts_addresses['OracleManager'] = oracle_manager_address

        # CoinPairPrice: one contract per registered coin pair
        self.contracts_loaded["CoinPairPrice"] = list()
        self.contracts_addresses['CoinPairPrice'] = list()
        self.contracts_coin_pairs = list()

        zero_address = '0x0000000000000000000000000000000000000000'
        coin_pair_count = self.contracts_loaded["OracleManager"].coin_pair_count()
        for i in range(coin_pair_count):
            coin_pair = self.contracts_loaded["OracleManager"].coin_pair_at_index(i)
            cp_address = self.contracts_loaded["OracleManager"].contract_address_of(coin_pair).lower()
            if cp_address == zero_address:
                # deleted coin pair
                continue
            try:
                coin_pair_name = Web3.to_text(coin_pair).rstrip('\x00')
            except Exception:
                coin_pair_name = coin_pair.hex() if hasattr(coin_pair, 'hex') else str(coin_pair)
            log.info("CoinPairPrice ({0}) using address: {1}".format(coin_pair_name, cp_address))
            cp_contract = OMOCCoinPairPrice(
                self.connection_helper.connection_manager,
                contract_address=cp_address)
            cp_contract.coin_pair = coin_pair_name
            self.contracts_loaded["CoinPairPrice"].append(cp_contract)
            self.contracts_addresses['CoinPairPrice'].append(cp_address)
            self.contracts_coin_pairs.append(coin_pair_name)

    def schedule_tasks(self):

        log.info("Starting adding indexer tasks...")

        # set max workers
        self.max_workers = 1

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
