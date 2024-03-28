import os
import uuid
import time
import json
import asyncio
import backoff
import shutil
import tempfile
import warnings
import requests
import websocket
from enum import Enum
from string import Template
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from aea.crypto.base import Crypto
from aea_ledger_ethereum import EthereumApi, EthereumCrypto
from web3 import Web3
from web3.contract import Contract as Web3Contract

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport

import multibase
import multicodec
from aea.helpers.cid import to_v1
from aea_cli_ipfs.ipfs_utils import IPFSTool


AGENT_REGISTRY_CONTRACT = "0xE49CB081e8d96920C38aA7AB90cb0294ab4Bc8EA"
MECHX_CHAIN_RPC = os.environ.get(
    "MECHX_CHAIN_RPC",
    "https://rpc.eu-central-2.gateway.fm/v4/gnosis/non-archival/mainnet",
)
LEDGER_CONFIG = {
    "address": MECHX_CHAIN_RPC,
    "chain_id": 100,
    "poa_chain": False,
    "default_gas_price_strategy": "eip1559",
    "is_gas_estimation_enabled": False,
}
PRIVATE_KEY_FILE_PATH = "ethereum_private_key.txt"

WSS_ENDPOINT = os.getenv(
    "WEBSOCKET_ENDPOINT",
    "wss://rpc.eu-central-2.gateway.fm/ws/v4/gnosis/non-archival/mainnet",
)
MANUAL_GAS_LIMIT = int(
    os.getenv(
        "MANUAL_GAS_LIMIT",
        "100_000",
    )
)
BLOCKSCOUT_API_URL = (
    "https://gnosis.blockscout.com/api/v2/smart-contracts/{contract_address}"
)
private_key_path = './ethereum_private_key.txt'

MAX_RETRIES = 3
WAIT_SLEEP = 3.0
TIMEOUT = 120.0
SUBGRAPH_TIMEOUT = 30.0

# Ignore a specific warning message
warnings.filterwarnings("ignore", "The log with transaction hash.*")


class ConfirmationType(Enum):
    """Verification type."""

    ON_CHAIN = "on-chain"
    OFF_CHAIN = "off-chain"
    WAIT_FOR_BOTH = "wait-for-both"


#############################################################################################################
################################## FOR REQUEST EVENTS #######################################################
#############################################################################################################
MECH_SUBGRAPH_URL = "https://api.studio.thegraph.com/query/57238/mech/version/latest"
AGENT_QUERY_TEMPLATE = Template(
    """{
    createMeches(where:{agentId:$agent_id}) {
        mech
    }
}
"""
)

@backoff.on_exception(backoff.expo, Exception, max_tries=MAX_RETRIES, giveup=lambda e: isinstance(e, ValueError))
async def query_agent_address(agent_id: int, timeout: Optional[float] = None) -> Optional[str]:
    """
    Query agent address from subgraph with retries on failure.

    :param agent_id: The ID of the agent.
    :param timeout: Timeout for the request.
    :return: The agent address if found, None otherwise.
    """
    try:
        client = Client(
            transport=AIOHTTPTransport(url=MECH_SUBGRAPH_URL),
            execute_timeout=timeout or SUBGRAPH_TIMEOUT,
        )
        response = await client.execute_async(
            document=gql(
                request_string=AGENT_QUERY_TEMPLATE.substitute({"agent_id": agent_id})
            )
        )
        mechs = response["createMeches"]
        if len(mechs) == 0:
            return None

        (record,) = mechs
        return record["mech"]
    except Exception as e:
        print(f"Error querying agent address: {e}")
        return None


def get_abi(contract_address: str) -> List:
    """Get contract abi"""
    abi_request_url = BLOCKSCOUT_API_URL.format(contract_address=contract_address)
    response = requests.get(abi_request_url).json()
    return response["abi"]


def get_contract(
    contract_address: str, abi: List, ledger_api: EthereumApi
) -> Web3Contract:
    """
    Returns a contract instance.

    :param contract_address: The address of the contract.
    :type contract_address: str
    :param abi: ABI Object
    :type abi: List
    :param ledger_api: The Ethereum API used for interacting with the ledger.
    :type ledger_api: EthereumApi
    :return: The contract instance.
    :rtype: Web3Contract
    """

    return ledger_api.get_contract_instance(
        {"abi": abi, "bytecode": "0x"}, contract_address
    )


def _tool_selector_prompt(available_tools: List[str]) -> str:
    """
    Tool selector prompt.

    :param available_tools: A list of available tools.
    :type available_tools: List[str]
    :return: The selected tool.
    :rtype: str
    """

    tool_col_len = max(map(len, available_tools))
    id_col_len = max(2, len(str(len(available_tools))))
    table_len = tool_col_len + id_col_len + 5

    separator = "|" + "-" * table_len + "|"
    print("Select prompting tool")

    def format_row(row: Tuple[Any, Any]) -> str:
        _row = list(map(str, row))
        row_str = "| "
        row_str += _row[0]
        row_str += " " * (id_col_len - len(_row[0]))
        row_str += " | "
        row_str += _row[1]
        row_str += " " * (tool_col_len - len(_row[1]))
        row_str += " |"
        return row_str

    while True:
        print(separator)
        print(format_row(("ID", "Tool")))
        print(separator)
        print("\n".join(map(format_row, enumerate(available_tools))))
        print(separator)
        try:
            tool_id = int(input("Tool ID > "))
            return available_tools[tool_id]
        except (ValueError, TypeError, IndexError):
            print("\nPlease enter valid tool ID.")


def verify_or_retrieve_tool(
    agent_id: int, ledger_api: EthereumApi, tool: Optional[str] = None
) -> str:
    """
    Checks if the tool is valid and for what agent.

    :param agent_id: The ID of the agent.
    :type agent_id: int
    :param ledger_api: The Ethereum API used for interacting with the ledger.
    :type ledger_api: EthereumApi
    :param tool: The tool to verify or retrieve (optional).
    :type tool: Optional[str]
    :return: The result of the verification or retrieval.
    :rtype: str
    """
    available_tools = fetch_tools(agent_id=agent_id, ledger_api=ledger_api)
    if tool is not None and tool not in available_tools:
        raise ValueError(
            f"Provided tool `{tool}` not in the list of available tools; Available tools={available_tools}"
        )
    if tool is not None:
        return tool
    return _tool_selector_prompt(available_tools=available_tools)


def fetch_tools(agent_id: int, ledger_api: EthereumApi) -> List[str]:
    """Fetch tools for specified agent ID."""
    mech_registry = get_contract(
        contract_address=AGENT_REGISTRY_CONTRACT,
        abi=get_abi(AGENT_REGISTRY_CONTRACT),
        ledger_api=ledger_api,
    )
    token_uri = mech_registry.functions.tokenURI(agent_id).call()
    response = requests.get(token_uri).json()
    return response["tools"]


def calculate_topic_id(event: Dict) -> str:
    """Caclulate topic ID"""
    text = event["name"]
    text += "("
    for inp in event["inputs"]:
        text += inp["type"]
        text += ","
    text = text[:-1]
    text += ")"
    return Web3.keccak(text=text).hex()


def get_event_signatures(abi: List) -> Tuple[str, str]:
    """Calculate `Request` and `Deliver` event topics"""
    request, deliver = "", ""
    for obj in abi:
        if obj["type"] != "event":
            continue
        if obj["name"] == "Deliver":
            deliver = calculate_topic_id(event=obj)
        if obj["name"] == "Request":
            request = calculate_topic_id(event=obj)
    return request, deliver


def register_event_handlers(
    wss: websocket.WebSocket,
    contract_address: str,
    crypto: Crypto,
    request_signature: str,
    deliver_signature: str,
) -> None:
    """
    Register event handlers.

    :param wss: The WebSocket connection object.
    :type wss: websocket.WebSocket
    :param contract_address: The address of the contract.
    :type contract_address: str
    :param crypto: The cryptographic object.
    :type crypto: Crypto
    :param request_signature: Topic signature for Request event
    :type request_signature: str
    :param deliver_signature: Topic signature for Deliver event
    :type deliver_signature: str
    """

    subscription_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_subscribe",
        "params": [
            "logs",
            {
                "address": contract_address,
                "topics": [
                    request_signature,
                    ["0x" + "0" * 24 + crypto.address[2:]],
                ],
            },
        ],
    }
    content = bytes(json.dumps(subscription_request), "utf-8")
    wss.send(content)

    # registration confirmation
    _ = wss.recv()
    subscription_deliver = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_subscribe",
        "params": [
            "logs",
            {"address": contract_address, "topics": [deliver_signature]},
        ],
    }
    content = bytes(json.dumps(subscription_deliver), "utf-8")
    wss.send(content)

    # registration confirmation
    _ = wss.recv()


def push_to_ipfs(file_path: str) -> Tuple[str, str]:
    """
    Push a file to IPFS.

    :param file_path: Path of the file to be pushed to IPFS.
    :type file_path: str

    :return: A tuple containing v1_file_hash and v1_file_hash_hex.
    :rtype: Tuple[str, str]
    """
    response = IPFSTool().client.add(
        file_path, pin=True, recursive=True, wrap_with_directory=False
    )
    v1_file_hash = to_v1(response["Hash"])
    cid_bytes = multibase.decode(v1_file_hash)
    multihash_bytes = multicodec.remove_prefix(cid_bytes)
    v1_file_hash_hex = "f01" + multihash_bytes.hex()
    return v1_file_hash, v1_file_hash_hex


def push_to_ipfs_with_retries(file_path: str, max_retries: int = MAX_RETRIES, timeout: float = TIMEOUT) -> Tuple[str, str]:
    """
    Push a file to IPFS with retries.

    :param file_path: Path of the file to be pushed to IPFS.
    :param max_retries: Maximum number of retries.
    :param timeout: Timeout for each IPFS operation in seconds.
    :return: A tuple containing v1_file_hash and v1_file_hash_hex.
    """
    attempt = 0
    start_time = time.time()
    while attempt < max_retries:
        try:
            if time.time() - start_time > timeout:
                print("Timeout reached while trying to push to IPFS.")
                return None, None
            return push_to_ipfs(file_path)
        except Exception as e:
            print(f"Attempt {attempt + 1} failed with error: {e}")
            attempt += 1
            time.sleep(2)  # Sleep between retries
    print("Max retries reached. Failed to push to IPFS.")
    return None, None


def push_metadata_to_ipfs(prompt: str, tool: str) -> Tuple[str, str]:
    """
    Pushes metadata object to IPFS.

    :param prompt: Prompt string.
    :type prompt: str
    :param tool: Tool string.
    :type tool: str
    :return: Tuple containing the IPFS hash and truncated IPFS hash.
    :rtype: Tuple[str, str]
    """
    metadata = {"prompt": prompt, "tool": tool, "nonce": str(uuid.uuid4())}
    dirpath = tempfile.mkdtemp()
    file_name = dirpath + "metadata.json"
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(metadata, f)
    _, v1_file_hash_hex = push_to_ipfs(file_name)
    shutil.rmtree(dirpath)
    return "0x" + v1_file_hash_hex[9:], v1_file_hash_hex


def send_request(  # pylint: disable=too-many-arguments,too-many-locals
    crypto: EthereumCrypto,
    ledger_api: EthereumApi,
    mech_contract: Web3Contract,
    prompt: str,
    tool: str,
    price: int = 10_000_000_000_000_000,
    retries: Optional[int] = None,
    timeout: Optional[float] = None,
    sleep: Optional[float] = None,
) -> None:
    """
    Sends a request to the mech.

    :param crypto: The Ethereum crypto object.
    :type crypto: EthereumCrypto
    :param ledger_api: The Ethereum API used for interacting with the ledger.
    :type ledger_api: EthereumApi
    :param mech_contract: The mech contract instance.
    :type mech_contract: Web3Contract
    :param prompt: The request prompt.
    :type prompt: str
    :param tool: The requested tool.
    :type tool: str
    :param price: The price for the request (default: 10_000_000_000_000_000).
    :type price: int
    :param retries: Number of retries for sending a transaction
    :type retries: int
    :param timeout: Timeout to wait for the transaction
    :type timeout: float
    :param sleep: Amount of sleep before retrying the transaction
    :type sleep: float
    """
    v1_file_hash_hex_truncated, v1_file_hash_hex = push_metadata_to_ipfs(prompt, tool)
    print(f"Prompt uploaded: https://gateway.autonolas.tech/ipfs/{v1_file_hash_hex}")
    method_name = "request"
    methord_args = {"data": v1_file_hash_hex_truncated}
    tx_args = {
        "sender_address": crypto.address,
        "value": price,
        "gas": MANUAL_GAS_LIMIT,
    }

    tries = 0
    retries = retries or MAX_RETRIES
    timeout = timeout or TIMEOUT
    sleep = sleep or WAIT_SLEEP
    deadline = datetime.now().timestamp() + timeout

    while tries < retries and datetime.now().timestamp() < deadline:
        tries += 1
        try:
            raw_transaction = ledger_api.build_transaction(
                contract_instance=mech_contract,
                method_name=method_name,
                method_args=methord_args,
                tx_args=tx_args,
                raise_on_try=True,
            )
            signed_transaction = crypto.sign_transaction(raw_transaction)
            transaction_digest = ledger_api.send_signed_transaction(
                signed_transaction,
                raise_on_try=True,
            )
            print(f"Transaction sent: https://gnosisscan.io/tx/{transaction_digest}")
            return
        except Exception as e:  # pylint: disable=broad-except
            print(
                f"Error occured while sending the transaction: {e}; Retrying in {sleep}"
            )
            time.sleep(sleep)

    
def wait_for_receipt(tx_hash: str, ledger_api: EthereumApi, timeout_seconds: int = TIMEOUT, retry_interval: int = 10) -> Dict:
    """
    Wait for a transaction receipt with retry and timeout.

    :param tx_hash: The transaction hash.
    :param ledger_api: The Ethereum API used for interacting with the ledger.
    :param timeout_seconds: Total timeout in seconds.
    :param retry_interval: Interval between retries in seconds.
    :return: The transaction receipt, or None if not retrieved.
    """
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            receipt = ledger_api._api.eth.get_transaction_receipt(tx_hash)
            if receipt is not None:
                return receipt
        except Exception as e:
            print(f"Error retrieving receipt: {e}")
        time.sleep(retry_interval)
    print(f"Timeout reached waiting for transaction receipt for tx_hash: {tx_hash}")
    return None


def watch_for_request_id(
    wss: websocket.WebSocket,
    mech_contract: Web3Contract,
    ledger_api: EthereumApi,
    request_signature: str,
    timeout_seconds: int = TIMEOUT,
) -> str:
    """
    Watches for events on mech.

    :param wss: The WebSocket connection object.
    :type wss: websocket.WebSocket
    :param mech_contract: The mech contract instance.
    :type mech_contract: Web3Contract
    :param ledger_api: The Ethereum API used for interacting with the ledger.
    :type ledger_api: EthereumApi
    :param request_signature: Topic signature for Request event
    :type request_signature: str
    :param timeout_seconds: Maximum time to wait for the request ID.
    :type timeout_seconds: int
    :return: The requested ID or None if timeout.
    :rtype: str or None
    """
    start_time = time.time()  # Record the start time
    while True:
        # Check for timeout
        if time.time() - start_time > timeout_seconds:
            print("Timeout waiting for request ID.")
            return None  # Or handle the timeout as needed

        # Set the WebSocket to non-blocking
        wss.settimeout(timeout_seconds - (time.time() - start_time))

        try:
            msg = wss.recv()
        except websocket.WebSocketTimeoutException:
            print("Timeout waiting for a message.")
            return None  # Or handle the timeout as needed
        except Exception as e:
            print(f"Error receiving message: {e}")
            return None  # Or handle other exceptions as needed

        data = json.loads(msg)
        tx_hash = data["params"]["result"]["transactionHash"]
        tx_receipt = wait_for_receipt(tx_hash=tx_hash, ledger_api=ledger_api)
        event_signature = tx_receipt["logs"][0]["topics"][0].hex()
        if event_signature != request_signature:
            continue

        rich_logs = mech_contract.events.Request().process_receipt(tx_receipt)
        request_id = str(rich_logs[0]["args"]["requestId"])
        return request_id
    

##############################################################################################################
################################## DELIVER EVENT #############################################################
##############################################################################################################
MECH_SUBGRAPH_URL = "https://api.studio.thegraph.com/query/57238/mech/version/latest"
AGENT_QUERY_TEMPLATE = Template(
    """{
    createMeches(where:{agentId:$agent_id}) {
        mech
    }
}
"""
)
DELIVER_QUERY_TEMPLATE = Template(
    """{
    delivers(
        orderBy: blockTimestamp
        where: {requestId:"$request_id"}
        orderDirection: desc
    ) {
        ipfsHash
  }
}
"""
)
DEFAULT_TIMEOUT = 600.0

async def query_deliver_hash(
    request_id: str, timeout: Optional[float] = None
) -> Optional[str]:
    """
    Query deliver IPFS hash from subgraph.

    :param request_id: The ID of the mech request.
    :param timeout: Timeout for the request.
    :type request_id: str
    :return: The deliver IPFS hash if found, None otherwise.
    :rtype: Optional[str]
    """
    client = Client(
        transport=AIOHTTPTransport(url=MECH_SUBGRAPH_URL),
        execute_timeout=timeout or 30.0,
    )
    response = await client.execute_async(
        document=gql(
            request_string=DELIVER_QUERY_TEMPLATE.substitute({"request_id": request_id})
        )
    )
    delivers = response["delivers"]  # pylint: disable=unsubscriptable-object
    if len(delivers) == 0:
        return None

    (record,) = delivers
    return record["ipfsHash"]


async def watch_for_data_url_from_subgraph(
    request_id: str, timeout: Optional[float] = None
) -> Optional[str]:
    """
    Continuously query for data URL until it's available or timeout is reached.

    :param request_id: The ID of the mech request.
    :type request_id: str
    :param timeout: Maximum time to wait for the data URL in seconds. Defaults to DEFAULT_TIMEOUT.
    :type timeout: Optional[float]
    :return: Data URL if available within timeout, otherwise None.
    :rtype: Optional[str]
    """
    timeout = timeout or DEFAULT_TIMEOUT
    start_time = asyncio.get_event_loop().time()
    while True:
        response = await query_deliver_hash(request_id=request_id)
        if response is not None:
            return f"https://gateway.autonolas.tech/ipfs/{response}"

        if asyncio.get_event_loop().time() - start_time >= timeout:
            print(f"Error: No response received after {timeout} seconds.")
            break

        await asyncio.sleep(5)

    return None

async def modified_watch_for_data_url_from_subgraph(
    request_id: str, timeout: Optional[float] = None
) -> Optional[str]:
    timeout = timeout or DEFAULT_TIMEOUT
    response = await query_deliver_hash(request_id=request_id)
    if response is not None:
        return f"https://gateway.autonolas.tech/ipfs/{response}"
    return None



##############################################################################################################
################################## MAIN REQUEST FUNCTION #############################################################
##############################################################################################################
async def make_mech_request(prompt: str, agent_id: int, tool: Optional[str] = None) -> Optional[str]:
    contract_address = await query_agent_address(agent_id=agent_id, timeout=30)
    wss = websocket.create_connection(WSS_ENDPOINT)
    crypto = EthereumCrypto(private_key_path=private_key_path)
    ledger_api = EthereumApi(**LEDGER_CONFIG)
    tool = tool or 'prediction-offline'
    tool = verify_or_retrieve_tool(agent_id=agent_id, ledger_api=ledger_api, tool=tool)
    abi = get_abi(contract_address=contract_address)
    mech_contract = get_contract(
        contract_address=contract_address, abi=abi, ledger_api=ledger_api
    )
    request_event_signature, deliver_event_signature = get_event_signatures(abi=abi)
    register_event_handlers(
        wss=wss,
        contract_address=contract_address,
        crypto=crypto,
        request_signature=request_event_signature,
        deliver_signature=deliver_event_signature,
    )
    send_request(
        crypto=crypto,
        ledger_api=ledger_api,
        mech_contract=mech_contract,
        prompt=prompt,
        tool=tool,
        timeout=180,
        retries=3,
        sleep=3,
    ) 

    request_id = watch_for_request_id(
        wss=wss,
        mech_contract=mech_contract,
        ledger_api=ledger_api,
        request_signature=request_event_signature,
    )

    print(f"Request ID: {request_id}")

    wss.close()

    return request_id