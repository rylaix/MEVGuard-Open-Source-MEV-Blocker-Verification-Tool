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
    e.data AS calldata,
    e.nonce
    --e.max_fee_per_gas,
    --e.max_priority_fee_per_gas,
    --gas_limit,
    --access_list (this one especially CAN BE needed, even if it's EIP-2930, must see in simulating tests)
FROM 
    ethereum.transactions e
WHERE 
    e.block_number >= {{start_block}}
    AND e.block_number <= {{end_block}}
ORDER BY 
    e.block_number, e.index;