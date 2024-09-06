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

def simulate_bundles(selected_bundles, web3, block_number):
    """
    Simulate the selected bundles and calculate the refund.
    :param selected_bundles: List of selected bundles
    :param web3: Web3 instance for RPC communication
    :param block_number: Block number for the simulation
    :return: List of simulation results with refunds
    """
    simulation_results = []
    
    for bundle in selected_bundles:
        log(f"Simulating bundle: {bundle}")
        
        # Check if 'transactions' is a string and convert it to a list of dictionaries
        if isinstance(bundle['transactions'], str):
            try:
                # Parse the string to JSON
                bundle['transactions'] = json.loads(bundle['transactions'])
            except json.JSONDecodeError as e:
                log(f"Error decoding transactions for bundle: {bundle}. Error: {e}")
                continue  # Skip this bundle if parsing fails

        # Now process the transactions as a list of dictionaries
        transactions = [tx['hash'] for tx in bundle['transactions'] if 'hash' in tx]
        
        if transactions:
            # Simulate the transaction bundle
            results = simulate_transaction_bundle(web3, transactions, block_number)
            
            if results:
                # Store the simulation results including refunds and state differences
                simulation_results.append({
                    'bundle': bundle,
                    'result': results,
                    'refund': calculate_refund(results)
                })
    
    return simulation_results

def calculate_refund(simulation_result):
    """
    Calculate the refund based on the simulation results.
    This is a placeholder - the actual logic would depend on the results returned from `trace_callMany`.
    :param simulation_result: The result from the simulation
    :return: Calculated refund amount
    """
    # Assuming the refund is a sum of some values in the stateDiff (simplified)
    refund = sum(tx['value'] for tx in simulation_result if 'value' in tx)
    return refund

def simulate_optimal_bundle_combinations(bundles, web3, block_number):
    """
    Simulate all permutations of the bundles to check for violations in the optimal bundle merging rule.
    :param bundles: List of all potential bundles
    :param web3: Web3 instance for RPC communication
    :param block_number: The block number to simulate
    :return: Optimal bundle combination and simulation results
    """
    # Generate all possible permutations of bundles
    all_combinations = itertools.permutations(bundles)
    optimal_combination = None
    highest_refund = 0

    for combination in all_combinations:
        transactions = [tx['hash'] for bundle in combination for tx in bundle['transactions']]
        results = simulate_transaction_bundle(web3, transactions, block_number)

        if results:
            refund = calculate_refund(results)
            if refund > highest_refund:
                highest_refund = refund
                optimal_combination = combination

    return optimal_combination, highest_refund

def detect_violation(optimal_combination, actual_combination, highest_refund, actual_refund):
    """
    Compare the optimal combination with the actual one and check if a violation occurred.
    :param optimal_combination: The optimal combination of bundles
    :param actual_combination: The actual combination of bundles
    :param highest_refund: The highest possible refund
    :param actual_refund: The actual refund received
    :return: Boolean indicating whether a violation occurred
    """
    if highest_refund > actual_refund:
        return True, highest_refund - actual_refund  # Return violation and difference
    return False, 0

def store_simulation_results(simulation_results, output_file):
    """
    Store the simulation results in a specified file.
    :param simulation_results: The results from the simulation
    :param output_file: The file where the results should be stored
    """
    with open(output_file, 'w') as f:
        json.dump(simulation_results, f, indent=4)
