-- SQL script to create necessary tables for tracking
CREATE TABLE IF NOT EXISTS processed_bundles (
    bundle_id TEXT PRIMARY KEY,
    block_number INTEGER,
    status TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processed_transactions (
    tx_hash TEXT PRIMARY KEY,
    bundle_id TEXT,
    block_number INTEGER,
    status TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(bundle_id) REFERENCES processed_bundles(bundle_id)
);

CREATE TABLE IF NOT EXISTS block_data (
    block_number INTEGER PRIMARY KEY,
    transaction_count INTEGER,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
