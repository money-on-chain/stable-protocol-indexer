from .mongo import mongo_manager
from .network import ConnectionManager


class ConnectionHelperBase(object):

    precision = 10 ** 18

    def __init__(self, config):
        self.config = config
        self.config_uri = config["uri"]
        self.connection_manager = self.connect_node()

    def connect_node(self):

        return ConnectionManager(uris=self.config_uri)


class ConnectionHelperMongo(ConnectionHelperBase):

    precision = 10 ** 18

    def __init__(self, config):
        super().__init__(config)
        self.m_client = self.connect_mongo_client()

    def connect_mongo_client(self):

        # connect to mongo db
        mongo_manager.set_connection(uri=self.config['mongo']['uri'], db=self.config['mongo']['db'])
        m_client = mongo_manager.connect()

        return m_client

    def mongo_collection(self, collection_name):

        return mongo_manager.get_collection(self.m_client, collection_name)
