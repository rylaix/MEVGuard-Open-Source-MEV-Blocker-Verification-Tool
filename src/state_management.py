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
import msgpack  # Faster serialization alternative to JSON

config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
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

    # Establish SQLite connection
    conn = connect_to_database()
    cursor = conn.cursor()

    # Ensure that transactions have the required fields before adding to trace_calls
    for tx in transactions:
        # Validate that tx is a dictionary and has the required 'from' field
        if not isinstance(tx, dict):
            log(f"Skipping invalid transaction format: {tx}. Expected dictionary, got {type(tx)}.")
            continue
        if 'from' not in tx:
            log(f"Skipping transaction due to missing 'from' field: {tx}.")
            continue

        # Log transaction details for debugging purposes
        log(f"Adding transaction {tx.get('hash', 'unknown')} to trace_calls structure with details: {tx}")

        # Construct the trace call object for this transaction
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

        # Append each trace call as a tuple with the trace object and the trace type in a sequence (e.g., list)
        trace_calls.append((trace_call_object, ["stateDiff"]))  # Use a list ["stateDiff"] instead of a string

    # Log the final trace_calls structure for debugging
    log(f"trace_calls structure: {trace_calls}")

    # If trace_calls is empty, log a warning and return
    if not trace_calls:
        log("No valid trace calls were constructed. Aborting simulation.")
        return None

    # Proceed with the simulation if trace_calls is not empty
    for attempt in range(retries):
        try:
            # Rate limit by waiting between requests
            time.sleep(call_interval)
            
            # The parameters for trace_callMany should be formatted as an array of tuples with the trace type as a sequence: [(trace_call_object, ["stateDiff"])]
            response = web3.provider.make_request("trace_callMany", [trace_calls])

            # Check for errors in the response
            if response.get('error'):
                log(f"Error in trace_callMany: {response['error']}")
                return None

            # Record each transaction being simulated in the SQLite database
            for tx in transactions:
                tx_hash = tx.get('hash')
                if tx_hash:
                    cursor.execute("INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status) VALUES (?, ?, ?, ?)",
                                    (tx_hash, tx.get('bundle_id', 'unknown'), block_number, "simulated"))
                    conn.commit()

            # Update the state after successful simulation
            update_block_state(web3, response.get('result'))

            # Mark the bundle as successfully processed in the database
            for tx in transactions:
                bundle_id = tx.get('bundle_id', 'unknown')
                cursor.execute("INSERT OR REPLACE INTO processed_bundles (bundle_id, block_number, status, processed_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                                (bundle_id, block_number, "success"))
                conn.commit()

            return response.get('result')

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Too Many Requests
                log(f"429 Error: Too Many Requests. Retrying in {backoff_factor ** attempt} seconds...")
                time.sleep(backoff_factor ** attempt)
            else:
                raise e
        except Exception as e:
            log_error(f"Unexpected error during transaction bundle simulation: {e}")

    conn.close()
    return None



def simulate_backruns_and_update_state(web3, transactions, block_number, block_time):
    """
    Simulate all possible backruns at position p+1 and update the state accordingly.
    Parameters:
    - web3: Web3 instance
    - transactions: List of transactions from the bundle
    - block_number: The block number in which the transaction is included
    - block_time: Timestamp of the block
    """
    # Establish SQLite connection
    conn = connect_to_database()
    cursor = conn.cursor()
    
    log(f"Simulating backruns for block {block_number} at timestamp {block_time}...")

    # Use multiprocessing.Manager to create a shared list to track processed transactions
    manager = Manager()
    shared_processed_transactions = manager.list()  # Use shared list to track processed transactions
    
    def process_transaction(tx):
        try:
            # Identify and process backruns (transactions at p+1)
            log(f"Simulating backrun for transaction {tx['hash']} at position p+1")

            # Perform the simulation for the backrun
            backrun_result = simulate_transaction_bundle(web3, [tx], block_number, block_time)
            
            # Update state management with backrun result
            if backrun_result:
                update_block_state(web3, backrun_result)
                # Log backrun simulation status in SQLite
                cursor.execute(
                    "INSERT OR REPLACE INTO processed_transactions (tx_hash, block_number, status) VALUES (?, ?, ?)",
                    (tx['hash'], block_number, "backrun_simulated")
                )
                shared_processed_transactions.append(tx['hash'])  # Add to shared list to prevent reprocessing
            else:
                log(f"Failed to simulate backrun for transaction {tx['hash']}")
        
        except Exception as e:
            log_error(f"Error during backrun simulation for transaction {tx['hash']}: {e}")

    # Use multiprocessing to parallelize simulations across processes
    if use_multiprocessing:
        with Pool(processes=max_processes) as pool:
            pool.map(process_transaction, transactions)
    else:
        # Fallback to threading if multiprocessing is not enabled
        threads = []
        for tx in transactions:
            thread = threading.Thread(target=process_transaction, args=(tx,))
            thread.start()
            threads.append(thread)
        for thread in threads:
            thread.join()

    # Batch commit all database changes
    try:
        conn.commit()
    except sqlite3.Error as e:
        log_error(f"Error committing batched transactions: {e}")
    
    # Serialize shared processed transactions with MessagePack for efficiency
    try:
        processed_transactions_path = os.path.join(config['data_storage']['data_directory'], "processed_transactions.msgpack")
        with open(processed_transactions_path, 'wb') as f:
            msgpack.pack(list(shared_processed_transactions), f)
        log(f"Stored processed transactions to {processed_transactions_path} using MessagePack.")
    except Exception as e:
        log_error(f"Error saving processed transactions with MessagePack: {e}")

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
        state_diff = result.get('stateDiff', {})
        tx_hash = result.get('transactionHash')

        if state_diff:
            # Store state_diff in the processed_bundles table if needed for future state analysis
            cursor.execute("INSERT OR REPLACE INTO processed_bundles (bundle_id, block_number, status, processed_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                            (tx_hash, result.get('blockNumber'), "success"))
            conn.commit()
            log(f"[INFO] Updated state for transaction {tx_hash} in block {result.get('blockNumber')}. StateDiff stored in database.")
        else:
            log(f"[WARNING] No stateDiff available for transaction {tx_hash}. Skipping state update.")

    conn.close()

def verify_transaction_inclusion(web3, block_number, transaction_hash):
    """
    Verify that a transaction is included in a given block.
    :param web3: Web3 instance connected to the RPC node
    :param block_number: Block number to check
    :param transaction_hash: Hash of the transaction to verify
    :return: Boolean indicating if the transaction is included
    """
    block = web3.eth.get_block(block_number, full_transactions=True)
    return any(tx['hash'] == transaction_hash for tx in block.transactions)
