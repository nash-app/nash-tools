import base64
import os
import requests
import time
from decimal import Decimal


from solana.rpc.api import Client
from solders.transaction import VersionedTransaction
from solders.message import MessageV0
from pydantic import BaseModel, Field, field_validator
from bip_utils import Bip39SeedGenerator
from solders.keypair import Keypair

RAYDIUM_API_HOST = "https://transaction-v1.raydium.io"
RAYDIUM_COMPUTE_SWAP_IN_API_ENDPOINT = f"{RAYDIUM_API_HOST}/compute/swap-base-in"
RAYDIUM_COMPUTE_SWAP_OUT_API_ENDPOINT = f"{RAYDIUM_API_HOST}/compute/swap-base-out"
RAYDIUM_SWAP_IN_API_ENDPOINT = f"{RAYDIUM_API_HOST}/transaction/swap-base-in"
RAYDIUM_SWAP_OUT_API_ENDPOINT = f"{RAYDIUM_API_HOST}/transaction/swap-base-out"
PRIORITY_FEE = "200000"
WSOL_INPUT_MINT = "So11111111111111111111111111111111111111112"  # WSOL
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"

DESCRIPTION = "Swaps SOL for a given token on Raydium. Takes token address, amount of SOL, and slippage in basis points."


class LLMParams(BaseModel):
    """Base class for parameters that must be provided by the LLM"""

    token_address: str = Field(
        ...,
        description="Address of token to swap to",
        min_length=32,  # Solana addresses are 32-44 chars
        max_length=44,
        pattern="^[1-9A-HJ-NP-Za-km-z]{32,44}$",  # Base58 format
    )
    amount: Decimal = Field(
        ..., description="Amount of SOL to swap", gt=0, le=10000  # Reasonable maximum
    )
    slippage_bps: int = Field(
        ..., description="Slippage in basis points", gt=0, le=1000  # Max 10% slippage
    )

    @field_validator("token_address")
    def validate_token_address(cls, v: str) -> str:
        if v == WSOL_INPUT_MINT:
            raise ValueError("Cannot swap SOL to SOL")
        return v


class ToolParameters(LLMParams):
    """Complete interface that the LLM must satisfy to use this tool.
    Must only extend LLMParams."""

    pass


class RaydiumError(Exception):
    """Custom exception for Raydium transaction errors"""

    pass


def get_swap_computation(
    token_address: str,
    lamports_amount: int,
    slippage_bps: int,
) -> dict:
    """Get swap computation from Raydium API"""
    try:
        response = requests.get(
            f"{RAYDIUM_COMPUTE_SWAP_IN_API_ENDPOINT}?inputMint={WSOL_INPUT_MINT}&"
            f"outputMint={token_address}&amount={lamports_amount}&"
            f"slippageBps={slippage_bps}&txVersion=V0"
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("success", False):
            raise RaydiumError(
                f"Swap computation failed: {data.get('msg', 'Unknown error')}"
            )

        return data
    except requests.RequestException as e:
        raise RaydiumError(f"API request failed: {str(e)}")


def get_swap_transaction(
    compute_data: dict,
    wallet_pubkey: str,
) -> dict:
    """Get transaction data from Raydium API"""
    try:
        trade_data = {
            "swapResponse": compute_data,
            "version": "V0",
            "txVersion": "V0",
            "wrapSol": True,
            "computeUnitPriceMicroLamports": PRIORITY_FEE,
            "wallet": str(wallet_pubkey),
        }
        response = requests.post(RAYDIUM_SWAP_IN_API_ENDPOINT, json=trade_data)
        response.raise_for_status()
        data = response.json()

        if not data.get("success", False):
            raise RaydiumError(
                f"Swap transaction failed: {data.get('msg', 'Unknown error')}"
            )

        return data
    except requests.RequestException as e:
        raise RaydiumError(f"API request failed: {str(e)}")


def process_transaction(transaction_data: dict, solana_keypair: Keypair) -> str:
    """Process a Raydium transaction and return the transaction hash"""
    try:
        # Setup Solana client
        solana_client = Client(SOLANA_RPC_URL)

        # Get latest blockhash first
        recent_blockhash = solana_client.get_latest_blockhash().value.blockhash

        # Decode transaction
        transaction_bytes = base64.b64decode(transaction_data["transaction"])
        transaction = VersionedTransaction.from_bytes(transaction_bytes)

        # Create new message with latest blockhash
        new_message = MessageV0(
            transaction.message.header,
            transaction.message.account_keys,
            recent_blockhash,
            transaction.message.instructions,
            transaction.message.address_table_lookups,
        )

        # Sign and send transaction
        new_transaction = VersionedTransaction(new_message, [solana_keypair])
        if not new_transaction.signatures:
            raise RaydiumError("Failed to sign transaction")

        # Add small delay to ensure blockhash is registered
        time.sleep(0.5)

        # Send transaction
        result = solana_client.send_transaction(new_transaction)
        if result.value is None:
            raise RaydiumError(f"Failed to send transaction: {result}")

        return str(result.value)

    except Exception as e:
        error_msg = str(e)
        if "insufficient lamports" in error_msg:
            raise RaydiumError(
                "Insufficient SOL to cover transaction fees and account creation costs. "
                "Need at least 0.004 SOL extra for fees."
            )
        raise RaydiumError(f"Transaction processing failed: {error_msg}")


def send_notification(message: str) -> None:
    """Send notification through Nash API proxy"""
    try:
        NASH_PROJECT_API_KEY = os.getenv("NASH_PROJECT_API_KEY")
        if not NASH_PROJECT_API_KEY:
            raise RaydiumError(
                "Environment Variable NASH_PROJECT_API_KEY not present. Did you set it in your project's secrets?"
            )

        response = requests.post(
            "https://api.nash.run/notifications/push",
            headers={"X-API-KEY": NASH_PROJECT_API_KEY},
            json={"title": "Raydium Swap", "body": message},
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise RaydiumError(f"Failed to send notification: {str(e)}")


def format_error_message(error_type: str, details: str) -> str:
    """Format error messages consistently for LLM consumption.

    Args:
        error_type: Category of error (e.g., "API Error", "Validation Error")
        details: Specific error details

    Returns:
        Formatted error message string
    """
    return f"raydium_swap_buy_tool error: {error_type} - {details}"


def tool_function(token_address: str, amount: Decimal, slippage_bps: int) -> str:
    """Swaps SOL for a given token on Raydium"""
    try:
        # Validate parameters
        try:
            params = ToolParameters(
                token_address=token_address, amount=amount, slippage_bps=slippage_bps
            )
        except ValueError as e:
            return format_error_message("Validation Error", str(e))

        # Get keypair from mnemonic
        MNEMONIC = os.getenv("MNEMONIC")
        if not MNEMONIC:
            return format_error_message(
                "Config Error",
                "Environment Variable MNEMONIC not present. Did you set it in your project's secrets?",
            )

        solana_keypair = Keypair.from_seed_and_derivation_path(
            Bip39SeedGenerator(MNEMONIC).Generate(), "m/44'/501'/0'/0'"
        )
        pub_key = str(solana_keypair.pubkey())

        # Core swap logic
        lamports_amount = int(params.amount * Decimal(10**9))

        # Get swap computation
        try:
            compute_result = get_swap_computation(
                token_address=params.token_address,
                lamports_amount=lamports_amount,
                slippage_bps=params.slippage_bps,
            )
        except RaydiumError as e:
            return format_error_message("Swap Computation Error", str(e))

        # Get transaction data
        try:
            swap_response = get_swap_transaction(
                compute_data=compute_result,
                wallet_pubkey=pub_key,
            )
        except RaydiumError as e:
            return format_error_message("Transaction Creation Error", str(e))

        # Process transactions
        transactions = swap_response.get("data", [])
        if not transactions:
            return format_error_message("API Error", "No transaction data received")

        for tx_data in transactions:
            last_error = None
            for _ in range(5):
                try:
                    tx_hash = process_transaction(tx_data, solana_keypair)
                    if tx_hash:
                        try:
                            send_notification(
                                f"Swapped {amount} SOL for {token_address} on Raydium"
                            )
                        except RaydiumError:
                            # Ignore notification failures
                            pass
                        return "Swap successful"
                except RaydiumError as e:
                    last_error = str(e)
                    if "insufficient" in last_error.lower():
                        return format_error_message("Transaction Error", last_error)
                    continue
            return format_error_message(
                "Transaction Error", f"Failed after 5 retries: {last_error}"
            )

        return format_error_message("Unknown Error", "No transactions processed")
    except Exception as e:
        return format_error_message("Unexpected Error", str(e))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    output = tool_function(
        token_address="AxriehR6Xw3adzHopnvMn7GcpRFcD41ddpiTWMg6pump",
        amount=Decimal("0.004"),
        slippage_bps=1000,
    )
    print(output)
