import pymongo


__all__ = ["mongo_manager"]


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


mongo_manager = MongoManager()
