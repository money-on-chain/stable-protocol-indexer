import datetime
from .models import DocumentTransactions


class BaseEvent:

    name = 'Name'

    def __init__(self, options, connection_helper, filter_contracts_addresses):

        self.options = options
        self.connection_helper = connection_helper
        self.filter_contracts_addresses = filter_contracts_addresses

    def parse_event(self, parsed_receipt, decoded_event):
        pass


class EventMocCABagTCMinted(BaseEvent):

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['sender_'] = decoded_event['sender_'].lower()
        parsed_receipt['recipient_'] = decoded_event['recipient_'].lower()
        parsed_receipt['qTC_'] = str(decoded_event['qTC_'])
        parsed_receipt['qAC_'] = str(decoded_event['qAC_'])
        parsed_receipt['qACfee_'] = str(decoded_event['qACfee_'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        DocumentTransactions.objects(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber']
        ).update_one(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber'],
            gas=parsed['gas'],
            gasPrice=str(parsed['gasPrice']),
            gasUsed=parsed['gasUsed'],
            processed=True,
            confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
            timestamp=parsed['timestamp'],
            eventName=parsed['eventName'],
            sender_=parsed['sender_'],
            recipient_=parsed['recipient_'],
            qTC_=parsed['qTC_'],
            qAC_=parsed['qAC_'],
            qACfee_=parsed['qACfee_'],
            createdAt=parsed["createdAt"],
            lastUpdatedAt=datetime.datetime.now(),
            upsert=True
        )

        return parsed


class EventMocCABagTCRedeemed(BaseEvent):

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['sender_'] = decoded_event['sender_'].lower()
        parsed_receipt['recipient_'] = decoded_event['recipient_'].lower()
        parsed_receipt['qTC_'] = str(decoded_event['qTC_'])
        parsed_receipt['qAC_'] = str(decoded_event['qAC_'])
        parsed_receipt['qACfee_'] = str(decoded_event['qACfee_'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        DocumentTransactions.objects(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber']
        ).update_one(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber'],
            gas=parsed['gas'],
            gasPrice=str(parsed['gasPrice']),
            gasUsed=parsed['gasUsed'],
            processed=True,
            confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
            timestamp=parsed['timestamp'],
            eventName=parsed['eventName'],
            sender_=parsed['sender_'],
            recipient_=parsed['recipient_'],
            qTC_=parsed['qTC_'],
            qAC_=parsed['qAC_'],
            qACfee_=parsed['qACfee_'],
            createdAt=parsed["createdAt"],
            lastUpdatedAt=datetime.datetime.now(),
            upsert=True
        )

        return parsed


class EventMocCABagTPMinted(BaseEvent):

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['i_'] = decoded_event['i_']
        parsed_receipt['sender_'] = decoded_event['sender_'].lower()
        parsed_receipt['recipient_'] = decoded_event['recipient_'].lower()
        parsed_receipt['qTP_'] = str(decoded_event['qTP_'])
        parsed_receipt['qAC_'] = str(decoded_event['qAC_'])
        parsed_receipt['qACfee_'] = str(decoded_event['qACfee_'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        DocumentTransactions.objects(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber']
        ).update_one(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber'],
            gas=parsed['gas'],
            gasPrice=str(parsed['gasPrice']),
            gasUsed=parsed['gasUsed'],
            processed=True,
            confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
            timestamp=parsed['timestamp'],
            eventName=parsed['eventName'],
            i_=parsed['i_'],
            sender_=parsed['sender_'],
            recipient_=parsed['recipient_'],
            qTP_=parsed['qTP_'],
            qAC_=parsed['qAC_'],
            qACfee_=parsed['qACfee_'],
            createdAt=parsed["createdAt"],
            lastUpdatedAt=datetime.datetime.now(),
            upsert=True
        )

        return parsed


class EventMocCABagTPRedeemed(BaseEvent):

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['i_'] = decoded_event['i_']
        parsed_receipt['sender_'] = decoded_event['sender_'].lower()
        parsed_receipt['recipient_'] = decoded_event['recipient_'].lower()
        parsed_receipt['qTP_'] = str(decoded_event['qTP_'])
        parsed_receipt['qAC_'] = str(decoded_event['qAC_'])
        parsed_receipt['qACfee_'] = str(decoded_event['qACfee_'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        DocumentTransactions.objects(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber']
        ).update_one(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber'],
            gas=parsed['gas'],
            gasPrice=str(parsed['gasPrice']),
            gasUsed=parsed['gasUsed'],
            processed=True,
            confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
            timestamp=parsed['timestamp'],
            eventName=parsed['eventName'],
            i_=parsed['i_'],
            sender_=parsed['sender_'],
            recipient_=parsed['recipient_'],
            qTP_=parsed['qTP_'],
            qAC_=parsed['qAC_'],
            qACfee_=parsed['qACfee_'],
            createdAt=parsed["createdAt"],
            lastUpdatedAt=datetime.datetime.now(),
            upsert=True
        )

        return parsed


class EventMocCABagTPSwappedForTP(BaseEvent):

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['iFrom_'] = decoded_event['iFrom_']
        parsed_receipt['iTo_'] = decoded_event['iTo_']
        parsed_receipt['sender_'] = decoded_event['sender_'].lower()
        parsed_receipt['recipient_'] = decoded_event['recipient_'].lower()
        parsed_receipt['qTPfrom_'] = str(decoded_event['qTPfrom_'])
        parsed_receipt['qTPto_'] = str(decoded_event['qTPto_'])
        parsed_receipt['qACfee_'] = str(decoded_event['qACfee_'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        DocumentTransactions.objects(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber']
        ).update_one(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber'],
            gas=parsed['gas'],
            gasPrice=str(parsed['gasPrice']),
            gasUsed=parsed['gasUsed'],
            processed=True,
            confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
            timestamp=parsed['timestamp'],
            eventName=parsed['eventName'],
            iFrom_=parsed['iFrom_'],
            iTo_=parsed['iTo_'],
            sender_=parsed['sender_'],
            recipient_=parsed['recipient_'],
            qTPfrom_=parsed['qTPfrom_'],
            qTPto_=parsed['qTPto_'],
            qACfee_=parsed['qACfee_'],
            createdAt=parsed["createdAt"],
            lastUpdatedAt=datetime.datetime.now(),
            upsert=True
        )

        return parsed


class EventMocCABagTPSwappedForTC(BaseEvent):

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['i_'] = decoded_event['i_']
        parsed_receipt['sender_'] = decoded_event['sender_'].lower()
        parsed_receipt['recipient_'] = decoded_event['recipient_'].lower()
        parsed_receipt['qTP_'] = str(decoded_event['qTP_'])
        parsed_receipt['qTC_'] = str(decoded_event['qTC_'])
        parsed_receipt['qACfee_'] = str(decoded_event['qACfee_'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        DocumentTransactions.objects(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber']
        ).update_one(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber'],
            gas=parsed['gas'],
            gasPrice=str(parsed['gasPrice']),
            gasUsed=parsed['gasUsed'],
            processed=True,
            confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
            timestamp=parsed['timestamp'],
            eventName=parsed['eventName'],
            i_=parsed['i_'],
            sender_=parsed['sender_'],
            recipient_=parsed['recipient_'],
            qTP_=parsed['qTP_'],
            qTC_=parsed['qTC_'],
            qACfee_=parsed['qACfee_'],
            createdAt=parsed["createdAt"],
            lastUpdatedAt=datetime.datetime.now(),
            upsert=True
        )

        return parsed


class EventMocCABagTCSwappedForTP(BaseEvent):

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['i_'] = decoded_event['i_']
        parsed_receipt['sender_'] = decoded_event['sender_'].lower()
        parsed_receipt['recipient_'] = decoded_event['recipient_'].lower()
        parsed_receipt['qTC_'] = str(decoded_event['qTC_'])
        parsed_receipt['qTP_'] = str(decoded_event['qTP_'])
        parsed_receipt['qACfee_'] = str(decoded_event['qACfee_'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        DocumentTransactions.objects(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber']
        ).update_one(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber'],
            gas=parsed['gas'],
            gasPrice=str(parsed['gasPrice']),
            gasUsed=parsed['gasUsed'],
            processed=True,
            confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
            timestamp=parsed['timestamp'],
            eventName=parsed['eventName'],
            i_=parsed['i_'],
            sender_=parsed['sender_'],
            recipient_=parsed['recipient_'],
            qTC_=parsed['qTC_'],
            qTP_=parsed['qTP_'],
            qACfee_=parsed['qACfee_'],
            createdAt=parsed["createdAt"],
            lastUpdatedAt=datetime.datetime.now(),
            upsert=True
        )

        return parsed


class EventMocCABagTCandTPRedeemed(BaseEvent):

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['i_'] = decoded_event['i_']
        parsed_receipt['sender_'] = decoded_event['sender_'].lower()
        parsed_receipt['recipient_'] = decoded_event['recipient_'].lower()
        parsed_receipt['qTC_'] = str(decoded_event['qTC_'])
        parsed_receipt['qTP_'] = str(decoded_event['qTP_'])
        parsed_receipt['qAC_'] = str(decoded_event['qAC_'])
        parsed_receipt['qACfee_'] = str(decoded_event['qACfee_'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        DocumentTransactions.objects(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber']
        ).update_one(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber'],
            gas=parsed['gas'],
            gasPrice=str(parsed['gasPrice']),
            gasUsed=parsed['gasUsed'],
            processed=True,
            confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
            timestamp=parsed['timestamp'],
            eventName=parsed['eventName'],
            i_=parsed['i_'],
            sender_=parsed['sender_'],
            recipient_=parsed['recipient_'],
            qTC_=parsed['qTC_'],
            qTP_=parsed['qTP_'],
            qAC_=parsed['qAC_'],
            qACfee_=parsed['qACfee_'],
            createdAt=parsed["createdAt"],
            lastUpdatedAt=datetime.datetime.now(),
            upsert=True
        )

        return parsed


class EventMocCABagTCandTPMinted(BaseEvent):

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['i_'] = decoded_event['i_']
        parsed_receipt['sender_'] = decoded_event['sender_'].lower()
        parsed_receipt['recipient_'] = decoded_event['recipient_'].lower()
        parsed_receipt['qTC_'] = str(decoded_event['qTC_'])
        parsed_receipt['qTP_'] = str(decoded_event['qTP_'])
        parsed_receipt['qAC_'] = str(decoded_event['qAC_'])
        parsed_receipt['qACfee_'] = str(decoded_event['qACfee_'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        DocumentTransactions.objects(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber']
        ).update_one(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber'],
            gas=parsed['gas'],
            gasPrice=str(parsed['gasPrice']),
            gasUsed=parsed['gasUsed'],
            processed=True,
            confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
            timestamp=parsed['timestamp'],
            eventName=parsed['eventName'],
            i_=parsed['i_'],
            sender_=parsed['sender_'],
            recipient_=parsed['recipient_'],
            qTC_=parsed['qTC_'],
            qTP_=parsed['qTP_'],
            qAC_=parsed['qAC_'],
            qACfee_=parsed['qACfee_'],
            createdAt=parsed["createdAt"],
            lastUpdatedAt=datetime.datetime.now(),
            upsert=True
        )

        return parsed


class EventTokenTransfer(BaseEvent):

    def parse_event(self, parsed_receipt, decoded_event):

        # decode event to support write in mongo
        parsed_receipt['from_'] = decoded_event['from'].lower()
        parsed_receipt['to_'] = decoded_event['to'].lower()
        parsed_receipt['value_'] = str(decoded_event['value'])

        return parsed_receipt

    def parse_event_and_save(self, parsed_receipt, decoded_event):

        parsed = self.parse_event(parsed_receipt, decoded_event)

        address_from_contract = '0x0000000000000000000000000000000000000000'
        address_not_allowed = [str.lower(address_from_contract), self.filter_contracts_addresses]

        if parsed['from_'] in address_not_allowed or \
                parsed['to_'] in address_not_allowed:
            # skip transfers to our contracts
            return parsed

        DocumentTransactions.objects(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber']
        ).update_one(
            hash=parsed['hash'],
            blockNumber=parsed['blockNumber'],
            gas=parsed['gas'],
            gasPrice=str(parsed['gasPrice']),
            gasUsed=parsed['gasUsed'],
            processed=True,
            confirmations=self.connection_helper.connection_manager.block_number - parsed['blockNumber'],
            timestamp=parsed['timestamp'],
            eventName=parsed['eventName'],
            from_=parsed['from_'],
            to_=parsed['to_'],
            value_=parsed['value_'],
            createdAt=parsed["createdAt"],
            lastUpdatedAt=datetime.datetime.now(),
            upsert=True
        )

        return parsed
