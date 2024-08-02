# MEVGuard - Open Source MEV Blocker Verification Tool

This project is an open-source tool designed to verify MEV Blocker transactions, maximize user refunds, and flag rule violations. The project is structured around three main milestones, and this document provides detailed instructions for setting up and running the data gathering process (Milestone 1).

## Table of Contents

- [Project Overview](#project-overview)
- [Technologies Used](#technologies-used)
- [Setup and Installation](#setup-and-installation)
- [Configuration](#configuration)
- [Running the Data Gathering Script](#running-the-data-gathering-script)
- [File Structure](#file-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Project Overview

The objective of this project is to develop a standalone service that confirms the maximization of user refunds for each included MEV Blocker transaction and flags rule violations. The project utilizes a combination of blockchain data and analytics to achieve these goals.

## Technologies Used

- **Python**: The main programming language used for the project.
- **web3.py**: A Python library to interact with the Ethereum blockchain.
- **Dune Analytics**: Used to query and analyze blockchain data.
- **Docker**: Containerization for easy deployment (to be implemented in future milestones).
- **Telegram & Slack**: Used for alerts and logging (to be implemented in future milestones).

## Setup and Installation

Follow these steps to set up the project environment and dependencies:

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/MEVGuard-Open-Source-MEV-Blocker-Verification-Tool.git
cd MEVGuard-Open-Source-MEV-Blocker-Verification-Tool
```

### 2. Create a Virtual Environment

Create and activate a virtual environment to manage dependencies:

```bash
# Create a virtual environment named 'venv'
python -m venv venv

# Activate the virtual environment (Windows)
.\venv\Scripts\activate

# Activate the virtual environment (macOS/Linux)
source venv/bin/activate
```

### 3. Install Required Packages

Install the necessary Python packages listed in the `requirements.txt` file:

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the root directory with the following variables:

```
RPC_NODE_URL=https://your-ethereum-node-url
DUNE_API_KEY=your-dune-api-key
DUNE_QUERY_ID=your-dune-query-id
```

- **RPC_NODE_URL**: URL of your Ethereum node provider (e.g., Infura, Alchemy).
- **DUNE_API_KEY**: API key for accessing Dune Analytics.
- **DUNE_QUERY_ID**: The ID of the Dune query used to fetch MEV Blocker transactions.

### 5. Configuration

Additional configurations can be added in the `config/config.yaml` file if necessary.

## Running the Data Gathering Script

To fetch and store block and bundle data, run the following command:

```bash
python src/data_gathering.py
```

This script will:
- Fetch the latest block data using web3.py.
- Execute a Dune Analytics query to identify potential MEV Blocker transactions.
- Store the fetched data in the `data/` directory as JSON files.

## File Structure

Below is the structure of the project directory:

```
MEVGuard-Open-Source-MEV-Blocker-Verification-Tool/
│
├── src/
│   ├── data_gathering.py         # Script for data gathering
│   ├── utils.py                  # Utility functions (logging, etc.)
│
├── data/                         # Directory where fetched data is stored
│
├── config/
│   └── config.yaml               # Configuration file
│
├── .gitignore                    # Git ignore file
├── requirements.txt              # Python dependencies
└── README.md                     # Project documentation
```

## Troubleshooting

### Common Issues

- **Virtual Environment Issues**: Ensure the virtual environment is activated before installing dependencies or running scripts.
- **API Key Errors**: Double-check that your API keys in the `.env` file are correct.
- **Network Errors**: Ensure you have a stable internet connection and valid RPC node URL.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue if you have any suggestions or improvements.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
```
