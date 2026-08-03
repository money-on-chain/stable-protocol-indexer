import pymongo
import logging


__all__ = ["mongo_manager"]


log = logging.getLogger()


class MongoManager:

    def __init__(self, uri='mongodb://localhost:27017/', db='db_example'):

        self.uri = uri
        self.db = db

    def set_connection(self, uri='mongodb://localhost:27017/', db='db_example'):

        self.uri = uri
        self.db = db

    def connect(self):

        uri = self.uri
        client = pymongo.MongoClient(uri)

        return client

    def get_collection(self, client, collection_name):
        mongo_db = self.db
        db = client[mongo_db]
        collection = db[collection_name]

        return collection

    def create_index(self, client, collection_name, index_map, unique=False):
        # index_map: [("field_to_index", ASCENDING)]

        collection = self.get_collection(client, collection_name)
        create = True
        for index in index_map:
            if index[0] in collection.index_information():
                create = False
                break

        if create:
            collection.create_index(index_map, unique=unique)
        else:
            log.error("Cannot create index already exist collection indexing!")


mongo_manager = MongoManager()
