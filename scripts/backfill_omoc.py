#!/usr/bin/env python3
"""
One-time historical backfill for the OMOC events (governance / staking / oracles).

Why this exists
---------------
The OMOC contract addresses were not part of ``filter_contracts_addresses`` when
the historical blocks were originally scanned, so their transactions were never
written to ``raw_transactions``. Re-running ``scan_raw_transactions`` from an old
block would reset the ``processed`` flag on every already-indexed MoC tx and
rewind ``moc_indexer.last_raw_tx_block`` (the cursor the live scanner reads).

This script instead pulls OMOC logs directly with ``eth_getLogs`` and feeds them
through the SAME decoders / event handlers the live indexer uses. It only ever
writes the new OMOC collections (``event_OracleManager_*``, ``event_CoinPairPrice_*``,
``event_DelayMachine_*``, ``event_Supporters_*``, ``event_VestingFactory_VestingCreated``,
``event_IncentiveV2_ClaimOK``, ``event_VotingMachine_*``, ``event_TasksRunner_TaskExecuted``,
``event_TaskTriggerOrder_TriggerOrdersReverted`` and ``omoc_operations``) and never
touches ``raw_transactions`` / ``moc_indexer`` / ``operations`` / ``Transaction``.

Every write is an upsert on ``id_event`` (``{txHash}:{logIndex}``) so it is
idempotent: safe to re-run, safe to overlap with the live indexer, safe to stop
and resume.

Resume state lives in a mongo collection (default ``omoc_backfill``, a single
doc ``_id="cursor"``), not a local file, so an ECS task with no persistent
volume can be killed and restarted and it picks up from the last committed
block.

Config / environment
--------------------
``--config`` points at an indexer settings json. These env vars override the
file (same names ``app_run_indexer.py`` uses), which is how you feed it on ECS:

    APP_CONFIG           full config json, replaces the file entirely
    APP_MONGO_URI    ->  mongo.uri
    APP_MONGO_DB     ->  mongo.db
    APP_CONNECTION_URI  ->  uri  (RSK RPC endpoint)

Usage
-----
    python scripts/backfill_omoc.py --config settings/productive/roc-mainnet.json --from-block 3000000
    python scripts/backfill_omoc.py --config config.json --from-block 4200000 --to-block 4300000 --dry-run
    python scripts/backfill_omoc.py --config config.json --addresses-only
    # resume: omit --from-block, it reads last_block from the mongo cursor
    python scripts/backfill_omoc.py --config config.json
"""

import argparse
import datetime
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo.errors import AutoReconnect
from web3 import Web3

from indexer.tasks import StableIndexerTasks
from indexer.scan_logs_transactions import ScanLogsTransactions
from indexer.base.decoder import UnknownEvent
from indexer.logger import log


LOCAL_TIMEZONE = datetime.datetime.now().astimezone().tzinfo

# scalar OMOC contract keys in ``contracts_addresses`` (CoinPairPrice is a list, handled apart)
OMOC_SCALAR_KEYS = [
    "DelayMachine",
    "Supporters",
    "VestingFactory",
    "VotingMachine",
    "IncentiveV2",
    "OracleManager",
    "TasksRunner",
    "TaskTriggerOrder",
]

RANGE_ERROR_HINTS = ("limit", "range", "too many", "10000", "query returned more", "more than")

# resume cursor: a single document {_id: "cursor"} in this collection
DEFAULT_STATE_COLLECTION = "omoc_backfill"
STATE_DOC_ID = "cursor"


def _redact(uri):
    """Hide user:pass@ credentials before logging a connection string."""
    return re.sub(r"://[^/@]+@", "://***@", uri or "")


def load_config(path):
    """Load the settings json, then apply the same env overrides as app_run_indexer.py."""

    if "APP_CONFIG" in os.environ:
        config = json.loads(os.environ["APP_CONFIG"])
        log.info("config loaded from APP_CONFIG env")
    else:
        with open(path) as f:
            config = json.load(f)

    config.setdefault("mongo", {})
    if os.environ.get("APP_MONGO_URI"):
        config["mongo"]["uri"] = os.environ["APP_MONGO_URI"]
    if os.environ.get("APP_MONGO_DB"):
        config["mongo"]["db"] = os.environ["APP_MONGO_DB"]
    if os.environ.get("APP_CONNECTION_URI"):
        config["uri"] = os.environ["APP_CONNECTION_URI"]

    log.info("mongo: {0} db={1}".format(_redact(config["mongo"].get("uri")), config["mongo"].get("db")))
    log.info("rpc:   {0}".format(config.get("uri")))
    return config


def collect_omoc_addresses(contracts_addresses):
    addresses = []
    for key in OMOC_SCALAR_KEYS:
        value = contracts_addresses.get(key)
        if isinstance(value, str) and value:
            addresses.append(value.lower())
    for value in contracts_addresses.get("CoinPairPrice", []) or []:
        addresses.append(value.lower())
    # stable, de-duplicated
    return sorted(set(addresses))


def build_scanner(config):
    """Load every contract exactly like production, then build the log router."""

    # skip schedule_tasks() building throwaway scanner objects; we only need load_contracts()
    cfg = dict(config)
    cfg["tasks"] = {}

    tasks = StableIndexerTasks(cfg)

    if "IRegistry" not in tasks.contracts_addresses:
        raise SystemExit(
            "OMOC is not configured for this network (no 'IRegistry' in addresses). Nothing to backfill."
        )

    scanner = ScanLogsTransactions(
        config,
        tasks.connection_helper,
        tasks.contracts_loaded,
        tasks.contracts_addresses,
        tasks.filter_contracts_addresses,
    )
    return tasks, scanner


def block_timestamp(connection_manager, cache, block_number):
    """tz-aware datetime for a block, built like scan_raw_transactions does."""
    if block_number not in cache:
        ts = connection_manager.get_block(block_number)["timestamp"]
        cache[block_number] = datetime.datetime.fromtimestamp(ts, LOCAL_TIMEZONE)
    return cache[block_number]


def with_mongo_retries(what, fn, retries=5):
    """Run fn() with retries on transient replica-set errors (step-down / election
    mid-write -> AutoReconnect / NotPrimaryError). All mongo writes here are
    upserts, so redoing one after a failed attempt is safe."""
    attempt = 0
    while True:
        try:
            return fn()
        except AutoReconnect as exc:
            attempt += 1
            if attempt > retries:
                raise
            wait = min(30, 2 ** attempt)
            log.warning(
                "{0} failed ({1}); retry {2}/{3} in {4}s".format(what, exc, attempt, retries, wait)
            )
            time.sleep(wait)


def load_state(collection):
    return with_mongo_retries("load resume cursor", lambda: collection.find_one({"_id": STATE_DOC_ID}))


def save_state(collection, **fields):
    now = datetime.datetime.now(LOCAL_TIMEZONE)
    fields["updatedAt"] = now
    with_mongo_retries("save resume cursor", lambda: collection.update_one(
        {"_id": STATE_DOC_ID},
        {"$set": fields, "$setOnInsert": {"createdAt": now}},
        upsert=True,
    ))


def fetch_logs(web3, addresses, start, end, chunk, min_chunk):
    """Return (logs, stop_block, chunk). Shrinks the window on range errors, retries transient ones."""

    attempt = 0
    while True:
        stop = min(start + chunk - 1, end)
        try:
            logs = web3.eth.get_logs(
                {"fromBlock": start, "toBlock": stop, "address": addresses}
            )
            return logs, stop, chunk
        except Exception as exc:  # noqa: BLE001 - provider errors are not a stable type
            message = str(exc).lower()
            is_range_error = any(hint in message for hint in RANGE_ERROR_HINTS)
            if is_range_error and chunk > min_chunk:
                chunk = max(min_chunk, chunk // 2)
                log.warning(
                    "get_logs [{0}-{1}] failed ({2}); shrinking window to {3} blocks".format(
                        start, stop, exc, chunk
                    )
                )
                continue
            attempt += 1
            if attempt <= 5:
                wait = min(30, 2 ** attempt)
                log.warning(
                    "get_logs [{0}-{1}] failed ({2}); retry {3}/5 in {4}s".format(
                        start, stop, exc, attempt, wait
                    )
                )
                time.sleep(wait)
                continue
            raise


def route_log(scanner, connection_manager, ts_cache, raw_log, dry_run, mongo_retries=5):
    """Decode one log and hand it to the same handler the live indexer uses.

    ``mongo_retries`` absorbs transient replica-set hiccups (a step-down / election
    mid-write raises AutoReconnect / NotPrimaryError) so they don't kill an
    otherwise-healthy, hours-long unattended run. Writes are upserts on
    ``id_event``, so redoing one after a failed attempt is safe.
    """

    address = raw_log["address"].lower()
    decoder = scanner.contracts_log_decoder.get(address)
    if decoder is None:
        return None
    try:
        decoded = decoder.decode_log(raw_log)
    except UnknownEvent:
        return None

    event_name = decoded["name"]
    handlers = scanner.map_events_contracts.get(address, {})
    if event_name not in handlers:
        # event exists in the ABI but the indexer does not track it (e.g. OwnershipTransferred)
        return None

    if dry_run:
        return event_name

    created_at = block_timestamp(connection_manager, ts_cache, raw_log["blockNumber"])
    fake_raw_tx = {
        "status": 1,
        "hash": raw_log["transactionHash"].hex(),
        "blockNumber": raw_log["blockNumber"],
        "gas": 0,
        "gasPrice": 0,
        "gasUsed": 0,
        "timestamp": created_at,
        "createdAt": created_at,
        "from": None,
        "logs": [raw_log],
    }
    what = "mongo write for {0} {1}:{2}".format(event_name, fake_raw_tx["hash"], raw_log["logIndex"])
    with_mongo_retries(what, lambda: scanner.process_logs(fake_raw_tx), retries=mongo_retries)
    return event_name


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.json", help="path to the indexer config json (default: config.json)")
    parser.add_argument("--from-block", type=int, help="first block to scan (omit to resume from the mongo cursor)")
    parser.add_argument("--to-block", type=int, help="last block to scan (default: chain tip - scan_logs.confirm_blocks)")
    parser.add_argument("--chunk", type=int, default=2000, help="initial eth_getLogs window in blocks (default: 2000)")
    parser.add_argument("--min-chunk", type=int, default=100, help="smallest window to shrink to on range errors (default: 100)")
    parser.add_argument("--delay", type=float, default=0,
                        help="seconds to sleep between eth_getLogs chunks, to go easier on a shared RPC node (default: 0)")
    parser.add_argument("--state-collection", default=DEFAULT_STATE_COLLECTION,
                        help="mongo collection holding the resume cursor (default: {0})".format(DEFAULT_STATE_COLLECTION))
    parser.add_argument("--reset-state", action="store_true",
                        help="delete the resume cursor before starting (ignored with --dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="decode and count only; write no events and no cursor")
    parser.add_argument("--addresses-only", action="store_true", help="print the resolved OMOC addresses and exit")
    return parser.parse_args()


def main():
    args = parse_args()
    config = load_config(args.config)

    tasks, scanner = build_scanner(config)
    connection_manager = tasks.connection_helper.connection_manager
    web3 = connection_manager.web3

    lower_addresses = collect_omoc_addresses(tasks.contracts_addresses)
    if not lower_addresses:
        raise SystemExit("No OMOC addresses resolved; nothing to do.")
    addresses = [Web3.to_checksum_address(a) for a in lower_addresses]

    if args.addresses_only:
        for key in OMOC_SCALAR_KEYS:
            if key in tasks.contracts_addresses:
                log.info("{0:16s} {1}".format(key, tasks.contracts_addresses[key]))
        for i, cp in enumerate(tasks.contracts_addresses.get("CoinPairPrice", []) or []):
            name = getattr(tasks.contracts_loaded["CoinPairPrice"][i], "coin_pair", "?")
            log.info("{0:16s} {1}  ({2})".format("CoinPairPrice", cp, name))
        return

    # OMOC event collection indexes (id_event / hash) are already ensured at this
    # point - build_scanner() -> StableIndexerTasks() does it automatically now
    # that OMOC is confirmed configured, so the live indexer gets the same
    # self-healing on a fresh deploy without ever needing to run this script.

    state_collection = tasks.connection_helper.mongo_collection(args.state_collection)
    if args.reset_state and not args.dry_run:
        state_collection.delete_one({"_id": STATE_DOC_ID})
        log.info("resume cursor {0}.{1} deleted".format(args.state_collection, STATE_DOC_ID))

    state = load_state(state_collection)

    from_block = args.from_block
    if from_block is None and state and state.get("last_block") is not None:
        from_block = state["last_block"] + 1
        log.info("resuming from mongo cursor {0}.{1}: last_block={2} -> from {3}".format(
            args.state_collection, STATE_DOC_ID, state["last_block"], from_block))
    if from_block is None:
        raise SystemExit(
            "--from-block is required on the first run (no resume cursor in '{0}')".format(args.state_collection))

    tip = connection_manager.block_number
    to_block = args.to_block if args.to_block is not None else tip - config["scan_logs"]["confirm_blocks"]
    if from_block > to_block:
        log.info("nothing to do: from-block {0} is past to-block {1} (already caught up)".format(from_block, to_block))
        return

    log.info(
        "OMOC backfill :: blocks {0} -> {1} :: {2} contracts :: {3}".format(
            from_block, to_block, len(addresses), "DRY RUN" if args.dry_run else "writing"
        )
    )

    started = time.time()
    ts_cache = {}
    counts = {}
    total = 0
    scanned_logs = 0
    chunk = args.chunk
    start = from_block

    while start <= to_block:
        logs, stop, chunk = fetch_logs(web3, addresses, start, to_block, chunk, args.min_chunk)
        chunk_tracked = 0
        for raw_log in logs:
            scanned_logs += 1
            name = route_log(scanner, connection_manager, ts_cache, raw_log, args.dry_run)
            if name:
                counts[name] = counts.get(name, 0) + 1
                chunk_tracked += 1
        total += chunk_tracked

        log.info(
            "blocks {0}-{1}: {2} logs, {3} tracked (running total {4})".format(
                start, stop, len(logs), chunk_tracked, total
            )
        )

        if not args.dry_run:
            save_state(
                state_collection,
                last_block=stop,
                from_block=from_block,
                to_block=to_block,
                events_written=total,
                status="running",
            )

        start = stop + 1

        if args.delay and start <= to_block:
            time.sleep(args.delay)

    elapsed = time.time() - started
    if not args.dry_run:
        save_state(
            state_collection,
            last_block=to_block,
            from_block=from_block,
            to_block=to_block,
            events_written=total,
            status="done",
            completedAt=datetime.datetime.now(LOCAL_TIMEZONE),
        )
    log.info("=" * 60)
    log.info("OMOC backfill done in {0:.1f}s :: {1} logs seen, {2} events {3}".format(
        elapsed, scanned_logs, total, "counted" if args.dry_run else "written"))
    for name in sorted(counts):
        log.info("  {0:40s} {1}".format(name, counts[name]))
    log.info("last block: {0}".format(to_block))


if __name__ == "__main__":
    main()
