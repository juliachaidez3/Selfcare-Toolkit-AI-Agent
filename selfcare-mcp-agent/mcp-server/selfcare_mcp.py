import json
import os
import sys
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from openai import OpenAI

# Ensure we can import the project's prompt definitions
try:
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.append(str(PROJECT_ROOT))

    from backend.prompts import system_prompt as shared_system_prompt_text, user_prompt_template  # noqa: E402
except ImportError as e:
    import sys
    print(f"ERROR: Failed to import backend.prompts: {e}", file=sys.stderr)
    print(f"PROJECT_ROOT: {PROJECT_ROOT if 'PROJECT_ROOT' in locals() else 'NOT SET'}", file=sys.stderr)
    print(f"sys.path: {sys.path}", file=sys.stderr)
    raise

# Load .env from project root, backend, or current directory
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
load_dotenv(dotenv_path=PROJECT_ROOT / "backend" / ".env")
load_dotenv()  # Also try current directory

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    import sys
    print("ERROR: OPENAI_API_KEY is not set.", file=sys.stderr)
    print(f"Checked .env files in: {PROJECT_ROOT / '.env'}, {PROJECT_ROOT / 'backend' / '.env'}, current directory", file=sys.stderr)
    raise RuntimeError("OPENAI_API_KEY is not set. Please configure it in .env file in project root or backend directory.")

# Use synchronous client - FastMCP tools should be synchronous
client = OpenAI(api_key=api_key, timeout=90.0)  # 90 second timeout for API calls
mcp = FastMCP("selfcare-mcp")  # FastMCP doesn't support invocation_timeout parameter


@mcp.prompt()
def system_prompt() -> str:
    """Expose the same coaching instructions used by the FastAPI backend."""
    return shared_system_prompt_text.strip()


@mcp.tool()  # FastMCP tool decorator - must be synchronous
def generate_toolkit(
    struggle: str,
    mood: str,
    focus: str,
    coping_preferences: Optional[List[str]] = None,
    energy_level: str = "medium",
) -> str:
    """Generate a personalized self-care toolkit using the shared prompt template."""

    prompt = user_prompt_template.format(
        struggle=struggle,
        mood=mood,
        focus=focus,
        coping_preferences=", ".join(coping_preferences or []),
        energy_level=energy_level,
    )

    # Use synchronous client for API call
    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": shared_system_prompt_text},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
    except Exception as e:
        import sys
        print(f"ERROR in OpenAI API call: {e}", file=sys.stderr)
        raise

    output = response.choices[0].message.content or "{}"

    try:
        parsed_output = json.loads(output)
    except json.JSONDecodeError as exc:
        import sys
        print(f"ERROR: Invalid JSON from OpenAI: {exc}", file=sys.stderr)
        print(f"Raw output: {output[:500]}", file=sys.stderr)
        raise ValueError(f"Invalid JSON response from OpenAI: {exc}") from exc

    # Extract recommendations - look for "recommendations" key specifically
    recommendations: list = []
    if isinstance(parsed_output, list):
        recommendations = parsed_output
    elif isinstance(parsed_output, dict):
        # First try the "recommendations" key (as specified in the prompt)
        if "recommendations" in parsed_output and isinstance(parsed_output["recommendations"], list):
            recommendations = parsed_output["recommendations"]
        else:
            # Fallback: look for any list value
            for key, value in parsed_output.items():
                if isinstance(value, list) and value:
                    recommendations = value
                    break

    if not recommendations:
        import sys
        print(f"ERROR: No recommendations found in response", file=sys.stderr)
        print(f"Parsed output keys: {list(parsed_output.keys()) if isinstance(parsed_output, dict) else 'N/A'}", file=sys.stderr)
        print(f"Parsed output: {str(parsed_output)[:500]}", file=sys.stderr)
        raise ValueError("No recommendations returned from the model")

    return json.dumps({"items": recommendations}, indent=2)


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except Exception as e:
        import sys
        import traceback
        print(f"ERROR in MCP server: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
