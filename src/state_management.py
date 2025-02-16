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
    trace_calls = []

    # Establish SQLite connection for tracking
    conn = connect_to_database()
    cursor = conn.cursor()
    
    tx_hash_map = []

    # Construct trace_call objects for each transaction in the bundle
    for tx in transactions:
        tx_hash = tx.get('hash')
        tx_hash_map.append((tx_hash))
        if not isinstance(tx, dict):
            log(f"Skipping invalid transaction format: {tx}. Expected dictionary, got {type(tx)}.")
            continue

        log(f"Processing transaction {tx.get('hash', 'unknown')} for simulation.")
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

    log(f"Constructed trace_calls structure: {trace_calls}")

    # If no valid trace calls were constructed, abort simulation
    if not trace_calls:
        log("No valid trace calls were constructed. Aborting simulation.")
        return None

    # Execute simulation with retries
    for attempt in range(retries):
        try:
            time.sleep(call_interval)
            response = web3.provider.make_request("trace_callMany", [trace_calls])

            # Handle errors in the RPC response
            if response.get('error'):
                log(f"Error in trace_callMany: {response['error']}")
                return None

            results = response.get('result', [])
            log(f"RESULT WAS {results}")
            for result in results:
                tx_hash = tx_hash_map
                tx_data = web3.eth.get_transaction(tx_hash)
                log(f"tx_data state_management simulate_transaction_bundle1 is {tx_data}")
                            
                result['blockNumber'] = tx_data.get('blockNumber')
                log(f"[INFO] Retrieved blockNumber {result['blockNumber']} for transaction {tx_hash}.")

            # Record successful simulation results in the database
            for tx in transactions:
                tx_hash = tx.get('hash')
                log(f"tx_hash state_management simulate_transaction_bundle1 is {tx_hash}")
                if tx_hash:
                    cursor.execute(
                        "INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status) VALUES (?, ?, ?, ?)",
                        (tx_hash, tx.get('bundle_id', 'unknown'), block_number, "simulated")
                    )
                    conn.commit()

            # Update state and mark bundles as processed
            update_block_state(web3, response.get('result'))

            for tx in transactions:
                bundle_id = tx.get('bundle_id', 'unknown')
                cursor.execute(
                    "INSERT OR REPLACE INTO processed_bundles (bundle_id, block_number, status, processed_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                    (bundle_id, block_number, "success")
                )
                conn.commit()

            return response.get('result')

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
    Dedicated function to simulate a backrun transaction. This is separate from the main simulation to ensure accuracy.
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

    log(f"Preparing trace call for backrun transaction {tx.get('hash', 'unknown')}.")
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

    # Retry logic for backrun simulation
    for attempt in range(retries):
        try:
            time.sleep(call_interval)
            response = web3.provider.make_request("trace_callMany", [trace_calls])

            if response.get('error'):
                log(f"Error in trace_callMany (backrun): {response['error']}")
                return None

            transaction_results = response.get('result', [])
            for result in transaction_results:
                tx_hash = result.get('transactionHash')
                if tx_hash:
                    try:
                        tx_data = web3.eth.get_transaction(tx_hash)
                        log(f"tx_data state_management2 simulate)backrun_transaction1 is {tx_data}")
                        result['blockNumber'] = tx_data.get('blockNumber')
                        log(f"[INFO] Retrieved blockNumber {result['blockNumber']} for backrun transaction {tx_hash}.")
                    except Exception as e:
                        log(f"[ERROR] Failed to retrieve blockNumber for backrun transaction {tx_hash}: {e}")
                        result['blockNumber'] = None

            return transaction_results

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
        try:
            tx_data = web3.eth.get_transaction(tx_hash)
            result['blockNumber'] = tx_data.get('blockNumber')
            log(f"[INFO] Retrieved blockNumber {result['blockNumber']} for transaction {tx_hash}.")
        except Exception as e:
            log(f"[ERROR] Failed to retrieve blockNumber for transaction {tx_hash}: {e}")
            result['blockNumber'] = None

        if not result.get('blockNumber'):
            log_error(f"[ERROR] Missing blockNumber for transaction {tx_hash}. Skipping.")
            continue

        state_diff = result.get('stateDiff', {})

        if state_diff:
            cursor.execute("INSERT OR REPLACE INTO processed_bundles (bundle_id, block_number, status, violation_detected, processed_at) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
                            (tx_hash, result['blockNumber'], "success", False))
            conn.commit()
            log(f"[INFO] Updated state for transaction {tx_hash} in block {result['blockNumber']}.")
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