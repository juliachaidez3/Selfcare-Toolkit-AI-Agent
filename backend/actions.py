"""
Action schema and executor for the Self-Care Agent.
Defines the structured actions that the agent can suggest and execute.
"""
from typing import Literal, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


# Action Type Definitions
class CreateCalendarBlockParams(BaseModel):
    duration_minutes: int = Field(..., ge=5, le=240, description="Duration in minutes (5-240)")
    time_window: Optional[str] = Field(
        default=None, description="When to schedule the block. Can be: 'now', 'in_1_hour', 'in_2_hours', 'today_morning', 'today_afternoon', 'today_evening', 'tomorrow_morning', 'tomorrow_afternoon', or ISO datetime format. If not provided, backend will automatically find the best free slot starting from 1 hour from now."
    )
    purpose: str = Field(..., description="Purpose of the calendar block")


class CreateJournalEntryParams(BaseModel):
    prompt_template: str = Field(..., description="Journal prompt to use")


class SuggestRetakeQuizParams(BaseModel):
    reason: Optional[str] = Field(None, description="Why the quiz is being suggested")


# Union type for all action params
ActionParams = CreateCalendarBlockParams | CreateJournalEntryParams | SuggestRetakeQuizParams


class AgentAction(BaseModel):
    """Structured action that the agent can suggest."""
    type: Literal["create_calendar_block", "create_journal_entry", "suggest_retake_quiz"] = Field(
        ..., description="Type of action"
    )
    message: str = Field(..., description="User-friendly message explaining the suggestion")
    requires_confirmation: bool = Field(True, description="Whether user must confirm before execution")
    params: Dict[str, Any] = Field(..., description="Action-specific parameters")


class AgentSuggestionsResponse(BaseModel):
    """Response containing agent suggestions."""
    actions: list[AgentAction] = Field(default_factory=list, description="List of suggested actions")


# Action Executor
async def execute_action(action: AgentAction, user_id: str, action_message: Optional[str] = None) -> Dict[str, Any]:
    """
    Execute a confirmed action.
    
    Args:
        action: The action to execute
        user_id: The user ID executing the action
        action_message: The original message shown to the user (for history)
        
    Returns:
        Dict with 'success', 'message', 'action_id' (for feedback), and optional 'data'
    """
    logger.info(f"Executing action {action.type} for user {user_id}")
    
    try:
        result = None
        if action.type == "create_calendar_block":
            result = await _execute_calendar_block(action.params, user_id)
        elif action.type == "create_journal_entry":
            result = await _execute_journal_entry(action.params, user_id)
        elif action.type == "suggest_retake_quiz":
            result = await _execute_retake_quiz(action.params, user_id)
        else:
            result = {
                "success": False,
                "message": f"Unknown action type: {action.type}"
            }
        
        # Add action_id for feedback tracking (frontend will generate this)
        # The frontend will store the action in agent_history and use the doc ID
        return result
    except Exception as e:
        logger.error(f"Error executing action {action.type}: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Failed to execute action: {str(e)}"
        }


async def _execute_calendar_block(params: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Execute calendar block creation using direct calendar service."""
    # Validate params
    try:
        calendar_params = CreateCalendarBlockParams(**params)
    except Exception as e:
        return {"success": False, "message": f"Invalid calendar block parameters: {str(e)}"}
    
    # Use direct calendar service to create the event
    try:
        from calendar_service import create_calendar_event
        
        # Create the event with the exact time_window provided
        result = await create_calendar_event(
            title=calendar_params.purpose,
            start_time=calendar_params.time_window,
            duration_minutes=calendar_params.duration_minutes,
            description="Self-care activity from toolkit",
            check_conflicts=True
        )
        
        if "error" in result:
            # Check if it's a conflict error
            if result.get("conflict"):
                return {
                    "success": False,
                    "message": result.get('error', 'Time slot conflicts with existing event'),
                    "conflict": True
                }
            return {
                "success": False,
                "message": f"Failed to create calendar event: {result.get('error', 'Unknown error')}"
            }
        elif "event_id" in result or "html_link" in result:
            # Successfully created event
            event_start = result.get("start", "")
            event_end = result.get("end", "")
            html_link = result.get("html_link", "")
            
            return {
                "success": True,
                "message": f"Calendar event '{calendar_params.purpose}' created successfully! Opening in a new tab...",
                "data": {
                    "event_id": result.get("event_id"),
                    "html_link": html_link,
                    "start_time": event_start,
                    "end_time": event_end,
                    "purpose": calendar_params.purpose,
                    "duration_minutes": calendar_params.duration_minutes
                }
            }
        
        # Fallback: if calendar service didn't work, log it
        logger.warning(f"Calendar service returned unexpected result: {result}")
        return {
            "success": False,
            "message": "Calendar event creation failed. Please check Google Calendar credentials."
        }
        
    except Exception as e:
        logger.error(f"Error calling calendar service: {e}", exc_info=True)
        return {
            "success": False,
            "message": f"Failed to create calendar event: {str(e)}"
        }


async def _execute_journal_entry(params: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Execute journal entry creation using MCP Google Docs tool."""
    try:
        journal_params = CreateJournalEntryParams(**params)
    except Exception as e:
        return {"success": False, "message": f"Invalid journal entry parameters: {str(e)}"}
    
    # Use MCP docs tool to create Google Doc
    try:
        from mcp_agent import _run_agent
        
        # Build prompt to call the docs_create_journal_entry tool
        # The prompt_template is already personalized by the agent based on user's quiz responses
        title = f"Self-Care Journal Entry - {datetime.now().strftime('%B %d, %Y')}"
        prompt = f"""Use the docs_create_journal_entry tool to create a journal entry document:
- Title: "{title}"
- Prompt template: "{journal_params.prompt_template}"
- User context: (leave empty, the prompt is already personalized)

Call the docs_create_journal_entry tool with title="{title}" and prompt_template="{journal_params.prompt_template}"."""
        
        # Call the agent with the docs tool available
        result = await _run_agent(prompt)
        
        # Parse the result
        if isinstance(result, dict):
            if "error" in result:
                return {
                    "success": False,
                    "message": f"Failed to create journal entry: {result.get('error', 'Unknown error')}"
                }
            elif "document_id" in result or "document_url" in result:
                # Successfully created or appended to document
                document_url = result.get("document_url", "")
                title = result.get("title", "Journal Entry")
                appended = result.get("appended", False)
                
                if appended:
                    message = f"New prompt added to today's journal entry! Click the link to continue writing."
                else:
                    message = f"Journal entry '{title}' created! Click the link to start writing."
                
                return {
                    "success": True,
                    "message": message,
                    "data": {
                        "document_id": result.get("document_id"),
                        "document_url": document_url,
                        "title": title,
                        "prompt": journal_params.prompt_template,
                        "appended": appended
                    }
                }
        
        # Fallback: if MCP tool didn't work
        logger.warning(f"Docs tool returned unexpected result: {result}")
        return {
            "success": False,
            "message": "Journal entry creation failed. Please check Google Docs API setup."
        }
        
    except Exception as e:
        logger.error(f"Error calling docs MCP tool: {e}", exc_info=True)
        # Fallback to simple logging
        journal_entry = {
            "user_id": user_id,
            "prompt": journal_params.prompt_template,
            "created_at": datetime.now().isoformat(),
            "content": ""
        }
        
        logger.info(f"Journal entry logged for user {user_id} (MCP tool unavailable): {journal_params.prompt_template[:50]}...")
        
        return {
            "success": True,
            "message": "Journal entry created. Note: Google Docs integration requires setup.",
            "data": {
                "journal_entry_id": f"journal_{user_id}_{int(datetime.now().timestamp())}",
                "prompt": journal_params.prompt_template,
                "note": "Google Docs not configured - entry logged only"
            }
        }


async def _execute_retake_quiz(params: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    """Execute quiz retake suggestion (just returns success, frontend handles navigation)."""
    logger.info(f"Quiz retake suggested for user {user_id}")
    
    return {
        "success": True,
        "message": "Ready to take the quiz!",
        "data": {
            "navigate_to_quiz": True
        }
    }

