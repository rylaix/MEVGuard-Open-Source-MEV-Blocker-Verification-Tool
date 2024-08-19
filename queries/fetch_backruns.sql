SELECT block_number, timestamp, transactions
FROM mevblocker.raw_bundles t
JOIN ethereum.transactions e
  ON t.blockNumber = e.block_number
  AND from_hex(CAST(json_extract(transactions, '$[0].hash') AS VARCHAR)) = e.hash
  AND block_number >= {{start_block}}
  AND block_number <= {{end_block}}