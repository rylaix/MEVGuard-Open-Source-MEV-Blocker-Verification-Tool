-- SQL script to create necessary tables for tracking

-- Table to track processed bundles, including backrun information
CREATE TABLE IF NOT EXISTS processed_bundles (
    bundle_id TEXT PRIMARY KEY,
    block_number INTEGER,
    status TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    backrun_id TEXT DEFAULT NULL, -- Reference ID for backrun simulations
    violation_detected BOOLEAN DEFAULT FALSE -- Indicates if a violation was detected during the bundle simulation
);

-- Table to track processed transactions, with additional fields for backruns and refunds
CREATE TABLE IF NOT EXISTS processed_transactions (
    tx_hash TEXT PRIMARY KEY,
    bundle_id TEXT,
    block_number INTEGER,
    status TEXT,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_backrun BOOLEAN DEFAULT FALSE, -- Flag to indicate if the transaction is part of a backrun
    refund_amount INTEGER DEFAULT 0, -- Amount of refund calculated during simulation
    FOREIGN KEY(bundle_id) REFERENCES processed_bundles(bundle_id)
);

-- Table to track block data, including information if blocks were simulated
CREATE TABLE IF NOT EXISTS block_data (
    block_number INTEGER PRIMARY KEY,
    transaction_count INTEGER,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_simulated BOOLEAN DEFAULT FALSE -- Indicates if backrun simulation has been performed for this block
);
