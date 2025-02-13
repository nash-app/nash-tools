import os
import requests
from pydantic import BaseModel, Field


DESCRIPTION = "Fetches the latest 10 posts from a specific user's Farcaster feed and returns them as a CSV string."


class ToolParameters(BaseModel):
    fid: int = Field(..., description="Farcaster user fid to fetch the feed for")


class FeedError(Exception):
    """Custom exception for feed fetching errors"""

    pass


def fetch_feed(fid: int) -> list:
    """Fetch user feed through Nash API proxy"""
    try:
        response = requests.get(
            "https://api.nash.run/proxy/neynar/v2/farcaster/feed/following",
            headers={
                "X-API-KEY": os.getenv("NASH_PROJECT_API_KEY"),
                "Content-Type": "application/json",
            },
            params={"fid": fid},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("casts", [])[:10]
    except requests.RequestException as e:
        raise FeedError(f"API request failed: {str(e)}")


def format_feed_csv(casts: list) -> str:
    """Format casts into CSV string"""
    if not casts:
        return "No posts found"

    csv_rows = ["author,text"]
    for cast in casts:
        author = cast["author"]["username"]
        text = cast["text"].replace('"', '""').replace("\n", " ")
        csv_rows.append(f'"{author}","{text}"')

    return "\n".join(csv_rows)


def format_error_message(error_type: str, details: str) -> str:
    """Format error messages consistently"""
    return f"feed_tool error: {error_type} - {details}"


def tool_function(fid: int) -> str:
    try:
        try:
            params = ToolParameters(fid=fid)
        except ValueError as e:
            return format_error_message("Validation Error", str(e))

        try:
            casts = fetch_feed(params.fid)
            return format_feed_csv(casts)
        except FeedError as e:
            return format_error_message("API Error", str(e))

    except Exception as e:
        return format_error_message("Unexpected Error", str(e))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    output = tool_function(fid=3)  # Example FID
    print(output)
