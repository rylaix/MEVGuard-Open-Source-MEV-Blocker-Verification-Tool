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

def simulate_bundles(selected_bundles, web3, block_number, block_time):
    """
    Simulate the selected bundles and calculate the refund.
    :param selected_bundles: List of selected bundles
    :param web3: Web3 instance for RPC communication
    :param block_number: Block number for the simulation
    :param block_time: Timestamp of the block
    :return: List of simulation results with refunds
    """
    simulation_results = []
    
    for bundle in selected_bundles:
        log(f"Simulating bundle ID: {bundle.get('id', 'unknown')} with {len(bundle.get('transactions', []))} transactions.")
        
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
            # Simulate the transaction bundle and pass block_time
            results = simulate_transaction_bundle(web3, transactions, block_number, block_time)
            
            if results:
                # Store the simulation results including refunds and state differences
                refund = calculate_refund(results)
                simulation_results.append({
                    'bundle': bundle,
                    'result': results,
                    'refund': refund
                })
                log(f"Calculated Refund for bundle: {refund} ETH")
                
                # Update blockchain state after simulation
                update_block_state(web3, results)
                log(f"Updated state for block {block_number}.")
    
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

