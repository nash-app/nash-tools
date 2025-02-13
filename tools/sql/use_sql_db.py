import os
from typing import Any, List, Dict
from pydantic import BaseModel, Field
from sqlalchemy import text, create_engine
from sqlalchemy.orm import Session

DESCRIPTION = """
Administrative tool for executing arbitrary SQL queries against a database.
Use with caution as this tool can perform any SQL operation.

Required environment variables:
- DATABASE_URL: Database connection string

This tool:
1. Connects to a database using environment configuration
2. Executes provided SQL query
3. Returns results in a structured format
"""


class ToolError(Exception):
    """Custom exception for database operation errors"""

    pass


class ToolParameters(BaseModel):
    """Validates LLM-provided parameters"""

    sql_query: str = Field(
        ..., description="SQL query to execute", min_length=1, max_length=10000
    )


def format_error_message(error_type: str, message: str) -> str:
    """Format error messages consistently"""
    return f"Error ({error_type}): {message}"


def execute_query(engine, query: str) -> List[Dict[str, Any]]:
    """
    Execute SQL query and return results.

    Args:
        engine: SQLAlchemy engine
        query: SQL query to execute

    Returns:
        List of dictionaries containing query results

    Raises:
        ToolError: If query execution fails
    """
    try:
        with Session(engine) as session:
            result = session.execute(text(query))
            if result.returns_rows:
                keys = result.keys()
                return [dict(zip(keys, row)) for row in result.fetchall()]
            return []
    except Exception as e:
        raise ToolError(f"Query execution failed: {str(e)}")


def tool_function(sql_query: str) -> str:
    """
    Execute SQL query against the database.

    Args:
        sql_query (str): SQL query to execute

    Returns:
        str: Query results or error message
    """
    try:
        # Validate environment variables
        DATABASE_URL = os.getenv("DATABASE_URL")
        if not DATABASE_URL:
            return format_error_message(
                "Config Error",
                "Environment Variable DATABASE_URL not present. Did you set it in your project's secrets?",
            )

        # Fix for Heroku's postgres:// URLs
        if DATABASE_URL.startswith("postgres://"):
            DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

        # Validate parameters
        try:
            params = ToolParameters(sql_query=sql_query)
        except ValueError as e:
            return format_error_message("Validation Error", str(e))

        # Core logic
        engine = create_engine(DATABASE_URL)
        results = execute_query(engine, params.sql_query)

        # Format results for output
        if not results:
            return "Query executed successfully (no rows returned)"
        return f"Query results:\n{results}"

    except ToolError as e:
        return format_error_message("Database Error", str(e))
    except Exception as e:
        return format_error_message("Unexpected Error", str(e))


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    output = tool_function(sql_query="SELECT version()")
    print(output)
