import os
import time
import requests
import pandas as pd
import mplfinance as mpf
from pydantic import BaseModel, Field, field_validator

DESCRIPTION = "Returns chart data for a given token over a given duration in minutes with resolution of 5 minutes on the Solana blockchain in CSV format."


class ToolParameters(BaseModel):
    token_address: str = Field(..., description="Solana token address")
    duration: str = Field(..., description="Duration in minutes")

    @field_validator("duration")
    def validate_duration(cls, v):
        try:
            duration = int(v)
            if duration <= 0:
                raise ValueError("Duration must be a positive number")
            return v
        except ValueError:
            raise ValueError("Duration must be a valid number in minutes")


class ChartError(Exception):
    """Custom exception for chart data fetching errors"""

    pass


def validate_params(token_address: str, duration: str, **kwargs) -> tuple[str, str]:
    """Extract and validate parameters"""
    params = ToolParameters(token_address=token_address, duration=duration)
    return params.token_address, params.duration


def fetch_chart_data(token_address: str, duration: str) -> dict:
    """Fetch chart data through Nash API proxy"""
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": os.getenv("NASH_PROJECT_API_KEY"),
    }

    data = {
        "query": f"""
            query {{
                getBars(
                    symbol: "{token_address}:1399811149"
                    from: {int(time.time()) - (int(duration)*60)}
                    to: {int(time.time())}
                    resolution: "5"
                    quoteToken: token1
                ) {{
                    o
                    h
                    l
                    c
                    v
                    t
                    volume
                    sellers
                    sells
                    sellVolume
                    buyers
                    buys
                    buyVolume
                    traders
                    transactions
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

        result = response.json()
        if "errors" in result:
            raise ChartError(f"GraphQL Error: {result['errors']}")

        bars = result["data"]["getBars"]
        if not bars:
            return {}
        return bars
    except requests.RequestException as e:
        raise ChartError(f"API request failed: {str(e)}")
    except (KeyError, TypeError) as e:
        raise ChartError(f"Invalid API response format: {str(e)}")


def process_chart_data(data: dict) -> str:
    """
    Convert the raw dictionary-of-arrays chart data into a row-based CSV.
    Exclude any row with None in critical fields: timestamp, open, high, low, close.
    Columns:
      timestamp,open,high,low,close,volume,buyVolume,sellVolume,
      buyers,sellers,buys,sells,traders,transactions
    Return the CSV string. If empty or invalid, return "No chart data".
    """

    # If 'data' is empty or not a dict with the right keys, return "No chart data"
    required_keys = [
        "o",
        "h",
        "l",
        "c",
        "t",
        "volume",
        "buyVolume",
        "sellVolume",
        "buyers",
        "sellers",
        "buys",
        "sells",
        "traders",
        "transactions",
    ]
    if not data or any(k not in data for k in required_keys):
        return "No chart data"

    # Prepare the header
    header_cols = [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "buyVolume",
        "sellVolume",
        "buyers",
        "sellers",
        "buys",
        "sells",
        "traders",
        "transactions",
    ]
    lines = [",".join(header_cols)]

    # We'll assume length is the same across all arrays
    length = len(data["t"])

    for i in range(length):
        # Gather each field for row i
        row_fields = {
            "timestamp": data["t"][i],
            "open": data["o"][i],
            "high": data["h"][i],
            "low": data["l"][i],
            "close": data["c"][i],
            "volume": data["volume"][i],
            "buyVolume": data["buyVolume"][i],
            "sellVolume": data["sellVolume"][i],
            "buyers": data["buyers"][i],
            "sellers": data["sellers"][i],
            "buys": data["buys"][i],
            "sells": data["sells"][i],
            "traders": data["traders"][i],
            "transactions": data["transactions"][i],
        }

        # Exclude rows where any critical field is None
        critical_keys = ["timestamp", "open", "high", "low", "close"]
        if any(row_fields[k] is None for k in critical_keys):
            continue

        # Convert all fields to string (handle None if needed)
        row_str = ",".join(str(row_fields[col]) for col in header_cols)
        lines.append(row_str)

    if len(lines) == 1:
        # Means we had only the header, no valid rows
        return "No chart data"

    # Join all lines into final CSV
    return "\n".join(lines)


def format_error_message(error_type: str, details: str) -> str:
    """Format error messages consistently"""
    return f"chart_tool error: {error_type} - {details}"


def tool_function(token_address: str, duration: str) -> str:
    """
    Returns a CSV of 5-minute candlestick chart data for the specified token & duration.
    Uses environment variables for configuration.
    """
    try:
        try:
            # Validate parameters
            params = ToolParameters(token_address=token_address, duration=duration)
        except ValueError as e:
            return format_error_message("Validation Error", str(e))

        try:
            raw_chart_data = fetch_chart_data(params.token_address, params.duration)
            csv_data = process_chart_data(raw_chart_data)
            return csv_data
        except ChartError as e:
            return format_error_message("API Error", str(e))

    except Exception as e:
        return format_error_message("Unexpected Error", str(e))


def plot_chart(csv_data: str):
    """
    Plot a candlestick chart from CSV data (as returned by tool_function).
    Expects columns:
       timestamp,open,high,low,close,volume,buyVolume,sellVolume,
       buyers,sellers,buys,sells,traders,transactions
    """
    if csv_data == "No chart data" or csv_data.startswith("chart_tool error:"):
        print(csv_data)
        return

    import io

    df = pd.read_csv(io.StringIO(csv_data))

    # Convert timestamp to datetime
    df["Date"] = pd.to_datetime(df["timestamp"], unit="s")
    df.set_index("Date", inplace=True)

    # mplfinance needs columns: Open,High,Low,Close,Volume
    # So rename them:
    df.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "volume": "Volume",
        },
        inplace=True,
    )

    # For clarity, limit to these columns
    df_for_plot = df[["Open", "High", "Low", "Close", "Volume"]]

    mpf.plot(
        df_for_plot,
        type="candle",
        volume=True,
        style="charles",
        title="Candlestick Chart",
    )


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    output = tool_function(
        token_address="AxriehR6Xw3adzHopnvMn7GcpRFcD41ddpiTWMg6pump",
        duration="360",  # 6 hours
    )
    print(output)

    # Optional: Plot the resulting CSV
    # plot_chart(output)
