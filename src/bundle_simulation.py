import os
import yaml
import json
import itertools
import sqlite3
import time
from utils import setup_logging, log
from db.db_utils import connect_to_database
from state_management import simulate_transaction_bundle, verify_transaction_inclusion, update_block_state

from db.database_initializer import initialize_or_verify_database
import threading
from state_management import has_sufficient_balance

# Initialize the database tables before any further operations
initialize_or_verify_database()

# Base directory for consistent path handling
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

config_path = os.path.join(BASE_DIR, 'config', 'config.yaml')
with open(config_path, 'r') as file:
    config = yaml.safe_load(file)

logs_dir = config['data_storage']['logs_directory']
log_filename = config['data_storage']['log_filename']
hardcoded_log_filename = "simulation_timings.log"
log_file_path = os.path.join(logs_dir, hardcoded_log_filename)

def greedy_bundle_selection(bundles, max_selected_bundles):
    """
    Apply a greedy algorithm to select the best bundles based on refund.
    :param bundles: List of bundles fetched from Dune
    :param max_selected_bundles: Maximum number of bundles to select
    :return: List of selected bundles
    """
    log(f"Greedy selection: Received {len(bundles)} bundles to select from")
    if not bundles:
        log("No bundles available for selection.")
        return []
    
    selected_bundles = sorted(bundles, key=lambda x: x.get('refund', 0), reverse=True)

    # Limit the number of selected bundles
    return selected_bundles[:max_selected_bundles]

def simulate_bundles(selected_bundles, web3, block_number, block_time, bundle_data_folder='data'):
    """
    Simulate the selected bundles and calculate the refund, while measuring time for local operations and remote server responses.
    :param selected_bundles: List of selected bundles
    :param web3: Web3 instance for RPC communication
    :param block_number: Block number for the simulation
    :param block_time: Timestamp of the block
    :param bundle_data_folder: Folder where bundle data files are stored
    :return: List of simulation results with refunds
    """
    # Initialize logging for simulation timings
    logs_dir = config['data_storage']['logs_directory']
    hardcoded_log_filename = "simulation_timings.log"
    log_file_path = os.path.join(logs_dir, hardcoded_log_filename)

    # Create log file directory if it doesn't exist
    os.makedirs(logs_dir, exist_ok=True)

    conn = connect_to_database()
    conn.execute('PRAGMA journal_mode=WAL;')  # Enable Write-Ahead Logging to reduce lock contention
    cursor = conn.cursor()

    simulation_results = []
    processed_transactions = set()  # Keep track of already processed transactions
    processed_bundles = set()  # Track processed bundles to avoid infinite loops

    # Load bundles from the data folder to ensure proper tracking of bundle IDs/names
    bundle_file = os.path.join(BASE_DIR, bundle_data_folder, f"bundles_{block_number}.json")
    try:
        with open(bundle_file, 'r') as file:
            loaded_bundles = json.load(file)
    except Exception as e:
        log(f"[ERROR] Error loading bundles from {bundle_file}: {e}")
        return simulation_results

    log(f"[INFO] Loaded {len(loaded_bundles)} bundles from file {bundle_file}.")

    for bundle_index, bundle in enumerate(loaded_bundles):
        bundle_id = bundle.get('id') or f'bundle_{bundle_index}'

        log(f"[DEBUG] Processing bundle ID: {bundle_id}")

        # Skip already processed bundles
        cursor.execute("SELECT status FROM processed_bundles WHERE bundle_id=? AND block_number=?", (bundle_id, block_number))
        bundle_status = cursor.fetchone()
        if bundle_status is not None and bundle_status[0] == 'simulated':
            log(f"[DEBUG] Skipping already processed bundle ID: {bundle_id}.")
            continue

        processed_bundles.add(bundle_id)

        # Get transactions from bundle
        transactions = bundle.get('transactions', [])
        if not transactions:
            log(f"[INFO] No transactions in bundle {bundle_id}, skipping.")
            continue

        any_new_transactions = False

        # Check if the entire bundle has sufficient balance before simulating transactions
        if not has_sufficient_balance({'transactions': transactions}, web3):
            log(f"[INFO] Bundle {bundle_id} has insufficient balance for one or more transactions. Skipping bundle.")
            # Mark all transactions in this bundle as skipped due to insufficient balance
            for tx in transactions:
                tx_hash = tx.get('hash', 'unknown')
                cursor.execute("INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status) VALUES (?, ?, ?, ?)",
                               (tx_hash, bundle_id, block_number, "insufficient_balance"))
            conn.commit()
            continue

        for tx in transactions:
            tx_hash = tx.get('hash')
            if not tx_hash:
                log(f"[WARNING] Skipping transaction due to missing hash: {tx}")
                continue

            log(f"[DEBUG] Checking transaction hash: {tx_hash}")

            # Skip already processed transactions
            cursor.execute("SELECT status FROM processed_transactions WHERE tx_hash=?", (tx_hash,))
            tx_status = cursor.fetchone()
            if tx_status is not None and tx_status[0] == 'simulated':
                log(f"[DEBUG] Skipping already processed transaction: {tx_hash}")
                continue

            processed_transactions.add(tx_hash)

            # Measure local time for balance checking
            local_start_time = time.time()

            # Check balance of the 'from' address
            sufficient_balance = True
            try:
                from_address = tx.get('from')
                if not from_address:
                    log(f"[WARNING] Skipping transaction {tx_hash} due to missing 'from' address.")
                    continue

                # Fetch the balance of the sender's address
                balance = web3.eth.get_balance(from_address, block_identifier=block_number)

                # Measure time taken to get balance from server
                server_response_time = time.time() - local_start_time
                local_time_end = time.time()
                local_operation_time = local_time_end - local_start_time

                # Log the time measurements
                with open(log_file_path, 'a') as timing_log:
                    timing_log.write(f"Local operation time for balance check (tx {tx_hash}): {local_operation_time} seconds\n")
                    timing_log.write(f"Server response time for balance check (tx {tx_hash}): {server_response_time} seconds\n")

                log(f"[DEBUG] Raw balance for address {from_address} at block {block_number}: {balance} (type: {type(balance)})")

                # Handle None balance case and ensure it's an integer
                if balance is None or not isinstance(balance, int):
                    log(f"[ERROR] Invalid balance for address {from_address}, skipping transaction {tx_hash}.")
                    sufficient_balance = False
                    continue

                # Convert necessary transaction parameters to integers
                try:
                    gas_price = int(tx.get('maxFeePerGas', 0))
                    gas_limit = int(tx.get('gasLimit', 0))
                    value = int(tx.get('value', 0))
                except (ValueError, TypeError) as e:
                    log(f"[ERROR] Error converting transaction parameters for {tx_hash}: {e}")
                    continue

                # Calculate the required balance for this transaction
                required_balance = gas_price * gas_limit + value
                log(f"[DEBUG] Required balance for transaction {tx_hash}: {required_balance} Wei")

                if balance < required_balance:
                    log(f"[INFO] Skipping transaction {tx_hash} due to insufficient balance: {balance} < {required_balance}")
                    sufficient_balance = False

            except Exception as e:
                log(f"[ERROR] Error checking balance for transaction {tx_hash}: {e}.")
                sufficient_balance = False

            if not sufficient_balance:
                log(f"[INFO] Skipping transaction ID: {tx_hash} due to insufficient balance.")
                # Insert transaction record with insufficient balance status
                cursor.execute("INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status) VALUES (?, ?, ?, ?)",
                               (tx_hash, bundle_id, block_number, "insufficient_balance"))
                conn.commit()
                continue

            # Simulate the transaction bundle
            try:
                local_simulation_start = time.time()
                log(f"[DEBUG] Simulating transaction bundle for transaction {tx_hash}")
                results = simulate_transaction_bundle(web3, [tx], block_number, block_time)
                local_simulation_end = time.time()

                if results is None:
                    log(f"[WARNING] No results returned for transaction {tx_hash}. Simulation might have failed or returned empty.")
                    continue

                # Measure and log simulation time
                simulation_time = local_simulation_end - local_simulation_start
                with open(log_file_path, 'a') as timing_log:
                    timing_log.write(f"Local simulation time for transaction {tx_hash}: {simulation_time} seconds\n")

            except Exception as e:
                log(f"[ERROR] Error simulating transaction bundle for transaction {tx_hash}: {e}")
                continue

            if results:
                try:
                    refund = calculate_refund(results)
                    simulation_results.append({
                        'bundle': bundle,
                        'transaction': tx,
                        'result': results,
                        'refund': refund
                    })
                    log(f"[INFO] Calculated Refund for transaction {tx_hash} = {refund} ETH")

                    # Save successful simulation to the output directory
                    simulation_output_directory = config['data_storage']['simulation_output_directory']
                    os.makedirs(simulation_output_directory, exist_ok=True)
                    output_file_path = os.path.join(simulation_output_directory, f"simulation_results_{block_number}.json")
                    with open(output_file_path, 'w') as output_file:
                        json.dump(simulation_results, output_file, indent=4)
                    log(f"[INFO] Successfully saved simulation results for transaction {tx_hash} to {output_file_path}")

                    # Insert transaction record into SQLite
                    cursor.execute("INSERT OR REPLACE INTO processed_transactions (tx_hash, bundle_id, block_number, status) VALUES (?, ?, ?, ?)",
                                   (tx_hash, bundle_id, block_number, "simulated"))
                    any_new_transactions = True
                    conn.commit()

                except Exception as e:
                    log(f"[ERROR] Error calculating refund for transaction {tx_hash}: {e}")
                    continue

                # Update blockchain state after simulation
                try:
                    update_block_state(web3, results)
                    log(f"[INFO] Updated state for transaction {tx_hash} in block {block_number}.")
                except Exception as e:
                    log(f"[ERROR] Error updating state for transaction {tx_hash}: {e}")
                    continue

        # Update bundle status in SQLite if new transactions were processed
        if any_new_transactions:
            try:
                cursor.execute("INSERT OR REPLACE INTO processed_bundles (bundle_id, block_number, status) VALUES (?, ?, ?)",
                               (bundle_id, block_number, "simulated"))
                conn.commit()
            except sqlite3.OperationalError as e:
                log(f"[ERROR] Database locked while updating bundle status for bundle {bundle_id}: {e}")
                continue

    log(f"[INFO] Finished simulating bundles for block {block_number}")
    conn.close()
    return simulation_results




def calculate_refund(simulation_result):
    """
    Calculate the refund based on the simulation results.
    This function calculates 90% of the total backrun value, including gas savings, builder rewards, 
    priority fees, and any other relevant incentives according to the MEVBlocker rules.
    
    :param simulation_result: The result from the simulation
    :return: Calculated refund amount (90% of the backrun value)
    """
    # Initialize total backrun value
    total_backrun_value = 0

    for tx in simulation_result:
        # Calculate refund from gas used and effective gas price
        if 'gas_used' in tx and 'effective_gas_price' in tx:
            gas_used = tx['gas_used']
            gas_price = tx['effective_gas_price']
            gas_refund = gas_used * gas_price
            total_backrun_value += gas_refund
            log(f"[DEBUG] Gas Refund for tx {tx['hash']}: {gas_refund} Wei")

        # Include builder rewards if specified
        if 'builder_reward' in tx:
            builder_reward = tx['builder_reward']
            total_backrun_value += builder_reward
            log(f"[DEBUG] Builder Reward for tx {tx['hash']}: {builder_reward} Wei")

        # Include priority fees (EIP-1559) if relevant
        if 'priority_fee' in tx:
            priority_fee = tx['priority_fee']
            total_backrun_value += priority_fee
            log(f"[DEBUG] Priority Fee for tx {tx['hash']}: {priority_fee} Wei")

        # Consider slippage protection if applicable
        if 'slippage_protection' in tx:
            slippage_value = tx['slippage_protection']
            total_backrun_value += slippage_value
            log(f"[DEBUG] Slippage Protection for tx {tx['hash']}: {slippage_value} Wei")

    # Apply the 90% rebate rule
    refund = total_backrun_value * 0.9
    log(f"[INFO] Total Backrun Value: {total_backrun_value} Wei")
    log(f"[INFO] Refund (90% of Backrun Value): {refund} Wei")

    return refund



def simulate_optimal_bundle_combinations(bundles, web3, block_number):
    """
    Simulate all permutations of the bundles to check for violations in the optimal bundle merging rule.
    :param bundles: List of all potential bundles
    :param web3: Web3 instance for RPC communication
    :param block_number: The block number to simulate
    :return: Optimal bundle combination and simulation results
    """
    conn = connect_to_database()
    cursor = conn.cursor()

    optimal_combination = None
    highest_refund = 0

    # Generate all possible combinations of bundles
    for r in range(1, len(bundles) + 1):
        for combination in itertools.combinations(bundles, r):
            combination_ids = [bundle.get('id') for bundle in combination]
            
            # Skip combinations that have already been simulated
            cursor.execute("SELECT status FROM processed_bundles WHERE bundle_id IN ({seq}) AND block_number=?"
                           .format(seq=','.join(['?']*len(combination_ids))), (*combination_ids, block_number))
            statuses = cursor.fetchall()

            if statuses and all(status[0] == 'simulated' for status in statuses):
                log(f"[INFO] Skipping combination {combination_ids} as it is already simulated for block {block_number}.")
                continue

            transactions = [tx for bundle in combination for tx in bundle['transactions']]
            results = simulate_transaction_bundle(web3, transactions, block_number, block_time=None)

            if results:
                refund = calculate_refund(results)
                if refund > highest_refund:
                    highest_refund = refund
                    optimal_combination = combination

    log(f"Optimal Refund: {highest_refund} ETH with {len(optimal_combination)} bundles" if optimal_combination else "No optimal combination found.")
    conn.close()
    return optimal_combination, highest_refund


def detect_violation(optimal_combination, actual_combination, highest_refund, actual_refund):
    """
    Compare the optimal combination with the actual one and check if a violation occurred.
    If a violation is detected, log details such as missed rewards or backruns.
    
    :param optimal_combination: The optimal combination of bundles
    :param actual_combination: The actual combination of bundles
    :param highest_refund: The highest possible refund
    :param actual_refund: The actual refund received
    :return: Boolean indicating whether a violation occurred, and the amount of the violation
    """
    if highest_refund > actual_refund:
        violation_amount = highest_refund - actual_refund
        
        # Log details of the violation
        missed_bundles = [bundle for bundle in optimal_combination if bundle not in actual_combination]
        log(f"Violation detected! Optimal refund: {highest_refund} ETH, Actual refund: {actual_refund} ETH")
        log(f"Missed opportunities: {missed_bundles}. Difference: {violation_amount} ETH")
        
        return True, violation_amount

    log("No violation detected.")
    return False, 0


def store_simulation_results(simulation_results, output_file):
    """
    Store the simulation results in a specified file.
    :param simulation_results: The results from the simulation
    :param output_file: The file where the results should be stored
    """
    with open(output_file, 'w') as f:
        json.dump(simulation_results, f, indent=4)

