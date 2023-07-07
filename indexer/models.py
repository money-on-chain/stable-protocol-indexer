from datetime import datetime
from mongoengine import Document, EmbeddedDocument
from mongoengine.fields import (
    DateTimeField,
    EmbeddedDocumentField,
    ListField,
    StringField,
    IntField,
    BooleanField,
    BinaryField
)


class DocumentRawLog(EmbeddedDocument):
    logIndex = IntField()
    blockNumber = IntField()
    blockHash = BinaryField()
    transactionHash = BinaryField()
    transactionIndex = IntField()
    address = StringField()
    data = BinaryField()
    topics = ListField(BinaryField())


class DocumentRawTransactions(Document):

    meta = {"collection": "raw_transactions"}
    hash = StringField()
    blockNumber = IntField()
    blockHash = StringField()
    from_ = StringField()
    to_ = StringField()
    value = StringField()
    gas = IntField()
    gasPrice = StringField()
    gasUsed = IntField()
    input = StringField()
    receipt = BooleanField()
    processed = BooleanField()
    processed_error = BooleanField()
    confirmations = IntField()
    timestamp = DateTimeField()
    logs = ListField(EmbeddedDocumentField(DocumentRawLog))
    status = IntField()
    not_found = BooleanField()
    createdAt = DateTimeField(default=datetime.now)
    lastUpdatedAt = DateTimeField()


class DocumentIndexer(Document):

    meta = {"collection": "indexer"}
    type = StringField(default='indexer', unique=True)
    last_raw_tx_block = IntField()
    last_block_number = IntField()
    last_block_ts = DateTimeField()
    updatedAt = DateTimeField(default=datetime.now)


class DocumentTransactions(Document):

    meta = {"collection": "transactions"}
    hash = StringField()
    blockNumber = IntField()
    gas = IntField()
    gasPrice = StringField()
    gasUsed = IntField()
    active = BooleanField(default=True)
    reverted = BooleanField(default=False)
    confirmations = IntField()
    timestamp = DateTimeField()
    eventName = StringField()
    sender_ = StringField()
    recipient_ = StringField()
    qTC_ = StringField()
    qAC_ = StringField()
    qACfee_ = StringField()
    i_ = IntField()
    qTP_ = StringField()
    iFrom_ = IntField()
    iTo_ = IntField()
    qTPfrom_ = StringField()
    qTPto_ = StringField()
    from_ = StringField()
    to_ = StringField()
    value_ = StringField()
    createdAt = DateTimeField(default=datetime.now)
    lastUpdatedAt = DateTimeField()
