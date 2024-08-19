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

- **Python**: The main programming language used for the project. (Python 3.10.10 used)
- **web3.py**: A Python library to interact with the Ethereum blockchain.
- **Dune Analytics**: Used to query and analyze blockchain data.
- **Docker**: Containerization for easy deployment (to be implemented in future milestones).
- **Telegram & Slack**: Used for alerts and logging (to be implemented in future milestones).
- **C Extensions**: Used for optimizing mathematical computations. (basically a placeholder at this stage, included for future development)
- **Multiprocessing**: Utilized to leverage CPU cores for parallel data processing.

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

### 4. Compile C Extensions

Compile the C extensions used for optimizing performance:

```bash
# Windows
cd c_extension
python setup.py build_ext --inplace

# macOS/Linux
cd c_extension
python3 setup.py build_ext --inplace
```

### 5. Configure Environment Variables

Create a `.env` file in the root directory with the following variables:

```
RPC_NODE_URL=https://your-ethereum-node-url
DUNE_API_KEY=your-dune-api-key
```

- **RPC_NODE_URL**: URL of your Ethereum node provider (e.g., Infura, Alchemy).
- **DUNE_API_KEY**: API key for accessing Dune Analytics.

### 6. Configuration

Additional configurations are mentioned in the `config/config.yaml` file.

## Running the Data Gathering Script

To fetch and store block and bundle data, run the following command:

```bash
python src/data_gathering.py
```

This script will:
- Fetch the latest block data using web3.py.
- Execute a Dune Analytics query to identify potential MEV Blocker transactions.
- Utilize multiprocessing to process data efficiently.
- Store the fetched data in the `data/` directory as JSON files.

## File Structure

Below is the structure of the project directory:

```
MEVGuard-Open-Source-MEV-Blocker-Verification-Tool/
│
├── src/
│   ├── __init__.py                         # Identification of folder so python can see it
│   ├── data_gathering.py                   # Script for data gathering
│   └── utils.py                            # Utility functions (logging, etc.)
│
├── c_extension/                            # Directory for C extension code
│   ├── c_extension.c                       # C extension for optimized calculations
│   └── setup.py                            # Setup script for building C extensions
│
├── data/                                   # Directory where fetched data is stored
│   └── __init__.py                         # Identification of folder so python can see it
│
├── logs/                                   # Default dir for logs
│
├── queries/                                # Directory with all queries used
│   ├── fetch_backruns.sql                  # Fetch Mevblocker backruns
│   └── fetch_remaining_transactions.sql    # Fetch data outside of MEV
│
├── config/
│   └── config.yaml                         # Configuration file
│
├── .gitignore                              # Git ignore file
├── requirements.txt                        # Python dependencies
├── .env                                    # Crucial to handle Keys 
└── README.md                               # Project documentation
```

## Troubleshooting

### Common Issues

- **Virtual Environment Issues**: Ensure the virtual environment is activated before installing dependencies or running scripts.
- **API Key Errors**: Double-check that your API keys in the `.env` file are correct.
- **Network Errors**: Ensure you have a stable internet connection and valid RPC node URL.
- **C Extension Compilation**: Ensure you have the necessary build tools installed for compiling C extensions.
