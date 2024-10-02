import os
import yaml
import json
import itertools
from utils import setup_logging, log
from state_management import simulate_transaction_bundle, verify_transaction_inclusion, update_block_state

config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
with open(config_path, 'r') as file:
    config = yaml.safe_load(file)

logs_dir = config['data_storage']['logs_directory']
log_filename = config['data_storage']['log_filename']

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
    Simulate the selected bundles and calculate the refund.
    :param selected_bundles: List of selected bundles
    :param web3: Web3 instance for RPC communication
    :param block_number: Block number for the simulation
    :param block_time: Timestamp of the block
    :param bundle_data_folder: Folder where bundle data files are stored
    :return: List of simulation results with refunds
    """
    simulation_results = []
    processed_transactions = set()  # Keep track of already processed transactions
    processed_bundles = set()  # Track processed bundles to avoid infinite loops

    # Load bundles from the data folder to ensure proper tracking of bundle IDs/names
    bundle_file = f"{bundle_data_folder}/bundles_{block_number}.json"
    try:
        with open(bundle_file, 'r') as file:
            loaded_bundles = json.load(file)
    except Exception as e:
        log(f"Error loading bundles from {bundle_file}: {e}")
        return simulation_results

    log(f"Loaded {len(loaded_bundles)} bundles from file {bundle_file}.")

    # Log the current state of loaded bundles
    log(f"State: processed_bundles: {processed_bundles}, processed_transactions: {processed_transactions}")

    # Map each bundle to its ID or name if available
    for bundle_index, bundle in enumerate(loaded_bundles):
        bundle_id = bundle.get('id') or f'bundle_{bundle_index}'

        # Log current bundle being processed
        log(f"Checking bundle ID: {bundle_id}")

        # Skip already processed bundles to prevent infinite loops
        if bundle_id in processed_bundles:
            log(f"Skipping already processed bundle ID: {bundle_id}.")
            continue

        log(f"Simulating bundle ID: {bundle_id} with {len(bundle.get('transactions', []))} transactions.")

        # Mark bundle as processed to avoid re-simulation
        processed_bundles.add(bundle_id)

        # Parse and verify the transactions list
        transactions = bundle.get('transactions', [])

        if not transactions:
            log(f"No transactions in bundle {bundle_id}, skipping.")
            continue

        # Track state to check if any new transactions were processed
        any_new_transactions = False

        for tx in transactions:
            tx_hash = tx['hash']
            
            # Log each transaction being processed
            log(f"Processing transaction {tx_hash} in bundle {bundle_id}.")

            if tx_hash in processed_transactions:
                log(f"Skipping already processed transaction: {tx_hash}.")
                continue

            # Mark transaction as processed
            processed_transactions.add(tx_hash)

            # Check balance of the 'from' address before simulating
            sufficient_balance = True
            try:
                from_address = tx['from']
                balance = web3.eth.get_balance(from_address, block_number)
                gas_price = int(tx.get('gasPrice', 0))
                gas_limit = int(tx.get('gasLimit', 0))
                value = int(tx.get('value', 0))
                required_balance = gas_price * gas_limit + value

                if balance < required_balance:
                    log(f"Skipping transaction {tx['hash']} due to insufficient balance: {balance} < {required_balance}")
                    sufficient_balance = False
            except Exception as e:
                log(f"Error checking balance for transaction {tx_hash}: {e}")
                sufficient_balance = False

            if not sufficient_balance:
                log(f"Skipping transaction ID: {tx_hash} due to insufficient balance.")
                continue

            # Simulate the transaction bundle and pass block_time
            results = simulate_transaction_bundle(web3, [tx], block_number, block_time)

            if results:
                refund = calculate_refund(results)
                simulation_results.append({
                    'bundle': bundle,
                    'transaction': tx,
                    'result': results,
                    'refund': refund
                })
                log(f"Calculated Refund for transaction: {tx_hash} = {refund} ETH")

                # Update blockchain state after simulation
                update_block_state(web3, results)
                log(f"Updated state for transaction {tx_hash} in block {block_number}.")
                any_new_transactions = True
            else:
                log(f"No results for transaction {tx_hash}, simulation skipped.")

        if not any_new_transactions:
            log(f"No new transactions processed in bundle {bundle_id}, moving to next.")
            continue

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
            log(f"Gas Refund for tx {tx['hash']}: {gas_refund} ETH")

        # Include builder rewards if specified
        if 'builder_reward' in tx:
            builder_reward = tx['builder_reward']
            total_backrun_value += builder_reward
            log(f"Builder Reward for tx {tx['hash']}: {builder_reward} ETH")

        # Include priority fees (EIP-1559) might be relevant
        if 'priority_fee' in tx:
            priority_fee = tx['priority_fee']
            total_backrun_value += priority_fee
            log(f"Priority Fee for tx {tx['hash']}: {priority_fee} ETH")

        # Consider slippage protection if applicable
        if 'slippage_protection' in tx:
            slippage_value = tx['slippage_protection']
            total_backrun_value += slippage_value
            log(f"Slippage Protection for tx {tx['hash']}: {slippage_value} ETH")

    # Apply the 90% rebate rule
    refund = total_backrun_value * 0.9
    log(f"Total Backrun Value: {total_backrun_value} ETH")
    log(f"Refund (90% of Backrun Value): {refund} ETH")

    return refund


def simulate_optimal_bundle_combinations(bundles, web3, block_number):
    """
    Simulate all permutations of the bundles to check for violations in the optimal bundle merging rule.
    This includes combinations of all backruns and checks whether they could have offered more value.

    :param bundles: List of all potential bundles
    :param web3: Web3 instance for RPC communication
    :param block_number: The block number to simulate
    :return: Optimal bundle combination and simulation results
    """
    optimal_combination = None
    highest_refund = 0

    # Generate all possible combinations of bundles
    for r in range(1, len(bundles) + 1):
        for combination in itertools.combinations(bundles, r):
            transactions = [tx['hash'] for bundle in combination for tx in bundle['transactions']]
            results = simulate_transaction_bundle(web3, transactions, block_number)

            if results:
                refund = calculate_refund(results)
                if refund > highest_refund:
                    highest_refund = refund
                    optimal_combination = combination

    log(f"Optimal Refund: {highest_refund} ETH with {len(optimal_combination)} bundles" if optimal_combination else "No optimal combination found.")
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

