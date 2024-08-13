import os
import json
import time
from web3 import Web3
from web3.datastructures import AttributeDict  # Import AttributeDict
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path, override=True)

# Initialize Web3
rpc_node_url = os.getenv('RPC_NODE_URL')  # Ensure this is set to your Infura or Alchemy RPC URL
web3 = Web3(Web3.HTTPProvider(rpc_node_url))

def convert_to_dict(obj):
    """Convert AttributeDict or bytes objects into serializable dictionaries."""
    if isinstance(obj, bytes):
        return obj.hex()
    elif isinstance(obj, AttributeDict):  # Specifically handle AttributeDict
        return {k: convert_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_to_dict(item) for item in obj]
    elif isinstance(obj, dict):
        return {k: convert_to_dict(v) for k, v in obj.items()}
    else:
        return obj

def fetch_block_and_transactions(block_number):
    """Fetch a block and its transactions."""
    block = web3.eth.get_block(block_number, full_transactions=True)
    block_data = convert_to_dict(block)
    transactions = block_data['transactions']  # Extract transactions

    return block_data, transactions

def store_data(block_data, transactions):
    """Store block and transaction data into JSON files."""
    block_number = block_data['number']
    
    with open(f"data/block_{block_number}.json", 'w') as f:
        json.dump(block_data, f, indent=4)

    with open(f"data/transactions_{block_number}.json", 'w') as f:
        json.dump(transactions, f, indent=4)

    print(f"Stored data for block {block_number}")

def main():
    # Ensure the data directory exists
    if not os.path.exists('data'):
        os.makedirs('data')

    # Define block range or specific blocks to process
    latest_block_number = web3.eth.block_number
    start_block_offset = 100  # How far back to start from the latest block
    num_blocks_to_process = 5  # Number of blocks to process

    # Calculate the range of blocks to fetch
    start_block = latest_block_number - start_block_offset
    end_block = start_block + num_blocks_to_process  # Correct the range limit

    block_numbers = range(start_block, end_block)

    for block_number in block_numbers:
        try:
            block_data, transactions = fetch_block_and_transactions(block_number)
            store_data(block_data, transactions)
            time.sleep(1)  # Add a delay between requests to avoid rate limits
        except Exception as e:
            print(f"Error processing block {block_number}: {e}")

    print("Finished processing blocks.")

if __name__ == "__main__":
    main()
