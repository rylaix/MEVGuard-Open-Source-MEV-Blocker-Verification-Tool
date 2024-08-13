SELECT 
    t.hash,
    t.from,
    t.to,
    t.gas,
    t.gas_price,
    t.value,
    t.input AS calldata,
    b.number AS block_number,
    b.timestamp AS block_timestamp,
    r.cumulative_gas_used,
    r.status,
    tr.trace_type,
    tr.action_from AS internal_from,
    tr.action_to AS internal_to,
    tr.action_value AS internal_value
FROM ethereum.transactions t
JOIN ethereum.blocks b ON t.block_number = b.number
JOIN ethereum.receipts r ON t.hash = r.transaction_hash
LEFT JOIN ethereum.traces tr ON t.hash = tr.transaction_hash
WHERE b.number BETWEEN :start_block AND :end_block
-- This query extracts detailed transaction information from Ethereum blockchain.
-- It joins transaction, block, receipt, and trace data to provide a comprehensive view.
-- Parameters :start_block and :end_block define the range of blocks to be analyzed.
-- Trace information provides insight into internal contract interactions.


/*The used query previously is fetching all landed user and searcher transaction since 2023-04-24.

Instead, it should:

Fetch all submitted backruns (even the ones that didn't make it on chain)
Not only collect their transaction hash, but all signed transaction parameters (to, from, gas, calldata, etc), so that they can be simulated in milestone 2.
Filter on block number or some other much smaller subset to avoid using a ton of credits
we intend to always run it on a range of blocks (e.g. the last hours), 
then I'd suggest to make the query mimic that intended range so we can have one query per run of the data fetching script
I think ideally, it would backfill based off a start date and the data that it can find in the /data folder (or DB)*/