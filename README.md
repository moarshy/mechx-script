# MechX Call Script

This repository contains scripts for interacting with MechX services. It includes scripts for sending requests to Mech services and monitoring responses.

## Getting Started

Follow these steps to run the scripts in this repository:

### Prerequisites

- Python 3.10 or higher
- pip

### Installation

1. **Clone the repository**

```bash
   git clone https://github.com/moarshy/mechx-call-script.git
   cd mechx-call-script
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

### Running the Scripts
0. **Private Key**
In a `ethereum_privat_key.txt` have your private key to a wallet with funds in the same directory as the `main.py` file.

1. **Execute the Request Script**
Open the `run_script.ipynb` Jupyter notebook in your preferred environment (e.g., JupyterLab, VSCode, or classic Jupyter Notebook). Navigate to the `run_script.ipynb` notebook and execute the cells to send requests to the MechX services.

2. **Monitor Responses**
To monitor the responses to the requests sent, open and run the check_response.ipynb notebook in a similar manner as described above. This notebook contains scripts to check and display the responses from MechX services.
