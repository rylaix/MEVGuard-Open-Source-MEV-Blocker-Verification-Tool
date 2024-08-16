SELECT 
    t.blockNumber, 
    t.timestamp, 
    t.transactions
FROM 
    mevblocker.raw_bundles t
JOIN 
    ethereum.transactions e 
    ON t.blockNumber = e.block_number
WHERE 
    t.blockNumber = (SELECT MAX(number) FROM ethereum.blocks)
ORDER BY 
    t.timestamp DESC
LIMIT 1;