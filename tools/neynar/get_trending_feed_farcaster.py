import os
import time
import requests
from datetime import datetime
from typing import List, Optional, Tuple
from pydantic import BaseModel

DESCRIPTION = "Fetches up to 10 pages of trending posts from Farcaster's global feed and returns them as a CSV string."


class UserProfile(BaseModel):
    fid: int
    username: str
    display_name: Optional[str] = None
    pfp_url: Optional[str] = None


class Reaction(BaseModel):
    likes_count: int = 0
    recasts_count: int = 0


class Reply(BaseModel):
    count: int = 0


class Frame(BaseModel):
    title: Optional[str] = None
    frames_url: Optional[str] = None


class Embed(BaseModel):
    url: Optional[str] = None


class Channel(BaseModel):
    object: str
    name: Optional[str] = None
    parent_url: Optional[str] = None
    image_url: Optional[str] = None
    channel_id: Optional[str] = None


class Cast(BaseModel):
    hash: str
    thread_hash: Optional[str] = None
    parent_hash: Optional[str] = None
    author: UserProfile
    text: str
    timestamp: datetime
    reactions: Optional[Reaction] = None
    replies: Optional[Reply] = None
    frames: Optional[List[Frame]] = None
    embeds: Optional[List[Embed]] = None
    channel: Optional[Channel] = None


class PaginationInfo(BaseModel):
    cursor: Optional[str] = None


class TrendingFeedResponse(BaseModel):
    casts: List[Cast]
    next: Optional[PaginationInfo] = None


class ToolParameters(BaseModel):
    pass  # No parameters needed for trending feed


class ToolError(Exception):
    """Custom exception for trending feed errors"""

    pass


def fetch_page(cursor: Optional[str] = None) -> Tuple[List[Cast], Optional[str]]:
    """Fetch a single page of trending casts through Nash API proxy"""
    url = "https://api.nash.run/proxy/neynar/v2/farcaster/feed/trending"
    if cursor:
        url += f"?cursor={cursor}"

    headers = {
        "X-API-KEY": os.getenv("NASH_PROJECT_API_KEY"),
        "Content-Type": "application/json",
    }

    try:
        time.sleep(0.25)  # Rate limit handling
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        feed_data = TrendingFeedResponse.model_validate(response.json())
        next_cursor = feed_data.next.cursor if feed_data.next else None
        return feed_data.casts, next_cursor

    except requests.RequestException as e:
        raise ToolError(f"API request failed: {str(e)}")
    except Exception as e:
        raise ToolError(f"Failed to process response: {str(e)}")


def format_casts_as_csv(casts: List[Cast]) -> str:
    """Format casts into CSV string"""
    if not casts:
        return "No trending posts found"

    csv_rows = [
        "timestamp,cast_hash,thread_hash,parent_hash,author_fid,author_username,author_display_name,author_pfp_url,text,channel_name,embed_url,frame_title,frame_url,warpcast_url,likes_count,recasts_count,replies_count"
    ]

    for cast in casts:
        # Prepare all fields with proper escaping
        timestamp = cast.timestamp.isoformat()
        cast_hash = cast.hash
        thread_hash = cast.thread_hash or ""
        parent_hash = cast.parent_hash or ""
        text = cast.text.replace('"', '""').replace("\n", " ")

        # Author fields
        author_fid = cast.author.fid
        author_username = cast.author.username
        author_display_name = cast.author.display_name or ""
        author_pfp_url = cast.author.pfp_url or ""

        # Build warpcast URL
        warpcast_url = f"https://warpcast.com/{author_username}/{cast_hash}"

        # Channel and embed fields
        channel_name = cast.channel.name if cast.channel else ""
        embed_url = (
            cast.embeds[0].url
            if cast.embeds and len(cast.embeds) > 0 and cast.embeds[0].url
            else ""
        )

        # Frame fields
        frame_title = (
            cast.frames[0].title
            if cast.frames and len(cast.frames) > 0 and cast.frames[0].title
            else ""
        )
        frame_url = (
            cast.frames[0].frames_url
            if cast.frames and len(cast.frames) > 0 and cast.frames[0].frames_url
            else ""
        )

        # Engagement metrics
        likes_count = cast.reactions.likes_count if cast.reactions else 0
        recasts_count = cast.reactions.recasts_count if cast.reactions else 0
        replies_count = cast.replies.count if cast.replies else 0

        # Build fields in the exact order we want them in the CSV
        escaped_fields = [
            f'"{timestamp}"',
            f'"{cast_hash}"',
            f'"{thread_hash}"',
            f'"{parent_hash}"',
            str(author_fid),  # Unquoted numeric field
            f'"{author_username}"',
            f'"{author_display_name}"',
            f'"{author_pfp_url}"',
            f'"{text}"',
            f'"{channel_name}"',
            f'"{embed_url}"',
            f'"{frame_title}"',
            f'"{frame_url}"',
            f'"{warpcast_url}"',
            str(likes_count),  # Unquoted numeric field
            str(recasts_count),  # Unquoted numeric field
            str(replies_count),  # Unquoted numeric field
        ]

        csv_rows.append(",".join(escaped_fields))

    return "\n".join(csv_rows)


def format_error_message(error_type: str, details: str) -> str:
    """Format error messages consistently"""
    return f"trending_feed_tool error: {error_type} - {details}"


def tool_function() -> str:
    """Fetches up to 10 pages of trending Farcaster posts and returns them as CSV."""
    try:
        all_casts = []
        next_cursor = None
        max_pages = 10

        try:
            for page in range(max_pages):
                casts, next_cursor = fetch_page(next_cursor)
                all_casts.extend(casts)

                if not next_cursor:
                    break

            return format_casts_as_csv(all_casts)

        except ToolError as e:
            return format_error_message("API Error", str(e))

    except Exception as e:
        return format_error_message("Unexpected Error", str(e))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    output = tool_function()
    print(output)
