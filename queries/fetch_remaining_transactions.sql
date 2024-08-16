SELECT 
    e.block_number, 
    e.timestamp,
    e.transactions
FROM 
    ethereum.transactions e
WHERE 
    e.block_number >= {{start_block}} 
    AND e.block_number <= {{end_block}} 
    AND e.hash NOT IN (
        SELECT from_hex(CAST(json_extract(transactions, '$[0].hash') AS VARCHAR)) 
        FROM mevblocker.raw_bundles t 
        WHERE t.blockNumber = e.block_number
    )
ORDER BY 
    e.block_number, e.hash;
