/*WITH 
backrun_transactions AS (
    SELECT 
        DISTINCT from_hex(CAST(json_extract(transactions, '$[1].hash') AS VARCHAR)) AS searcher_tx,
        transactions
    FROM mevblocker.raw_bundles
    WHERE json_array_length(transactions) = 2
    AND from_hex(CAST(json_extract(transactions, '$[1].from') AS VARCHAR)) != from_hex(CAST(json_extract(transactions, '$[0].from') AS VARCHAR))
),

-- Join with the Ethereum transactions to fetch additional details
transaction_details AS (
    SELECT et.block_number, et.hash, et."from", et.to, et.gas, et.input AS calldata
    FROM backrun_transactions bt
    INNER JOIN ethereum.transactions et ON bt.searcher_tx = et.hash
)

SELECT 
    td.block_number,
    td."from" AS searcher,
    td.to,
    td.gas,
    td.calldata,
    bt.transactions
FROM transaction_details td
JOIN ethereum.blocks b ON td.block_number = b.number
WHERE td.block_number BETWEEN {{start_block}} AND {{end_block}}
*/
-- This SQL query is only an a attempt to reach the desired espectations. Pure test purposes only --