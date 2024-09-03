from web3 import Web3
from dotenv import load_dotenv
import os

def initialize_web3():
    """
    Initialize a Web3 instance using the RPC node URL from the .env file.
    """
    load_dotenv()
    rpc_node_url = os.getenv('RPC_NODE_URL')
    return Web3(Web3.HTTPProvider(rpc_node_url))

def simulate_transaction_bundle(web3, transactions, block_number):
    """
    Simulate the transactions in the given bundle using trace_callMany.
    :param web3: Web3 instance connected to the RPC node
    :param transactions: List of transactions to simulate
    :param block_number: Block number to simulate the transactions at
    :return: Results of the simulation
    """
    try:
        trace_calls = [{'transaction': tx, 'stateOverride': {}, 'blockNumber': block_number} for tx in transactions]
        results = web3.manager.request_blocking('trace_callMany', [trace_calls, 'stateDiff'])
        return results
    except Exception as e:
        print(f"Error during simulation: {e}")
        return None

def update_block_state(web3, transaction_result):
    """
    Update the blockchain state after a successful transaction simulation.
    :param web3: Web3 instance connected to the RPC node
    :param transaction_result: Result of the simulated transaction
    :return: Updated block state
    """
    # This is a simplified example, detailed state management would require tracking specific changes
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