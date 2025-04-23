import os
import time
import sqlite3
import yaml
from web3 import Web3
from dotenv import load_dotenv
from utils import log, log_error, load_config
from db.db_utils import connect_to_database
import requests
from multiprocessing import Pool, cpu_count, Manager
import threading

# Base directory for consistent path handling
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

config_path = os.path.join(BASE_DIR, 'config', 'config.yaml')
with open(config_path, 'r') as file:
    config = yaml.safe_load(file)

# Load rate limit settings from config.yaml
calls_per_minute = config['rate_limit_handling'].get('calls_per_minute', 60)
call_interval = 60 / calls_per_minute  # Time interval between each call in seconds
use_multiprocessing = config['performance_tuning'].get('use_multiprocessing', False)
max_processes = config['performance_tuning'].get('max_processes', 'auto')

if max_processes == 'auto':
    max_processes = cpu_count()

def initialize_web3():
    """
    Initialize a Web3 instance using the RPC node URL from the .env file.
    """
    load_dotenv()
    rpc_node_url = os.getenv('RPC_NODE_URL')
    return Web3(Web3.HTTPProvider(rpc_node_url))

def add_hex_prefix_if_missing(value):
    """Ensure that a hex string has the '0x' prefix for both transaction hashes and block numbers."""
    if isinstance(value, str) and not value.startswith("0x"):
        return "0x" + value
    elif isinstance(value, int):
        # Convert integer block numbers to hex with '0x' prefix
        return hex(value)
    return value


def simulate_transaction_bundle(web3, transactions, block_number, block_time, retries=3, backoff_factor=2):
    """
    Simulate a list of transactions as a bundle at a specific block.
    Returns a list of result dicts, each annotated with:
      - transactionHash
      - bundle_id
      - blockNumber
      - stateDiff (if present)
    and records them in your SQLite DB.
    """
    trace_calls = []
    tx_hash_map = []
    bundle_id_map = []
    conn = connect_to_database()
    cursor = conn.cursor()

    for tx in transactions:
        if not isinstance(tx, dict):
            log(f"Skipping non-dict tx entry: {tx}")
            continue
        txh = tx.get('hash')
        bid = tx.get('bundle_id', 'unknown')
        tx_hash_map.append(txh)
        bundle_id_map.append(bid)

        trace_calls.append((
            {
                'from':           tx['from'],
                'to':             tx.get('to'),
                'gas':            tx.get('gas'),
                'gasPrice':       tx.get('gas_price'),
                'maxFeePerGas':   tx.get('max_fee_per_gas'),
                'maxPriorityFeePerGas': tx.get('max_priority_fee_per_gas'),
                'value':          tx.get('value', 0),
                'data':           tx.get('data'),
                'nonce':          tx.get('nonce'),
                'chainId':        tx.get('chainId', 1),
                'accessList':     tx.get('access_list')
            },
            ["stateDiff"]
        ))

    if not trace_calls:
        log("No valid trace_calls constructed; aborting simulate_transaction_bundle.")
        return None

    for attempt in range(retries):
        try:
            time.sleep(call_interval)
            resp = web3.provider.make_request(
                "trace_callMany",
                [ trace_calls, add_hex_prefix_if_missing(block_number) ]
            )
            if resp.get('error'):
                log_error(f"RPC error in trace_callMany: {resp['error']}")
                return None

            results = resp.get('result', [])
            log(f"[DEBUG] trace_callMany returned {len(results)} results")

            # Annotate & fetch blockNumber
            for idx, result in enumerate(results):
                txh = tx_hash_map[idx]
                bid = bundle_id_map[idx]
                result['transactionHash'] = txh
                result['bundle_id'] = bid
                try:
                    txdata = web3.eth.get_transaction(txh)
                    result['blockNumber'] = txdata.get('blockNumber')
                except Exception as e:
                    log_error(f"Failed to fetch blockNumber for {txh}: {e}")
                    result['blockNumber'] = None
                log(f"[INFO] Simulation for tx {txh} in bundle {bid}: blockNumber={result['blockNumber']}")

            # Persist each transaction as simulated
            for txh, bid in zip(tx_hash_map, bundle_id_map):
                cursor.execute(
                    "INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status) VALUES (?, ?, ?, ?)",
                    (txh, bid, block_number, "simulated")
                )
            conn.commit()

            # Apply stateDiffs
            update_block_state(web3, results)

            # Mark bundles successful
            for bid in set(bundle_id_map):
                cursor.execute(
                    "INSERT OR REPLACE INTO processed_bundles (bundle_id, block_number, status, processed_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (bid, block_number, "success")
                )
            conn.commit()

            return results

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                delay = backoff_factor ** attempt
                log(f"429 Too Many Requests; retrying in {delay}s…")
                time.sleep(delay)
            else:
                raise
        except Exception as e:
            log_error(f"Unexpected error in simulate_transaction_bundle: {e}")

    conn.close()
    return None


def simulate_backrun_transaction(web3, tx, block_number, block_time, retries=3, backoff_factor=2):
    """
    Simulate a single backrun transaction at p+1 for a given block.
    Returns a list (usually length 1) of result dict(s), each annotated with:
      - transactionHash
      - bundle_id
      - blockNumber
      - stateDiff (if present)
    """
    if not isinstance(tx, dict) or 'from' not in tx:
        log(f"Skipping invalid backrun tx: {tx}")
        return None

    trace_calls = [(
        {
            'from':           tx['from'],
            'to':             tx.get('to'),
            'gas':            tx.get('gas'),
            'gasPrice':       tx.get('gas_price'),
            'maxFeePerGas':   tx.get('max_fee_per_gas'),
            'maxPriorityFeePerGas': tx.get('max_priority_fee_per_gas'),
            'value':          tx.get('value', 0),
            'data':           tx.get('data'),
            'nonce':          tx.get('nonce'),
            'chainId':        tx.get('chainId', 1),
            'accessList':     tx.get('access_list')
        },
        ["stateDiff"]
    )]

    txh = tx.get('hash')
    bid = tx.get('bundle_id', 'unknown')

    for attempt in range(retries):
        try:
            time.sleep(call_interval)
            resp = web3.provider.make_request(
                "trace_callMany",
                [ trace_calls, add_hex_prefix_if_missing(block_number) ]
            )
            if resp.get('error'):
                log_error(f"Backrun RPC error: {resp['error']}")
                return None

            results = resp.get('result', [])
            for result in results:
                result['transactionHash'] = txh
                result['bundle_id'] = bid
                try:
                    txdata = web3.eth.get_transaction(txh)
                    result['blockNumber'] = txdata.get('blockNumber')
                except Exception as e:
                    log_error(f"Failed to fetch blockNumber for backrun tx {txh}: {e}")
                    result['blockNumber'] = None
                log(f"[INFO] Retrieved blockNumber {result['blockNumber']} for backrun tx {txh}.")

            return results

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                delay = backoff_factor ** attempt
                log(f"429 on backrun; retrying in {delay}s…")
                time.sleep(delay)
            else:
                raise
        except Exception as e:
            log_error(f"Unexpected error in simulate_backrun_transaction for {txh}: {e}")
            break

    return None

def simulate_backruns_and_update_state(web3, transactions, block_number, block_time):
    """
    Simulate all possible backruns at position p+1 and update the state accordingly.
    :param web3: Web3 instance
    :param transactions: List of transactions from the bundle
    :param block_number: The block number in which the transaction is included
    :param block_time: Timestamp of the block
    """
    log(f"Simulating backruns for block {block_number} at timestamp {block_time}...")

    # Establish SQLite connection
    conn = connect_to_database()
    cursor = conn.cursor()

    for tx in transactions:
        # Ensure that the transaction is in dictionary format
        if not isinstance(tx, dict):
            log_error(f"Invalid transaction format: {tx}. Expected dictionary, got {type(tx)}.")
            continue

        # Use the helper function to check balance sufficiency
        if not has_sufficient_balance({'transactions': [tx]}, web3):
            log(f"[INFO] Transaction {tx.get('hash', 'unknown')} has insufficient balance.")
            # Insert transaction record with status 'insufficient_balance' and mark as backrun
            cursor.execute("INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status, is_backrun, processed_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                           (tx.get('hash', 'unknown'), tx.get('bundle_id', 'unknown'), block_number, "insufficient_balance", True))
            conn.commit()
            continue

        try:
            # Log the simulation process for debugging
            log(f"Simulating backrun for transaction {tx['hash']} at position p+1")

            # Perform the simulation for the backrun using the dedicated backrun function
            backrun_result = simulate_backrun_transaction(web3, tx, block_number, block_time)
            
            # Verify if backrun simulation yielded valid results
            if not backrun_result:
                log_error(f"[ERROR] Backrun simulation returned empty results for transaction {tx['hash']}. Skipping.")
                continue

            # Update state management with backrun result
            for result in backrun_result:
                tx_hash = tx.get('hash')
                block_number_result = result.get('blockNumber')
                
                if not tx_hash or not block_number_result:
                    log_error(f"[ERROR] Transaction hash or block number missing in backrun result: {result}. Skipping this transaction.")
                    continue
                
                update_block_state(web3, result)
                
                # Update processed transactions table
                try:
                    cursor.execute(
                        "INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status, is_backrun, processed_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                        (tx_hash, tx.get('bundle_id', 'unknown'), block_number_result, "backrun_simulated", True)
                    )
                    conn.commit()
                    log(f"Backrun simulated successfully for transaction {tx_hash}")
                except sqlite3.OperationalError as e:
                    log_error(f"Database error while updating transaction {tx_hash}: {e}")
                    continue

        except Exception as e:
            log_error(f"Error during backrun simulation for transaction {tx['hash']}: {e}")

    # Mark block as simulated in block_data
    try:
        cursor.execute(
            "UPDATE block_data SET is_simulated = ? WHERE block_number = ?",
            (True, block_number)
        )
        conn.commit()
        log(f"Block {block_number} marked as simulated in block_data.")
    except sqlite3.OperationalError as e:
        log_error(f"Error updating block_data for block {block_number}: {e}")

    conn.close()


def update_block_state(web3, transaction_results):
    """
    Persist each result's stateDiff into your DB.
    Expects each result dict to have:
      - transactionHash
      - blockNumber
      - stateDiff
    Safely skips any malformed entries.
    """
    if not transaction_results:
        log("No transaction_results to update_block_state.")
        return

    # If a single dict is passed, wrap it so the loop always sees dicts
    if isinstance(transaction_results, dict):
        transaction_results = [transaction_results]

    conn = connect_to_database()
    cursor = conn.cursor()

    for result in transaction_results:
        if not isinstance(result, dict):
            log_error(f"Skipping non-dict result: {result}")
            continue

        txh = result.get('transactionHash')
        blk = result.get('blockNumber')
        diff = result.get('stateDiff', {})

        if not txh:
            log_error("Result missing transactionHash—skipping.")
            continue
        if not blk:
            log_error(f"Result for {txh} missing blockNumber—skipping.")
            continue
        if not diff:
            log(f"No stateDiff for {txh}; nothing to apply.")
            continue

        cursor.execute(
            "INSERT OR REPLACE INTO processed_bundles (bundle_id, block_number, status, processed_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (txh, blk, "state_applied")
        )
        conn.commit()
        log(f"[INFO] Applied stateDiff for tx {txh} at block {blk}.")

    conn.close()


def verify_transaction_inclusion(web3, block_number, transaction_hash, retries=3):
    """
    Verify that a transaction is included in a given block.
    :param web3: Web3 instance connected to the RPC node
    :param block_number: Block number to check
    :param transaction_hash: Hash of the transaction to verify
    :return: Boolean indicating if the transaction is included
    """
    for attempt in range(retries):
        try:
            tx = web3.eth.get_transaction(transaction_hash)
            if tx and tx.get('blockNumber') == block_number:
                return True
            elif tx:
                log(f"Transaction {transaction_hash} found but is in block {tx.get('blockNumber')}, not {block_number}.")
                return False

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                retry_interval = config['rate_limit_handling'].get('initial_delay_seconds', 5) * (2 ** attempt)
                log(f"429 Error: Too Many Requests while verifying transaction inclusion. Retrying in {retry_interval} seconds...")
                time.sleep(retry_interval)
            else:
                log_error(f"HTTP error during transaction inclusion verification: {e}")
                return False
        except Exception as e:
            log_error(f"Unexpected error during transaction inclusion verification for transaction {transaction_hash}: {e}")
            return False

    log(f"Exceeded retry limit while verifying inclusion for transaction {transaction_hash}.")
    return False

def has_sufficient_balance(bundle, web3):
    """
    Check if the bundle has sufficient balance to proceed with simulation.
    :param bundle: The bundle containing transactions to be checked.
    :param web3: Web3 instance to interact with the blockchain.
    :return: Boolean indicating if the balance is sufficient.
    """
    for tx in bundle['transactions']:
        from_address = tx.get('from')
        if from_address:
            balance = web3.eth.get_balance(from_address)
            if balance is None or balance < int(tx.get('value', 0)):
                return False
    return True