# scripts/

One-off / operational scripts that run outside the indexer task loop.

---

## `backfill_omoc.py`

One-time historical backfill for the **OMOC** events (governance / staking /
decentralized oracles).

### Why it exists

The OMOC contract addresses were not part of `filter_contracts_addresses` when
the historical blocks were first scanned, so their transactions were never
written to `raw_transactions`. Re-running `scan_raw_transactions` from an old
block would reset the `processed` flag on every already-indexed MoC tx and
rewind `moc_indexer.last_raw_tx_block` (the cursor the live scanner reads).

This script instead pulls OMOC logs directly with `eth_getLogs` and feeds them
through the **same** decoders / event handlers the live indexer uses
(`ScanLogsTransactions`). It only writes the new OMOC collections and never
touches `raw_transactions` / `moc_indexer` / `operations` / `Transaction`.

Collections written:

- `event_OracleManager_*`
- `event_CoinPairPrice_*`
- `event_DelayMachine_*`, `omoc_operations`
- `event_Supporters_*`
- `event_VestingFactory_VestingCreated`
- `event_IncentiveV2_ClaimOK`
- `event_VotingMachine_*`
- `event_TasksRunner_TaskExecuted` (only when `addresses.TasksRunner` is set)
- `event_TaskTriggerOrder_TriggerOrdersReverted` (only when `addresses.TaskTriggerOrder` is set)

Every write is an upsert on `id_event` (`{txHash}:{logIndex}`), so it is
**idempotent**: safe to re-run, safe to overlap with the live indexer, safe to
stop and resume.

### Resume cursor (Mongo, not a file)

Progress is stored in a Mongo collection (default `omoc_backfill`, a single
document `_id: "cursor"`):

```json
{
  "_id": "cursor",
  "last_block": 8039102,
  "from_block": 1321713,
  "to_block": 8039102,
  "events_written": 2250,
  "status": "running | done",
  "createdAt": "...",
  "updatedAt": "...",
  "completedAt": "..."
}
```

Because state is in Mongo, an ECS task with no persistent volume can be killed
and restarted and it picks up from `last_block + 1`. Omit `--from-block` to
resume; pass it to force a start point (it wins over the cursor).

### Config & environment

`--config` points at an indexer settings json (e.g.
`settings/productive/roc-mainnet.json`). The config **must** contain
`addresses.IRegistry` or the script exits — that is how it discovers the
DelayMachine / Supporters / VestingFactory / VotingMachine / OracleManager and
every `CoinPairPrice` instance.

`addresses.IncentiveV2`, `addresses.TasksRunner` and `addresses.TaskTriggerOrder`
are **optional** explicit addresses (none has a published registry constant). Set
`TasksRunner` to also index `TasksRunner.TaskExecuted`, and `TaskTriggerOrder` to
index the mocFlow `TaskTriggerOrder.TriggerOrdersReverted` failure log; leave one
out and that contract is simply skipped.

These env vars override the file (same names as `app_run_indexer.py`), which is
how you feed it on ECS:

| env var              | overrides            |
| -------------------- | -------------------- |
| `APP_CONFIG`         | entire config (JSON string) |
| `APP_MONGO_URI`      | `mongo.uri`          |
| `APP_MONGO_DB`       | `mongo.db`           |
| `APP_CONNECTION_URI` | `uri` (RSK RPC endpoint) |

On startup it logs the effective mongo (credentials redacted) and rpc.

### Flags

| flag                | default                         | purpose |
| ------------------- | ------------------------------- | ------- |
| `--config`          | `config.json`                   | indexer settings json |
| `--from-block`      | *(resume from cursor)*          | first block to scan |
| `--to-block`        | chain tip − `scan_logs.confirm_blocks` | last block to scan |
| `--chunk`           | `2000`                          | initial `eth_getLogs` window; auto-halves toward `--min-chunk` on provider range errors |
| `--min-chunk`       | `100`                           | floor for the shrink |
| `--state-collection`| `omoc_backfill`                 | Mongo collection holding the resume cursor |
| `--reset-state`     | off                             | delete the cursor before starting (ignored with `--dry-run`) |
| `--dry-run`         | off                             | decode + count only; write no events and no cursor |
| `--addresses-only`  | off                             | print the resolved OMOC addresses and exit |

### Usage

```bash
# 0. resolve IRegistry -> all OMOC + CoinPairPrice addresses (RPC only, no writes)
python scripts/backfill_omoc.py --config config.json --addresses-only

# 1. dry run over a range: decode + count per event type, write nothing
python scripts/backfill_omoc.py --config config.json \
    --from-block 4200000 --to-block 4300000 --dry-run

# 2. real backfill from a start block to chain tip
python scripts/backfill_omoc.py --config config.json --from-block <omoc-deploy-block>

# 3. resume after a stop / crash (reads last_block from the Mongo cursor)
python scripts/backfill_omoc.py --config config.json
```

On a **paid RPC provider** raise `--chunk` (10k–50k, whatever the provider's
`eth_getLogs` cap allows) for far fewer round-trips. On `public-node.rsk.co`
the window collapses to `--min-chunk` (~100 blocks) and it runs slowly — leave
it detached; the Mongo cursor makes kill/restart safe.

### Run on ECS

Container command:

```
python scripts/backfill_omoc.py --config config.json --from-block <omoc-deploy-block>
```

Task-definition env: `APP_MONGO_URI`, `APP_MONGO_DB`, `APP_CONNECTION_URI`.

The first run needs `--from-block`. If the task dies, the next run (same
command) sees the cursor and resumes; once it reaches `--to-block` it writes
`status: "done"` and, on any further run where the cursor is already past the
target, exits 0 without work. For a one-shot `RunTask`, drop `--from-block` on
reruns entirely.

### Monitor

```js
db.omoc_backfill.findOne({ _id: "cursor" })
```

### Requirements

Needs the project deps (`web3`, `pymongo`, …) importable — see the repo README.
Local dev:

```bash
~/.pyenv/versions/3.9.18/bin/python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/backfill_omoc.py --config config.json --addresses-only
```
