import os
import requests
from pydantic import BaseModel, Field, field_validator

DESCRIPTION = """
Minimal template demonstrating the required structure for tool development.

This template shows:
1. Parameter validation using Pydantic
2. Error handling with custom exceptions
3. Helper functions with clear return types
4. Environment variable handling
5. Nash API proxy usage
"""


class ToolParameters(BaseModel):
    """Parameters that must be provided to the tool"""

    message: str = Field(
        ..., description="Message to echo back", min_length=1, max_length=1000
    )

    @field_validator("message")
    def validate_message(cls, v):
        if v.strip() == "":
            raise ValueError("Message cannot be empty or just whitespace")
        return v


class ToolError(Exception):
    """Custom exception for tool-specific errors"""

    pass


def send_notification(message: str) -> None:
    """Helper function to send notifications via Nash API proxy"""
    try:
        response = requests.post(
            "https://api.nash.run/proxy/notifications",
            headers={"X-API-KEY": os.getenv("NASH_PROJECT_API_KEY")},
            json={"title": "Message Received", "body": f"Echo: {message}"},
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise ToolError(f"Failed to send notification: {str(e)}")


def format_error_message(error_type: str, details: str) -> str:
    """Format error messages consistently"""
    return f"template_tool error: {error_type} - {details}"


def tool_function(message: str) -> str:
    """Template tool that echoes back a message."""
    try:
        # Validate env vars
        api_key = os.getenv("NASH_PROJECT_API_KEY")
        if not api_key:
            return format_error_message("Config Error", "NASH_PROJECT_API_KEY not set")

        # Validate parameters
        try:
            params = ToolParameters(message=message)
        except ValueError as e:
            return format_error_message("Validation Error", str(e))

        # Core tool logic
        try:
            send_notification(params.message)
            return f"Echoed message: {params.message}"
        except ToolError as e:
            return format_error_message("API Error", str(e))

    except Exception as e:
        return format_error_message("Unexpected Error", str(e))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    output = tool_function(message="Hello, World!")
    print(output)
