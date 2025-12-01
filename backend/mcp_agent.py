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

                # For suggestions, we might want to use a different system prompt
                # that doesn't encourage tool usage. But for now, use the MCP system prompt.
                agent = Agent(
                    name="Self-Care Companion",
                    instructions=instructions,
                    mcp_servers=[server],
                )

                input_items: List[Dict[str, str]] = [{"role": "user", "content": prompt}]
                logger.info("Starting agent execution")
                logger.info(f"User prompt (first 200 chars): {prompt[:200]}...")
                result = Runner.run_streamed(agent, input=input_items)

                tool_payload = None
                text_output = None
                all_outputs = []
                # Wrap the event streaming with a longer timeout to handle slow API responses
                try:
                    async def collect_events():
                        nonlocal tool_payload, text_output, all_outputs
                        async for event in result.stream_events():
                            logger.info(f"Event received - type: {event.type}, item type: {getattr(event.item, 'type', 'N/A') if hasattr(event, 'item') else 'N/A'}")
                            if event.type == "run_item_stream_event":
                                item_type = getattr(event.item, 'type', 'unknown')
                                logger.info(f"Processing item type: {item_type}")
                                
                                if item_type == "tool_call_output_item":
                                    tool_payload = event.item.output
                                    logger.info(f"Tool output received: {str(tool_payload)[:200] if tool_payload else 'None'}...")
                                    all_outputs.append(("tool", tool_payload))
                                elif item_type == "text_output_item":
                                    text_output = event.item.output
                                    logger.info(f"Text output received: {str(text_output)[:200] if text_output else 'None'}...")
                                    all_outputs.append(("text", text_output))
                                elif item_type == "message_item" or item_type == "message_output_item":
                                    # Agent's message response
                                    logger.info(f"Processing message item, has raw_item: {hasattr(event.item, 'raw_item')}")
                                    if hasattr(event.item, 'raw_item') and hasattr(event.item.raw_item, 'content'):
                                        # Extract from raw_item.content (like in the example)
                                        content = event.item.raw_item.content
                                        if isinstance(content, list) and len(content) > 0:
                                            # Content is a list, get text from first item
                                            first_content = content[0]
                                            if hasattr(first_content, 'text'):
                                                text_output = first_content.text
                                            elif isinstance(first_content, dict) and 'text' in first_content:
                                                text_output = first_content['text']
                                            else:
                                                text_output = str(first_content)
                                            logger.info(f"Text output from message raw_item.content: {text_output[:200]}...")
                                            all_outputs.append(("text", text_output))
                                    elif hasattr(event.item, 'content'):
                                        content = event.item.content
                                        if isinstance(content, str):
                                            text_output = content
                                            logger.info(f"Text output from message content: {text_output[:200]}...")
                                            all_outputs.append(("text", text_output))
                                        elif isinstance(content, list) and len(content) > 0:
                                            # Content might be a list of text parts
                                            text_parts = [c.get('text', '') if isinstance(c, dict) else str(c) for c in content if c]
                                            text_output = ''.join(text_parts)
                                            logger.info(f"Text output from message content list: {text_output[:200]}...")
                                            all_outputs.append(("text", text_output))
                                elif hasattr(event.item, 'content') and event.item.content:
                                    # Sometimes the output is in content
                                    content = event.item.content
                                    if isinstance(content, str):
                                        text_output = content
                                        logger.info(f"Text output from content: {text_output[:200]}...")
                                        all_outputs.append(("text", text_output))
                                    elif isinstance(content, dict) and 'text' in content:
                                        text_output = content['text']
                                        logger.info(f"Text output from content.text: {text_output[:200]}...")
                                        all_outputs.append(("text", text_output))
                                else:
                                    # Log other item types for debugging
                                    logger.info(f"Other item type: {item_type}, item attributes: {dir(event.item)}")
                    
                    await asyncio.wait_for(collect_events(), timeout=120.0)  # 120 second timeout
                except asyncio.TimeoutError:
                    raise RuntimeError("Tool execution timed out after 120 seconds. The API may be taking longer than expected.")

                logger.info(f"Collected outputs: {len(all_outputs)} items (tool: {tool_payload is not None}, text: {text_output is not None})")

                # If we have tool output (from generate_toolkit), parse it
                if tool_payload:
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
                
                # If we have text output (direct agent response, not from a tool), parse it as JSON
                elif text_output:
                    logger.info(f"Parsing text output as JSON: {text_output[:200]}...")
                    try:
                        # Try to parse as JSON directly
                        parsed_result = json.loads(text_output)
                        logger.info(f"Parsed text output, keys: {list(parsed_result.keys()) if isinstance(parsed_result, dict) else 'N/A'}")
                        return parsed_result
                    except json.JSONDecodeError:
                        # If it's not valid JSON, try to extract JSON from the text
                        import re
                        json_match = re.search(r'\{.*\}', text_output, re.DOTALL)
                        if json_match:
                            parsed_result = json.loads(json_match.group())
                            logger.info(f"Extracted JSON from text, keys: {list(parsed_result.keys()) if isinstance(parsed_result, dict) else 'N/A'}")
                            return parsed_result
                        else:
                            raise ValueError(f"Could not parse JSON from agent text output: {text_output[:500]}")
                
                else:
                    logger.warning(f"Agent finished without emitting any output. All collected outputs: {all_outputs}")
                    # Try to get the final response from the agent's run result
                    try:
                        # Try different ways to get the result
                        if hasattr(result, 'get_final_result'):
                            final_result = result.get_final_result()
                            logger.info(f"Found final result via get_final_result(): {type(final_result)}")
                            if isinstance(final_result, str):
                                text_output = final_result
                            elif isinstance(final_result, dict):
                                return final_result
                        
                        # Try accessing result directly
                        if hasattr(result, 'result'):
                            final_result = result.result
                            logger.info(f"Found final result via result.result: {type(final_result)}")
                            if isinstance(final_result, str):
                                text_output = final_result
                            elif isinstance(final_result, dict):
                                return final_result
                        
                        # Try iterating through all items one more time
                        logger.info("Attempting to collect all items from result...")
                        all_items = []
                        try:
                            async for event in result.stream_events():
                                if hasattr(event, 'item'):
                                    all_items.append((event.item.type if hasattr(event.item, 'type') else 'unknown', str(event.item)[:200]))
                            logger.info(f"Collected {len(all_items)} items on second pass: {all_items}")
                        except Exception as e:
                            logger.warning(f"Could not iterate events again: {e}")
                            
                    except Exception as e:
                        logger.warning(f"Could not get final result: {e}")
                    
                    if not text_output:
                        raise RuntimeError(
                            f"Agent finished without emitting any output (neither tool output nor text output). "
                            f"Collected {len(all_outputs)} outputs. "
                            f"The agent may need to be instructed to return JSON directly, or it may be trying to call a tool that doesn't exist."
                        )
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
