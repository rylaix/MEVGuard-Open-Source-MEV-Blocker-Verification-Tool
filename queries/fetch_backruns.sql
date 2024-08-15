WITH 
latest_transactions AS (
    SELECT 
        from_hex(CAST(json_extract(transactions, '$[0].hash') AS VARCHAR)) AS tx_hash,
        transactions,
        blockNumber,
        to_unixtime(cast(from_unixtime(timestamp / 1000) as timestamp)) as unix_timestamp
    FROM mevblocker.raw_bundles
    WHERE to_unixtime(cast(from_unixtime(timestamp / 1000) as timestamp)) > to_unixtime(NOW() - INTERVAL '1' HOUR)
),

bundles_with_backruns AS (
    SELECT 
        bt.tx_hash,
        bt.transactions,
        et.hash AS transaction_hash,
        et."from",
        et.to,
        et.gas_limit,
        et.gas_price,
        et.data AS calldata,
        bt.blockNumber,
        bt.unix_timestamp as timestamp
    FROM latest_transactions bt
    JOIN ethereum.transactions et ON from_hex(CAST(json_extract(bt.transactions, '$[1].hash') AS VARCHAR)) = et.hash
),

final_selection AS (
    SELECT 
        b.*,
        e.miner,
        e.gas_used,
        e.hash as block_hash,
        e.parent_hash,
        e.base_fee_per_gas
    FROM bundles_with_backruns b
    JOIN ethereum.blocks e ON b.blockNumber = e.number
    WHERE b.timestamp > to_unixtime(NOW() - INTERVAL '1' HOUR)
    AND EXISTS (
        SELECT 1
        FROM ethereum.transactions etx
        WHERE etx.block_number = b.blockNumber  -- Updated reference here
        AND etx.hash = b.tx_hash
    )
)

SELECT * 
FROM final_selection
ORDER BY timestamp DESC;