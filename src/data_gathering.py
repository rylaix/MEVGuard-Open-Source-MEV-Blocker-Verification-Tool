import os
import json
from web3 import Web3
from web3.datastructures import AttributeDict
from dune_client.client import DuneClient
from dune_client.query import QueryBase
from dotenv import load_dotenv
from utils import log
import yaml

# Load environment variables
load_dotenv()

# Load additional config if needed
with open('config/config.yaml', 'r') as file:
    config = yaml.safe_load(file)

class DataGathering:
    def __init__(self):
        # Initialize Web3 with the provided RPC node URL
        self.web3 = Web3(Web3.HTTPProvider(os.getenv('RPC_NODE_URL')))
        
        # Initialize Dune API client with the provided API key
        self.dune_client = DuneClient(api_key=os.getenv('DUNE_API_KEY'))

    def fetch_block_contents(self, block_number):
        """Fetch the contents of a block given its number."""
        block = self.web3.eth.get_block(block_number, full_transactions=True)
        log(f"Fetched block {block_number} with {len(block['transactions'])} transactions.")
        return block

    def identify_mev_blocker_bundles(self, block):
        """Identify MEV Blocker bundles from Dune Analytics using the block data."""
        query_id = os.getenv('DUNE_QUERY_ID') or config['dune_query_id']

        # Create a QueryBase object for the query
        query = QueryBase(
            query_id=int(query_id),
            params=[]
        )

        # Execute the query
        execution_id = self.dune_client.execute_query(query)

        # Fetch the latest result from the executed query
        result = self.dune_client.get_latest_result(query)

        # Ensure the results are retrieved as a list of dictionaries
        bundles = result.get_rows()

        log(f"Identified {len(bundles)} MEV Blocker bundles.")
        return bundles

    def store_data(self, block, bundles):
        """Store the block and bundles data into the data directory."""
        
        # Helper function to convert AttributeDict to dictionary
        def convert_to_dict(obj):
            if isinstance(obj, AttributeDict):
                return {key: convert_to_dict(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_to_dict(item) for item in obj]
            elif isinstance(obj, bytes):
                return obj.hex()
            else:
                return obj

        # Convert block to dictionary
        block_dict = convert_to_dict(block)

        with open(f"data/block_{block['number']}.json", 'w') as f:
            json.dump(block_dict, f, indent=4)

        with open(f"data/bundles_{block['number']}.json", 'w') as f:
            json.dump(bundles, f, indent=4)

        log(f"Stored data for block {block['number']}")

if __name__ == "__main__":
    dg = DataGathering()
    latest_block_number = dg.web3.eth.block_number
    block = dg.fetch_block_contents(latest_block_number)
    bundles = dg.identify_mev_blocker_bundles(block)
    dg.store_data(block, bundles)
