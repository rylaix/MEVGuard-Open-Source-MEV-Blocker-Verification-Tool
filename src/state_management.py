from web3 import Web3
from dotenv import load_dotenv
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

def  simulate_transaction_bundle(web3, transactions, block_number, retries=3, backoff_factor=2):
    """
    Simulate the transactions in the given bundle using trace_callMany via raw RPC call.
    Includes retry logic for 429 errors and rate-limiting control.
    """
    trace_calls = [{'transaction': tx, 'stateOverride': {}, 'blockNumber': block_number} for tx in transactions]
    last_call_time = 0  # Track the time of the last RPC call

    for attempt in range(retries):
        try:
            # Implement rate limiting by waiting between requests
            time_since_last_call = time.time() - last_call_time
            if time_since_last_call < call_interval:
                time.sleep(call_interval - time_since_last_call)
            
            # Perform the request
            response = web3.provider.make_request("trace_callMany", [trace_calls, "stateDiff"])
            last_call_time = time.time()  # Update last call time

            # Handle response and check for errors
            if response.get('error'):
                print(f"Error in trace_callMany: {response['error']}")
                return None
            
            return response.get('result')
        
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Too Many Requests
                print(f"429 Error: Too Many Requests. Retrying in {backoff_factor ** attempt} seconds...")
                time.sleep(backoff_factor ** attempt)
            else:
                raise e
    return None

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
