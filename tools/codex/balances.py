import csv
import io
import os
from bip_utils import Bip39SeedGenerator
from solders.keypair import Keypair

import requests
from pydantic import BaseModel


DESCRIPTION = (
    "Returns the balances of a given wallet on the Solana blockchain in CSV format. If no wallet is provided, it will return the balances of the wallet associated with the agent. "
    "If there are no balances, it will return 'No balances for this address' which you can assume means the wallet has no balances for any tokens and you can move on."
)


class ToolParameters(BaseModel):
    """No parameters needed since wallet is handled via kwargs"""

    pass


class BalancesError(Exception):
    """Custom exception for balance fetching errors"""

    pass


def fetch_balances(wallet_address: str) -> list:
    """Fetch balances from Defined.fi API"""
    solana_chain_id = "1399811149"
    balances = []
    cursor = "null"

    for _ in range(10):
        headers = {
            "Content-Type": "application/json",
            "X-API-KEY": os.getenv("NASH_PROJECT_API_KEY"),
        }
        data = {
            "query": f"""
                query {{
                balances(input: {{ walletId: "{wallet_address}:{solana_chain_id}", cursor: {cursor} }}) {{
                    cursor
                    items {{
                        walletId
                        tokenId
                        balance
                        shiftedBalance
                    }}
                }}
            }}
            """
        }

        try:
            response = requests.post(
                "https://api.nash.run/proxy/codex",
                headers=headers,
                json=data,
            )
            response.raise_for_status()

            data = response.json()
            if "errors" in data:
                raise BalancesError(f"GraphQL Error: {data['errors']}")

            items = data["data"]["balances"]["items"]
            if not items:
                break

            balances.extend(items)
            cursor = data["data"]["balances"]["cursor"]
            if not cursor:
                break

            cursor = f'"{cursor}"'

        except requests.RequestException as e:
            raise BalancesError(f"API request failed: {str(e)}")
        except (KeyError, TypeError) as e:
            raise BalancesError(f"Invalid API response format: {str(e)}")

    return balances


def format_balances_csv(balances: list) -> str:
    """Format balances into CSV string"""
    if not balances:
        return "No balances for this address"

    fieldnames = balances[0].keys()
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for balance in balances:
        cleaned_balance = {
            key: (
                ""
                if value is None
                else (
                    value.replace(":1399811149", "")
                    if isinstance(value, str)
                    else value
                )
            )
            for key, value in balance.items()
        }
        writer.writerow(cleaned_balance)

    return output.getvalue()


def format_error_message(error_type: str, details: str) -> str:
    """Format error messages consistently"""
    return f"balances_tool error: {error_type} - {details}"


def tool_function() -> str:
    try:
        MNEMONIC = os.getenv("MNEMONIC")
        # Generate Solana address from mnemonic
        solana_keypair = Keypair.from_seed_and_derivation_path(
            Bip39SeedGenerator(MNEMONIC).Generate(), "m/44'/501'/0'/0'"
        )
        wallet_address = str(solana_keypair.pubkey())

        # Fetch balances
        try:
            balances = fetch_balances(wallet_address)
        except BalancesError as e:
            return format_error_message("API Error", str(e))

        # Format and return results
        return format_balances_csv(balances)

    except Exception as e:
        return format_error_message("Unexpected Error", str(e))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    output = tool_function()
    print(output)
