import json
import os
import sys
import asyncio
from pathlib import Path
from typing import Any, Dict, List

from agents import Agent, Runner
from agents.mcp import MCPServerStdio

from prompts import user_prompt_template

# Patch MCP client timeout - the SDK has a hardcoded 5-second timeout we need to override
try:
    import mcp
    import mcp.client.stdio
    import mcp.client.session
    
    # Try to find and patch the timeout constant
    # The MCP SDK might have a DEFAULT_TIMEOUT or similar constant
    for module_name in ['mcp.client.stdio', 'mcp.client.session', 'mcp']:
        try:
            module = __import__(module_name, fromlist=[''])
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                # Look for timeout-related constants
                if 'timeout' in attr_name.lower() and isinstance(attr, (int, float)):
                    if attr == 5.0:  # If it's the 5-second timeout
                        setattr(module, attr_name, 90.0)
        except:
            pass
    
    # Patch StdioClient initialization
    if hasattr(mcp.client.stdio, 'StdioClient'):
        StdioClient = mcp.client.stdio.StdioClient
        original_init = StdioClient.__init__
        
        def patched_init(self, *args, **kwargs):
            # Force timeout to 90 seconds
            kwargs['timeout'] = 90.0
            return original_init(self, *args, **kwargs)
        StdioClient.__init__ = patched_init
    
    # Note: Removed broken monkey-patching code that was causing coroutine warnings
            
except (ImportError, AttributeError, Exception) as e:
    # If patching fails, log but continue
    import logging
    logging.warning(f"Could not patch MCP client timeout: {e}")
    pass

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MCP_DIR = PROJECT_ROOT / "selfcare-mcp-agent"
MCP_SCRIPT = MCP_DIR / "mcp-server" / "selfcare_mcp.py"


async def _run_agent(prompt: str) -> Dict[str, Any]:
    """Call the MCP tool directly to avoid timeout issues with openai-agents library."""

    import logging
    logger = logging.getLogger(__name__)

    # Get OPENAI_API_KEY from environment to pass to MCP server
    env = os.environ.copy()
    if "OPENAI_API_KEY" not in env:
        # Try to load from .env file
        from dotenv import load_dotenv
        load_dotenv()
        if "OPENAI_API_KEY" in os.environ:
            env["OPENAI_API_KEY"] = os.environ["OPENAI_API_KEY"]

    # Verify MCP script exists
    if not MCP_SCRIPT.exists():
        raise RuntimeError(f"MCP server script not found at {MCP_SCRIPT}")

    # Set MCP client timeout environment variables (try multiple possible names)
    env["MCP_CLIENT_TIMEOUT"] = "90"
    env["MCP_TIMEOUT"] = "90"
    env["MCP_REQUEST_TIMEOUT"] = "90"
    env["MCP_TOOL_TIMEOUT"] = "90"
    env["TIMEOUT"] = "90"

    try:
        logger.info(f"Starting MCP server: {sys.executable} {MCP_SCRIPT}")
        logger.info(f"MCP script exists: {MCP_SCRIPT.exists()}")
        logger.info(f"MCP directory: {MCP_DIR}")
        logger.info(f"OPENAI_API_KEY in env: {'OPENAI_API_KEY' in env}")
        
        # Use absolute path for script and ensure cwd is correct
        script_path = str(MCP_SCRIPT.resolve())
        cwd_path = str(MCP_DIR.resolve())
        
        logger.info(f"Script absolute path: {script_path}")
        logger.info(f"CWD absolute path: {cwd_path}")
        
        async with MCPServerStdio(
            name="Selfcare MCP Server",
            params={
                "command": sys.executable,
                "args": [script_path],
                "cwd": cwd_path,
                "env": env,
            },
            client_session_timeout_seconds=120.0,  # Override default 5-second timeout
        ) as server:
            logger.info("MCP server connected, getting system prompt")
            try:
                prompt_result = await server.get_prompt("system_prompt")
                instructions = prompt_result.messages[0].content.text
                logger.info("System prompt retrieved successfully")

                agent = Agent(
                    name="Self-Care Companion",
                    instructions=instructions,
                    mcp_servers=[server],
                )

                input_items: List[Dict[str, str]] = [{"role": "user", "content": prompt}]
                logger.info("Starting agent execution")
                result = Runner.run_streamed(agent, input=input_items)

                tool_payload = None
                # Wrap the event streaming with a longer timeout to handle slow API responses
                try:
                    async def collect_events():
                        nonlocal tool_payload
                        async for event in result.stream_events():
                            if event.type == "run_item_stream_event" and event.item.type == "tool_call_output_item":
                                tool_payload = event.item.output
                                logger.info(f"Tool output received: {tool_payload[:200] if tool_payload else 'None'}...")  # Log first 200 chars
                    
                    await asyncio.wait_for(collect_events(), timeout=120.0)  # 120 second timeout
                except asyncio.TimeoutError:
                    raise RuntimeError("Tool execution timed out after 120 seconds. The API may be taking longer than expected.")

                if not tool_payload:
                    raise RuntimeError("Agent finished without emitting toolkit results")

                # Parse the tool output - it may be a JSON string or a structured object
                parsed_result = json.loads(tool_payload)
                logger.info(f"Parsed tool result type: {type(parsed_result)}")
                logger.info(f"Parsed tool result keys: {list(parsed_result.keys()) if isinstance(parsed_result, dict) else 'N/A'}")
                
                # The MCP tool output may be wrapped in a structure like {'type': 'text', 'text': '...'}
                # If so, we need to parse the 'text' field
                if isinstance(parsed_result, dict) and "text" in parsed_result:
                    # The actual JSON is in the 'text' field
                    inner_json = parsed_result["text"]
                    parsed_result = json.loads(inner_json)
                    logger.info(f"Parsed inner JSON, keys: {list(parsed_result.keys()) if isinstance(parsed_result, dict) else 'N/A'}")
                
                # The tool returns {"items": [...]}, so return it directly
                if isinstance(parsed_result, dict) and "items" in parsed_result:
                    logger.info(f"Found {len(parsed_result['items'])} items")
                    return parsed_result
                else:
                    # Fallback: if it's already in the right format or different structure
                    logger.warning(f"Unexpected result structure: {parsed_result}")
                    return parsed_result
            except Exception as e:
                logger.error(f"Error during agent execution: {e}", exc_info=True)
                raise RuntimeError(f"Error during agent execution: {str(e)}")
    except Exception as e:
        logger.error(f"Error connecting to MCP server: {e}", exc_info=True)
        # Check if it's a connection closed error
        error_msg = str(e)
        if "Connection closed" in error_msg or "connection" in error_msg.lower():
            raise RuntimeError(
                f"MCP server connection closed. This usually means the MCP server process crashed. "
                f"Check that the MCP server script exists and can run. Error: {error_msg}"
            )
        raise RuntimeError(f"Failed to connect to MCP server: {error_msg}")


def build_user_prompt(*, struggle: str, mood: str, focus: str, coping_preferences: List[str], energy_level: str) -> str:
    return user_prompt_template.format(
        struggle=struggle,
        mood=mood,
        focus=focus,
        coping_preferences=", ".join(coping_preferences),
        energy_level=energy_level,
    )


async def request_toolkit_async(**payload: Any) -> Dict[str, Any]:
    """Call the MCP tool using Agent approach with extended timeout handling."""
    prompt = build_user_prompt(**payload)
    return await _run_agent(prompt)
