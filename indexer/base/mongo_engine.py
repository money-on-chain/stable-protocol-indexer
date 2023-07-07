from mongoengine import connect


__all__ = ["mongo_engine_manager"]


class MongoEngineManager:

    def __init__(self, uri='mongodb://localhost:27017/', db='indexer_db'):

        self.uri = uri
        self.db = db

    def set_connection(self, uri='mongodb://localhost:27017/', db='indexer_db'):

        self.uri = uri
        self.db = db

    def connect(self):

        return connect(self.db, host=self.uri, alias="default")


mongo_engine_manager = MongoEngineManager()
