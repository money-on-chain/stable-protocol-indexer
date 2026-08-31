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
``event_IncentiveV2_ClaimOK``, ``event_VotingMachine_*`` and ``omoc_operations``) and
never touches ``raw_transactions`` / ``moc_indexer`` / ``operations`` / ``Transaction``.

Every write is an upsert on ``id_event`` (``{txHash}:{logIndex}``) so it is
idempotent: safe to re-run, safe to overlap with the live indexer, safe to stop
and resume.

Usage
-----
    python scripts/backfill_omoc.py --config settings/productive/roc-mainnet.json --from-block 3000000
    python scripts/backfill_omoc.py --config config.json --from-block 4200000 --to-block 4300000 --dry-run
    python scripts/backfill_omoc.py --config config.json --addresses-only
"""

import argparse
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
]

RANGE_ERROR_HINTS = ("limit", "range", "too many", "10000", "query returned more", "more than")


def load_config(path):
    with open(path) as f:
        return json.load(f)


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
    if block_number not in cache:
        ts = connection_manager.block_timestamp(block_number)
        cache[block_number] = datetime.datetime.fromtimestamp(ts, LOCAL_TIMEZONE)
    return cache[block_number]


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


def route_log(scanner, connection_manager, ts_cache, raw_log, dry_run):
    """Decode one log and hand it to the same handler the live indexer uses."""

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
    scanner.process_logs(fake_raw_tx)
    return event_name


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="config.json", help="path to the indexer config json (default: config.json)")
    parser.add_argument("--from-block", type=int, help="first block to scan (or read from --state-file)")
    parser.add_argument("--to-block", type=int, help="last block to scan (default: chain tip - scan_logs.confirm_blocks)")
    parser.add_argument("--chunk", type=int, default=2000, help="initial eth_getLogs window in blocks (default: 2000)")
    parser.add_argument("--min-chunk", type=int, default=100, help="smallest window to shrink to on range errors (default: 100)")
    parser.add_argument("--state-file", help="json file to persist/resume the last completed block (kept out of mongo)")
    parser.add_argument("--dry-run", action="store_true", help="decode and count only; write nothing")
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

    from_block = args.from_block
    if from_block is None and args.state_file and os.path.exists(args.state_file):
        with open(args.state_file) as f:
            from_block = json.load(f)["last_block"] + 1
            log.info("Resuming from --state-file at block {0}".format(from_block))
    if from_block is None:
        raise SystemExit("--from-block is required (or provide an existing --state-file)")

    tip = connection_manager.block_number
    to_block = args.to_block if args.to_block is not None else tip - config["scan_logs"]["confirm_blocks"]
    if from_block > to_block:
        raise SystemExit("from-block ({0}) is past to-block ({1})".format(from_block, to_block))

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

        if args.state_file and not args.dry_run:
            with open(args.state_file, "w") as f:
                json.dump({"last_block": stop, "updatedAt": datetime.datetime.now().isoformat()}, f)

        start = stop + 1

    elapsed = time.time() - started
    log.info("=" * 60)
    log.info("OMOC backfill done in {0:.1f}s :: {1} logs seen, {2} events {3}".format(
        elapsed, scanned_logs, total, "counted" if args.dry_run else "written"))
    for name in sorted(counts):
        log.info("  {0:40s} {1}".format(name, counts[name]))
    log.info("last block: {0}".format(to_block))


if __name__ == "__main__":
    main()
