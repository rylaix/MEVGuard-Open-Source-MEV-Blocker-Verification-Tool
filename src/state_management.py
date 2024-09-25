from web3 import Web3
from dotenv import load_dotenv
from utils import log
import os
import time
import requests
import yaml

config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
with open(config_path, 'r') as file:
    config = yaml.safe_load(file)

# Load rate limit settings from config.yaml
calls_per_minute = config['rate_limit_handling'].get('calls_per_minute', 60)
call_interval = 60 / calls_per_minute  # Time interval between each call in seconds

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
    last_call_time = 0  # Track the time of the last RPC call
    call_interval = 60 / 60  # Limit to one call per second (adjust according to your rate limit)
    
    for tx in transactions:
        # Ensure we have all necessary fields
        trace_calls.append({
            'from': tx['from'],
            'to': tx['to'],
            'gas': tx.get('gas', None),
            'gasPrice': tx.get('gas_price', None),
            'maxFeePerGas': tx.get('max_fee_per_gas', None),
            'maxPriorityFeePerGas': tx.get('max_priority_fee_per_gas', None),
            'value': tx.get('value', 0),
            'data': tx.get('calldata', None),
            'nonce': tx.get('nonce', None),
            'chainId': tx.get('chainId', 1),
            'accessList': tx.get('access_list', None)
        })

    for attempt in range(retries):
        try:
            # Rate limit by waiting between requests
            time_since_last_call = time.time() - last_call_time
            if time_since_last_call < call_interval:
                time.sleep(call_interval - time_since_last_call)
            
            # Make the raw RPC call for trace_callMany
            response = web3.provider.make_request("trace_callMany", [trace_calls, "stateDiff"])
            last_call_time = time.time()  # Update last call time

            # Check for errors in the response
            if response.get('error'):
                log(f"Error in trace_callMany: {response['error']}")
                return None
            
            # Simulate backruns and update the state after each simulation
            simulate_backruns_and_update_state(web3, transactions, block_number, block_time)
            
            return response.get('result')
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Too Many Requests
                log(f"429 Error: Too Many Requests. Retrying in {backoff_factor ** attempt} seconds...")
                time.sleep(backoff_factor ** attempt)
            else:
                raise e

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
    
    log(f"Simulating backruns for block {block_number} at timestamp {block_time}...")
    
    for tx in transactions:
        # Identify and process backruns (transactions at p+1)
        log(f"Simulating backrun for transaction {tx['hash']} at position p+1")
        
        # Perform the simulation for the backrun
        backrun_result = simulate_transaction_bundle(web3, [tx], block_number, block_time)
        
        # Update state management with backrun result
        if backrun_result:
            update_block_state(web3, backrun_result)
        else:
            log(f"Failed to simulate backrun for transaction {tx['hash']}")

def update_block_state(web3, transaction_result):
    """
    Update the blockchain state after a successful transaction simulation.
    :param web3: Web3 instance connected to the RPC node
    :param transaction_result: Result of the simulated transaction
    :return: Updated block state
    """
    state_diff = transaction_result.get('stateDiff', {})
    return state_diff

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
