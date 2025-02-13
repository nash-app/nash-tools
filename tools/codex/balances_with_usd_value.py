from typing import Any, List, Dict
import csv
import io
import os
from bip_utils import Bip39SeedGenerator
from solders.keypair import Keypair

import requests
from pydantic import BaseModel


DESCRIPTION = (
    "Returns the balances of a given wallet on the Solana blockchain in CSV format. "
    "If no wallet is provided, it will return the balances of the wallet associated with the agent. "
    "If there are no balances, it will return 'No balances for this address' which you can assume "
    "means the wallet has no balances for any tokens and you can move on."
)

SOLANA_CHAIN_ID = "1399811149"


class ToolParameters(BaseModel):
    """No parameters needed since wallet is handled via kwargs"""

    pass


class BalancesError(Exception):
    """Custom exception for balance fetching errors"""

    pass


def chunks(lst: List[Any], n: int) -> List[List[Any]]:
    """Split list into chunks of size n"""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def fetch_balances(wallet_address: str) -> list:
    """Fetch balances through Nash API proxy"""
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
                balances(input: {{ walletId: "{wallet_address}:{SOLANA_CHAIN_ID}", cursor: {cursor} }}) {{
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


def fetch_token_prices(token_ids: List[str]) -> Dict[str, float]:
    """Fetch token prices through Nash API proxy"""
    prices = {}

    for token_chunk in chunks(token_ids, 25):
        inputs = [
            {"address": token_id.split(":")[0], "networkId": int(SOLANA_CHAIN_ID)}
            for token_id in token_chunk
        ]

        query_inputs = "\n      ".join(
            f'{{ address: "{input["address"]}", networkId: {input["networkId"]} }}'
            for input in inputs
        )

        data = {
            "query": f"""
                query {{
                    getTokenPrices(
                        inputs: [
                            {query_inputs}
                        ]
                    ) {{
                        address
                        networkId
                        priceUsd
                    }}
                }}
            """
        }

        try:
            response = requests.post(
                "https://api.nash.run/proxy/codex",
                headers={
                    "X-API-KEY": os.getenv("NASH_PROJECT_API_KEY"),
                    "Content-Type": "application/json",
                },
                json=data,
            )
            response.raise_for_status()

            result = response.json()
            if "errors" in result:
                raise BalancesError(f"GraphQL Error: {result['errors']}")

            for price_data in result["data"]["getTokenPrices"]:
                token_id = f"{price_data['address']}:{price_data['networkId']}"
                prices[token_id] = price_data["priceUsd"]

        except requests.RequestException as e:
            raise BalancesError(f"Price API request failed: {str(e)}")

    return prices


def format_balances_csv(balances: list, token_prices: Dict[str, float]) -> str:
    """Format balances into CSV string with USD values"""
    if not balances:
        return "No balances for this address"

    fieldnames = list(balances[0].keys()) + ["usdValue"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for balance in balances:
        cleaned_balance = {
            key: (
                ""
                if value is None
                else (
                    value.replace(f":{SOLANA_CHAIN_ID}", "")
                    if isinstance(value, str)
                    else value
                )
            )
            for key, value in balance.items()
        }

        # Calculate total USD value
        token_price = token_prices.get(balance["tokenId"], 0)
        cleaned_balance["usdValue"] = float(balance["shiftedBalance"]) * token_price

        writer.writerow(cleaned_balance)

    return output.getvalue()


def format_error_message(error_type: str, details: str) -> str:
    """Format error messages consistently"""
    return f"balances_tool error: {error_type} - {details}"


def tool_function() -> str:
    try:
        mnemonic = os.getenv("MNEMONIC")
        if not mnemonic:
            return format_error_message(
                "Parameter Error", "MNEMONIC environment variable not set"
            )

        # Generate Solana address from mnemonic
        solana_keypair = Keypair.from_seed_and_derivation_path(
            Bip39SeedGenerator(mnemonic).Generate(), "m/44'/501'/0'/0'"
        )
        wallet_address = str(solana_keypair.pubkey())

        # Fetch balances
        try:
            balances = fetch_balances(wallet_address)
            if balances:
                token_ids = [b["tokenId"] for b in balances]
                token_prices = fetch_token_prices(token_ids)
            else:
                token_prices = {}
        except BalancesError as e:
            return format_error_message("API Error", str(e))

        # Format and return results with USD values
        return format_balances_csv(balances, token_prices)

    except Exception as e:
        return format_error_message("Unexpected Error", str(e))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    output = tool_function()
    print(output)
