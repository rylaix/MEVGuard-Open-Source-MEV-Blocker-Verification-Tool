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
- [Devcontainer Setup](#devcontainer-setup)
  - [Setting Up GitHub for Git in Devcontainer](#setting-up-github-for-git-in-devcontainer)
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

Rename a `.env.example` file to `.env` in the root directory with the following variables:

```
RPC_NODE_URL=https://your-ethereum-node-url
DUNE_API_KEY=your-dune-api-key
```

- **RPC_NODE_URL**: URL of your Ethereum node provider (e.g., Infura, Alchemy).
- **DUNE_API_KEY**: API key for accessing Dune Analytics.

### 6. Configuration

Additional configurations are mentioned in the `config/config.yaml` file.

To setup query, create a dune query with contents from `fetch_backruns.sql". Be careful, all vars in dune must be set via button with brackets
(sometimes Dune just ignores vars if they're inserted manually). Then, take Query ID and place it to a `all_mev_blocker_bundle_per_block` in `config.yaml`

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

## Devcontainer Setup

The project is configured to run smoothly in a **devcontainer** within Visual Studio Code (VS Code). This setup allows you to easily work within an isolated environment without worrying about dependency installation or system configuration issues.

### Prerequisites

Before using the devcontainer, ensure the following prerequisites are met:
1. **Docker** is installed and running on your machine.
2. **Visual Studio Code** is installed.
3. Install the **Remote Development Extension Pack** in VS Code, which includes:
   - Remote - Containers
   - Remote - SSH
   - Remote - WSL (optional, if you're using Windows with WSL)

You can find the Remote Development Extension Pack on the [VS Code marketplace](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.vscode-remote-extensionpack).

### Steps to Use the Devcontainer

## **1. Open the Project in VS Code**

**Open the folder in VS Code**:

```bash
code .
```

## **2. Reopen in Container**

Once the project is open in VS Code, you'll be prompted to reopen the project in a container. Click **Reopen in Container**.

VS Code will start building the container image as specified in the `Dockerfile` and `devcontainer.json`. This process may take a few minutes to complete.

## **3. Activate the Virtual Environment**

After the container is built and you're inside the VS Code environment, you need to activate the Python virtual environment:

Open the integrated terminal in VS Code and run:

```bash
source /workspace/.venv/bin/activate
```

Once activated, you're ready to start working on the project.

## Setting Up GitHub for Git in Devcontainer
To ensure Git works seamlessly in the development container, configure GitHub with SSH authentication:

Step 1: Generate SSH Key (If Not Already Generated)
Generate a new SSH key on your host machine:
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```


Step 2: Add the SSH Key to GitHub
Copy your public key:
```
cat ~/.ssh/id_ed25519.pub
```

Go to Settings > SSH and GPG Keys in GitHub.
Add a new SSH key, paste the copied key, and save it.


Step 3: Test the SSH Connection
Test the connection:
```bash
ssh -T git@github.com
```


Step 4: Forward SSH Agent to Devcontainer
Start the SSH agent on your host machine:
```bash
eval $(ssh-agent)
ssh-add ~/.ssh/id_ed25519
```

Rebuild the devcontainer in VS Code:
Open the Command Palette (`Ctrl+Shift+P`).
Select `Remote-Containers: Rebuild Container`.
Now, Git operations inside the container will use your SSH credentials.