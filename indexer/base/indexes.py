"""
Index bootstrap shared by the live indexer (app_run_indexer.py) and the OMOC
backfill (scripts/backfill_omoc.py) - both construct a StableIndexerTasks, so
calling this from there covers a fresh deploy no matter which one runs first.

create_index() is a no-op if an equivalent index already exists, so this is
safe to call on every process start - a fresh DB gets its indexes from
scratch, an existing one just confirms what's already there. It only ever
builds indexes; it never reads or writes a document, so it doesn't touch data
any more than a DBA's own `createIndex()` would. Best-effort: a mongo user
without index-management rights (e.g. a read replica) should not block
startup.

It also owns the read-side indexes stable-protocol-api's queries rely on:
the API's mongo user may be read-only, so it never creates indexes itself.
"""

from pymongo.collation import Collation

from ..logger import log

# Lets the API's address queries match regardless of checksum casing while
# still using an index. Must be identical to the collation the API queries
# with (stable-protocol-api api/db.py CASE_INSENSITIVE_COLLATION), or Mongo
# won't pick these indexes.
CASE_INSENSITIVE_COLLATION = Collation(locale="en", strength=2)

# (collection, index keys, extra create_index options)
CORE_INDEX_SPECS = [
    # scan_raw_transactions.py: find_one_and_update({hash, blockNumber}, upsert=True)
    # runs once per transaction while scanning raw blocks.
    ("raw_transactions", [("hash", 1), ("blockNumber", 1)], {}),
    # scan_logs_transactions.py scan_events_txs(): find({"processed": False},
    # sort=[("blockNumber", 1)]) polls this exact filter+sort shape forever,
    # whether or not there's anything left to process.
    ("raw_transactions", [("processed", 1), ("blockNumber", 1)], {}),
    # events.py: every confirmed MoC event handler (Mint/Redeem/Transfer/...)
    # and the reverted-tx path in scan_logs_transactions.py both upsert via
    # find_one_and_update({transactionHash, address, event}) - the highest
    # frequency write in the whole system, against what is likely the oldest
    # and largest collection.
    ("Transaction", [("transactionHash", 1), ("address", 1), ("event", 1)], {}),
    # stable-protocol-api read-side lookups on Transaction (api/routers/operations.py).
    # Built here rather than by the API, whose mongo user may be read-only.
    ("Transaction", [("address", 1), ("createdAt", -1)],
     {"collation": CASE_INSENSITIVE_COLLATION}),
    ("Transaction", [("tokenInvolved", 1), ("createdAt", -1)], {}),
    ("Transaction", [("event", 1), ("confirmationTime", 1)], {}),
    ("Transaction", [("otherAddress", 1)], {}),
]

# Every OMOC collection an event handler in events.py may write (see
# scan_logs_transactions.py's map_events()). Every write there is an upsert
# on id_event, plus a legacy hash-only-doc existence check on hash - without
# indexes on both, insert throughput decays as each collection grows (every
# write full-scans the whole collection twice -> O(n^2) over a backfill, and
# the same cost hits the live indexer as these collections keep growing).
OMOC_EVENT_COLLECTIONS = [
    "event_IncentiveV2_ClaimOK",
    "event_VestingFactory_VestingCreated",
    "event_DelayMachine_PaymentCancel",
    "event_DelayMachine_PaymentDeposit",
    "event_DelayMachine_PaymentWithdraw",
    "event_Supporters_AddStake",
    "event_Supporters_CancelEarnings",
    "event_Supporters_PayEarnings",
    "event_Supporters_Withdraw",
    "event_Supporters_WithdrawStake",
    "event_VotingMachine_PreVoteEvent",
    "event_VotingMachine_VoteEvent",
    "event_VotingMachine_PreVoteStepEvent",
    "event_VotingMachine_VoteStepEvent",
    "event_VotingMachine_AcceptedStepEvent",
    "event_VotingMachine_UnregisterEvent",
    "event_OracleManager_OracleRegistered",
    "event_OracleManager_OracleStakeAdded",
    "event_OracleManager_OracleSubscribed",
    "event_OracleManager_OracleUnsubscribed",
    "event_OracleManager_OracleRemoved",
    "event_CoinPairPrice_PricePublished",
    "event_CoinPairPrice_EmergencyPricePublished",
    "event_CoinPairPrice_ForcedPriceQueryModeSet",
    "event_CoinPairPrice_OracleRewardTransfer",
    "event_CoinPairPrice_NewRound",
    "event_CoinPairPrice_OracleAutoUnsubscribed",
    "event_TasksRunner_TaskExecuted",
    "event_TaskTriggerOrder_TriggerOrdersReverted",
    "omoc_operations",
]

OMOC_INDEX_SPECS = [
    (collection, [(field, 1)], {})
    for collection in OMOC_EVENT_COLLECTIONS
    for field in ("id_event", "hash")
]

# stable-protocol-api read-side lookups on the OMoC collections
# (api/routers/omoc.py). Built here rather than by the API, whose mongo user
# may be read-only.
OMOC_INDEX_SPECS += [
    ("event_VestingFactory_VestingCreated", [("holder", 1), ("createdAt", -1)],
     {"collation": CASE_INSENSITIVE_COLLATION}),
    ("event_IncentiveV2_ClaimOK", [("recipient", 1), ("createdAt", -1)],
     {"collation": CASE_INSENSITIVE_COLLATION}),
]

# Some OMoC event feeds accept an optional address filter that "$or"s the
# address against every party field on the event, so index each of those
# fields (with the createdAt sort key) under the case-insensitive collation.
_ADDRESS_FILTERED_FEEDS = {
    "event_DelayMachine_PaymentCancel": ("source", "destination"),
    "event_DelayMachine_PaymentDeposit": ("source", "destination"),
    "event_DelayMachine_PaymentWithdraw": ("source", "destination"),
    "event_Supporters_AddStake": ("user", "subaccount", "sender"),
    "event_Supporters_Withdraw": ("msgSender", "subaccount", "receiver"),
    "event_Supporters_WithdrawStake": ("user", "subaccount", "destination"),
}
OMOC_INDEX_SPECS += [
    (collection, [(field, 1), ("createdAt", -1)],
     {"collation": CASE_INSENSITIVE_COLLATION})
    for collection, fields in _ADDRESS_FILTERED_FEEDS.items()
    for field in fields
]

# /omoc/staking_operations/ "$or"s the staker address against `subaccount`
# (Supporters_*) and `destination` (DelayMachine_*) on omoc_operations.
OMOC_INDEX_SPECS += [
    ("omoc_operations", [(field, 1), ("createdAt", -1)],
     {"collation": CASE_INSENSITIVE_COLLATION})
    for field in ("subaccount", "destination")
]

# Several VotingMachine feeds can also be filtered by proposal address.
OMOC_INDEX_SPECS += [
    (collection, [("proposal", 1), ("createdAt", -1)],
     {"collation": CASE_INSENSITIVE_COLLATION})
    for collection in (
        "event_VotingMachine_VoteEvent",
        "event_VotingMachine_PreVoteStepEvent",
        "event_VotingMachine_AcceptedStepEvent",
        "event_VotingMachine_UnregisterEvent",
    )
]

# The OracleManager feeds can be filtered by caller address.
OMOC_INDEX_SPECS += [
    (collection, [("caller", 1), ("createdAt", -1)],
     {"collation": CASE_INSENSITIVE_COLLATION})
    for collection in (
        "event_OracleManager_OracleRegistered",
        "event_OracleManager_OracleStakeAdded",
        "event_OracleManager_OracleSubscribed",
        "event_OracleManager_OracleUnsubscribed",
        "event_OracleManager_OracleRemoved",
    )
]

# The CoinPairPrice feeds can be filtered by the coin pair's contract address.
OMOC_INDEX_SPECS += [
    (collection, [("contractAddress", 1), ("createdAt", -1)],
     {"collation": CASE_INSENSITIVE_COLLATION})
    for collection in (
        "event_CoinPairPrice_PricePublished",
        "event_CoinPairPrice_EmergencyPricePublished",
        "event_CoinPairPrice_ForcedPriceQueryModeSet",
        "event_CoinPairPrice_OracleRewardTransfer",
        "event_CoinPairPrice_NewRound",
        "event_CoinPairPrice_OracleAutoUnsubscribed",
    )
]

# The remaining OMoC event collections are served as unfiltered feeds sorted
# by createdAt desc, so a plain createdAt index keeps the sort from blowing
# the in-memory sort limit as the logs grow.
OMOC_INDEX_SPECS += [
    (collection, [("createdAt", -1)], {})
    for collection in (
        "event_DelayMachine_PaymentCancel",
        "event_DelayMachine_PaymentDeposit",
        "event_DelayMachine_PaymentWithdraw",
        "event_Supporters_AddStake",
        "event_Supporters_CancelEarnings",
        "event_Supporters_PayEarnings",
        "event_Supporters_Withdraw",
        "event_Supporters_WithdrawStake",
        "event_VotingMachine_PreVoteEvent",
        "event_VotingMachine_VoteEvent",
        "event_VotingMachine_PreVoteStepEvent",
        "event_VotingMachine_VoteStepEvent",
        "event_VotingMachine_AcceptedStepEvent",
        "event_VotingMachine_UnregisterEvent",
        "event_OracleManager_OracleRegistered",
        "event_OracleManager_OracleStakeAdded",
        "event_OracleManager_OracleSubscribed",
        "event_OracleManager_OracleUnsubscribed",
        "event_OracleManager_OracleRemoved",
        "event_CoinPairPrice_PricePublished",
        "event_CoinPairPrice_EmergencyPricePublished",
        "event_CoinPairPrice_ForcedPriceQueryModeSet",
        "event_CoinPairPrice_OracleRewardTransfer",
        "event_CoinPairPrice_NewRound",
        "event_CoinPairPrice_OracleAutoUnsubscribed",
        "event_TasksRunner_TaskExecuted",
        "event_TaskTriggerOrder_TriggerOrdersReverted",
    )
]


def _create_indexes(mongo_collection, specs, label):
    """`mongo_collection` is ConnectionHelperMongo.mongo_collection (or any
    callable(name) -> pymongo Collection)."""
    created = 0
    for collection_name, keys, options in specs:
        collection = mongo_collection(collection_name)
        try:
            # Match by key pattern, not name: index_information() keys are index
            # NAMES (e.g. the auto-generated "transactionHash_1_address_1_event_1"),
            # which can collide with a differently-optioned index someone already
            # created by hand (unique, collation, ...) under that exact same
            # default name. A naive create_index() then raises
            # IndexOptionsConflict (code 85) even though an index on these same
            # keys already exists and already serves the query just fine - so
            # check by key first instead of relying on create_index()'s own
            # name-based conflict detection.
            target_key = list(keys)
            exists = any(
                info.get("key") == target_key
                for info in collection.index_information().values()
            )
            if exists:
                continue
            collection.create_index(keys, **options)
            created += 1
        except Exception as exc:
            # Best-effort: a lingering name conflict we didn't catch above, or a
            # mongo user without index-management rights (e.g. a read replica),
            # should not block startup.
            log.warning(
                "Could not ensure index {0} on {1}: {2}: {3}".format(
                    keys, collection_name, type(exc).__name__, exc
                )
            )
    log.info("ensured {0} {1} indexes ({2} newly created)".format(len(specs), label, created))


def ensure_core_indexes(mongo_collection):
    """raw_transactions / Transaction - written by every network, OMOC or not."""
    _create_indexes(mongo_collection, CORE_INDEX_SPECS, "core")


def ensure_omoc_indexes(mongo_collection):
    """The OMOC event_* collections - only call this once OMOC is actually
    configured for the network (an IRegistry address is set), otherwise this
    would implicitly create 30-odd empty collections on a MoC-only network."""
    _create_indexes(mongo_collection, OMOC_INDEX_SPECS, "OMOC event")
