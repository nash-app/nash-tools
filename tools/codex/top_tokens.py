import csv
import io
import time
import requests
import os
from pydantic import BaseModel, Field, field_validator


DESCRIPTION = (
    "Returns a CSV of the top trending tokens on the Solana blockchain over a given "
    "resolution. Resolution can be '1', '5', '15', '30', '60', '240', '720', or '1D' "
    "where '1' is 1 minute, '5' is 5 minutes, '15' is 15 minutes, '30' is 30 minutes, "
    "'60' is 1 hour, '240' is 4 hours, '720' is 12 hours, and '1D' is 1 day. If there are "
    "no tokens found, it will return 'No tokens found'."
)


class ToolParameters(BaseModel):
    resolution: str = Field(
        ...,
        description="Resolution for time window to look for trending tokens. "
        "Valid values are '1', '5', '15', '30', '60', '240', '720', or '1D'",
    )

    @field_validator("resolution")
    def validate_resolution(cls, v):
        valid_resolutions = ["1", "5", "15", "30", "60", "240", "720", "1D"]
        if v not in valid_resolutions:
            raise ValueError(f"Resolution must be one of {valid_resolutions}")
        return v


class TopTokensError(Exception):
    """Custom exception for top tokens fetching errors"""

    pass


def validate_params(resolution: str, **kwargs) -> str:
    """Extract and validate parameters"""
    params = ToolParameters(resolution=resolution)
    return params.resolution


def fetch_top_tokens(resolution: str) -> list:
    """Fetch top tokens through Nash API proxy"""
    solana_chain_id = "1399811149"
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": os.getenv("NASH_PROJECT_API_KEY"),
    }
    query = {
        "query": f"""
            query {{
                listTopTokens(networkFilter: [{solana_chain_id}], limit: 50, resolution: "{resolution}") {{
                name
                symbol
                address
                createdAt
                volume
                liquidity
                marketCap
                price
                priceChange1
                priceChange4
                priceChange12
                priceChange24
                uniqueBuys1
                uniqueBuys4
                uniqueBuys12
                uniqueBuys24
                uniqueSells1
                uniqueSells4
                uniqueSells12
                uniqueSells24
                txnCount1
                txnCount4
                txnCount12
                txnCount24
                isScam
            }}
        }}
        """
    }

    try:
        response = requests.post(
            "https://api.nash.run/proxy/codex",
            headers=headers,
            json=query,
        )
        response.raise_for_status()

        data = response.json()
        if "errors" in data:
            raise TopTokensError(f"GraphQL Error: {data['errors']}")

        return data["data"]["listTopTokens"]

    except requests.RequestException as e:
        raise TopTokensError(f"API request failed: {str(e)}")
    except (KeyError, TypeError) as e:
        raise TopTokensError(f"Invalid API response format: {str(e)}")


def process_tokens(tokens: list) -> list:
    """Process token data and calculate age"""
    for token in tokens:
        token["ageInMinutes"] = int((time.time() - token["createdAt"]) / 60)
        del token["createdAt"]
        del token["isScam"]
    return tokens


def format_tokens_csv(tokens: list) -> str:
    """Format tokens into CSV string"""
    if not tokens:
        return "No tokens found"

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=tokens[0].keys())
    writer.writeheader()

    for token in tokens:
        cleaned_token = {
            key: ("" if value is None else value) for key, value in token.items()
        }
        writer.writerow(cleaned_token)

    return output.getvalue()


def format_error_message(error_type: str, details: str) -> str:
    """Format error messages consistently"""
    return f"top_tokens_tool error: {error_type} - {details}"


def tool_function(resolution: str) -> str:
    try:
        try:
            # Validate parameters
            params = ToolParameters(resolution=resolution)
        except ValueError as e:
            return format_error_message("Validation Error", str(e))

        try:
            tokens = fetch_top_tokens(params.resolution)
            processed_tokens = process_tokens(tokens)
            return format_tokens_csv(processed_tokens)
        except TopTokensError as e:
            return format_error_message("API Error", str(e))

    except Exception as e:
        return format_error_message("Unexpected Error", str(e))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    output = tool_function(resolution="60")
    print(output)
