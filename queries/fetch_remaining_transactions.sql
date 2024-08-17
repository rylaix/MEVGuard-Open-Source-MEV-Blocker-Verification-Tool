SELECT 
    e.block_number, 
    e.block_time AS timestamp,
    e.hash,
    e."from",
    e."to",
    e.value,
    e.gas_used AS gas,
    e.gas_price,
    e.index AS transaction_index,
    e.data AS calldata
    e.nonce
FROM 
    ethereum.transactions e
WHERE 
    e.block_number >= {{start_block}}
    AND e.block_number <= {{end_block}}
ORDER BY 
    e.block_number, e.index;