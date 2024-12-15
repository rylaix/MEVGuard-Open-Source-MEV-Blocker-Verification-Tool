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
    Simulate the transactions in the given bundle using trace_callMany via raw RPC call.
    Includes retry logic for 429 errors and rate-limiting control.

    Parameters:
    - web3: Web3 instance
    - transactions: List of transactions with full details (from, to, gas, etc.)
    - block_number: The block number in which the transaction is included
    - block_time: Timestamp of the block for identifying bundles within the correct time window
    """
    conn = connect_to_database()
    cursor = conn.cursor()

    trace_calls = []
    transaction_metadata = []

    for tx in transactions:
        if not isinstance(tx, dict):
            log(f"Skipping invalid transaction format: {tx}. Expected dictionary, got {type(tx)}.")
            continue

        if not has_sufficient_balance({'transactions': [tx]}, web3):
            log(f"[INFO] Transaction {tx.get('hash', 'unknown')} has insufficient balance.")
            cursor.execute(
                "INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status) VALUES (?, ?, ?, ?)",
                (tx.get('hash', 'unknown'), tx.get('bundle_id', 'unknown'), block_number, "insufficient_balance")
            )
            conn.commit()
            continue

        original_hash = tx.get('hash')
        trace_call_object = {
            'from': tx['from'],
            'to': tx.get('to', None),
            'gas': tx.get('gas', None),
            'gasPrice': tx.get('gas_price', None),
            'maxFeePerGas': tx.get('max_fee_per_gas', None),
            'maxPriorityFeePerGas': tx.get('max_priority_fee_per_gas', None),
            'value': tx.get('value', 0),
            'data': tx.get('data', None),
            'nonce': tx.get('nonce', None),
            'chainId': tx.get('chainId', 1),
            'accessList': tx.get('access_list', None)
        }

        transaction_metadata.append({
            'original_hash': original_hash,
            'bundle_id': tx.get('bundle_id', 'unknown')
        })
        trace_calls.append((trace_call_object, ["stateDiff"]))

    log(f"trace_calls structure: {trace_calls}")

    if not trace_calls:
        log("No valid trace calls were constructed. Aborting simulation.")
        conn.close()
        return None

    for attempt in range(retries):
        try:
            time.sleep(call_interval)
            response = web3.provider.make_request("trace_callMany", [trace_calls])

            if response.get('error'):
                log(f"Error in trace_callMany: {response['error']}")
                conn.close()
                return None

            enriched_results = []
            results = response.get('result', [])
            for idx, result in enumerate(results):
                metadata = transaction_metadata[idx]
                tx_block_number = None
                try:
                    if metadata['original_hash']:
                        tx = web3.eth.get_transaction(metadata['original_hash'])
                        tx_block_number = tx.get('blockNumber')
                except Exception as e:
                    log_error(f"Could not retrieve block number for transaction {metadata['original_hash']}: {e}")

                enriched_result = result.copy()
                enriched_result.update({
                    'transactionHash': metadata['original_hash'],
                    'blockNumber': tx_block_number or block_number,
                    'bundleId': metadata['bundle_id']
                })
                enriched_results.append(enriched_result)

                cursor.execute(
                    "INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status) VALUES (?, ?, ?, ?)",
                    (metadata['original_hash'], metadata['bundle_id'], tx_block_number or block_number, "simulated")
                )
                conn.commit()

            update_block_state(web3, enriched_results)

            for metadata in transaction_metadata:
                cursor.execute(
                    "INSERT OR REPLACE INTO processed_bundles (bundle_id, block_number, status, processed_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (metadata['bundle_id'], block_number, "success")
                )
                conn.commit()

            conn.close()
            return enriched_results

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                log(f"429 Error: Too Many Requests. Retrying in {backoff_factor ** attempt} seconds...")
                time.sleep(backoff_factor ** attempt)
            else:
                raise e
        except Exception as e:
            log_error(f"Unexpected error during transaction bundle simulation: {e}")
            conn.close()
            return None

def simulate_backrun_transaction(web3, tx, block_number, block_time, retries=3, backoff_factor=2):
    """
    Dedicated function to simulate a backrun transaction.
    This is separate from the main simulation to ensure accuracy.

    :param web3: Web3 instance
    :param tx: Transaction dictionary
    :param block_number: The block number in which the transaction is included
    :param block_time: Timestamp of the block
    """
    trace_calls = []

    if not isinstance(tx, dict):
        log(f"Skipping invalid transaction format: {tx}. Expected dictionary, got {type(tx)}.")
        return None

    if 'from' not in tx:
        log(f"Skipping transaction due to missing 'from' field: {tx}.")
        return None

    if not has_sufficient_balance({'transactions': [tx]}, web3):
        log(f"[INFO] Transaction {tx.get('hash', 'unknown')} has insufficient balance.")
        conn = connect_to_database()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status, is_backrun) VALUES (?, ?, ?, ?, ?)",
                       (tx.get('hash', 'unknown'), tx.get('bundle_id', 'unknown'), block_number, "insufficient_balance", True))
        conn.commit()
        conn.close()
        return None

    log(f"Adding transaction {tx.get('hash', 'unknown')} to trace_calls structure with details: {tx}")

    trace_call_object = {
        'from': tx['from'],
        'to': tx.get('to', None),
        'gas': tx.get('gas', None),
        'gasPrice': tx.get('gas_price', None),
        'maxFeePerGas': tx.get('max_fee_per_gas', None),
        'maxPriorityFeePerGas': tx.get('max_priority_fee_per_gas', None),
        'value': tx.get('value', 0),
        'data': tx.get('data', None),
        'nonce': tx.get('nonce', None),
        'chainId': tx.get('chainId', 1),
        'accessList': tx.get('access_list', None)
    }

    trace_calls.append((trace_call_object, ["stateDiff"]))

    log(f"trace_calls structure for backrun: {trace_calls}")

    original_hash = tx.get('hash')

    for attempt in range(retries):
        try:
            time.sleep(call_interval)
            response = web3.provider.make_request("trace_callMany", [trace_calls])

            if response.get('error'):
                log(f"Error in trace_callMany (backrun): {response['error']}")
                return None

            transaction_results = response.get('result', [])
            if not transaction_results:
                log("[ERROR] Empty results from trace_callMany (backrun). Aborting.")
                return None

            # Enrich results with original transaction hash and block number
            enriched_results = []
            for result in transaction_results:
                tx_block_number = None
                try:
                    if original_hash:
                        tx = web3.eth.get_transaction(original_hash)
                        tx_block_number = tx.get('blockNumber')
                except Exception as e:
                    log_error(f"Could not retrieve block number for transaction {original_hash}: {e}")

                enriched_result = result.copy()
                enriched_result.update({
                    'transactionHash': original_hash,
                    'blockNumber': tx_block_number or block_number
                })
                enriched_results.append(enriched_result)

            return enriched_results

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                log(f"429 Error: Too Many Requests (backrun). Retrying in {backoff_factor ** attempt} seconds...")
                time.sleep(backoff_factor ** attempt)
            else:
                log_error(f"HTTP error during backrun simulation: {e}")
                break
        except Exception as e:
            log_error(f"Unexpected error during backrun simulation: {e}")
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
    conn = connect_to_database()
    cursor = conn.cursor()

    for tx in transactions:
        if not isinstance(tx, dict):
            log_error(f"Invalid transaction format: {tx}. Expected dictionary, got {type(tx)}.")
            continue

        if not has_sufficient_balance({'transactions': [tx]}, web3):
            log(f"[INFO] Transaction {tx.get('hash', 'unknown')} has insufficient balance.")
            cursor.execute("INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status, is_backrun, processed_at) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                           (tx.get('hash', 'unknown'), tx.get('bundle_id', 'unknown'), block_number, "insufficient_balance", True))
            conn.commit()
            continue

        try:
            log(f"Simulating backrun for transaction {tx['hash']} at position p+1")
            backrun_result = simulate_backrun_transaction(web3, tx, block_number, block_time)

            if not backrun_result:
                log_error(f"[ERROR] Backrun simulation returned empty results for transaction {tx['hash']}. Skipping.")
                continue

            for result in backrun_result:
                tx_hash = result.get('transactionHash')
                block_number_result = result.get('blockNumber')

                if not tx_hash or not block_number_result:
                    log_error(f"[ERROR] Transaction hash or block number missing in backrun result: {result}. Skipping this transaction.")
                    continue

                update_block_state(web3, [result])

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
    Update the blockchain state after a successful transaction simulation.
    :param web3: Web3 instance connected to the RPC node
    :param transaction_results: Result of the simulated transactions
    :return: Updated block state
    """
    if not transaction_results:
        log("No transaction results provided for state update. Aborting.")
        return

    # Establish SQLite connection
    conn = connect_to_database()
    cursor = conn.cursor()
    
    for result in transaction_results:
        tx_hash = result.get('transactionHash')
        block_number = result.get('blockNumber')
        state_diff = result.get('stateDiff', {})

        if not tx_hash or not block_number:
            log_error(f"[ERROR] Transaction hash or block number missing in transaction result: {result}")
            continue

        if state_diff:
            # Store state_diff in the processed_bundles table if needed for future state analysis
            cursor.execute("INSERT OR REPLACE INTO processed_bundles (bundle_id, block_number, status, violation_detected, processed_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                            (tx_hash, block_number, "success", False))
            conn.commit()
            log(f"[INFO] Updated state for transaction {tx_hash} in block {block_number}. StateDiff stored in database.")
        else:
            log(f"[WARNING] No stateDiff available for transaction {tx_hash}. Skipping state update.")

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