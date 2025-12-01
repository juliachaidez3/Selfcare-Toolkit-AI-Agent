import logging
import traceback
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from mcp_agent import request_toolkit_async
from actions import AgentAction, execute_action
from agent_suggestions import generate_agent_suggestions
from calendar_journal import get_upcoming_calendar_events, get_recent_journal_entries

# Load .env file from backend directory or project root
load_dotenv()
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Self-Care Toolkit API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ToolkitRequest(BaseModel):
    struggle: str
    mood: str
    focus: str
    copingPreferences: list[str]
    energyLevel: str


class AgentSuggestionsRequest(BaseModel):
    """Request for agent suggestions - frontend provides user context."""
    lastQuiz: dict | None = None  # Last quiz data (struggle, mood, focus, etc.)
    toolkitCount: int = 0
    daysSinceLastQuiz: int | None = None
    latitude: float | None = None  # Optional location for weather-based suggestions
    longitude: float | None = None  # Optional location for weather-based suggestions
    userProfile: dict | None = None  # User preferences, likes, dislikes, constraints
    recentActions: list[dict] | None = None  # Last 7 actions with outcomes
    actionStats: dict | None = None  # Action statistics (acceptance rates, ratings)


class ExecuteActionRequest(BaseModel):
    """Request to execute a confirmed action."""
    action: dict  # AgentAction as dict
    userId: str


@app.get("/")
async def root():
    return {"message": "Self-Care Toolkit API"}


@app.post("/api/toolkit")
async def toolkit(request: ToolkitRequest):
    try:
        logger.info(f"Received toolkit request: struggle={request.struggle}, mood={request.mood}")
        result = await request_toolkit_async(
            struggle=request.struggle,
            mood=request.mood,
            focus=request.focus,
            coping_preferences=request.copingPreferences,
            energy_level=request.energyLevel,
        )
        logger.info(f"Toolkit generated successfully: {len(result.get('items', []))} items")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        error_msg = str(exc)
        error_trace = traceback.format_exc()
        logger.error(f"Error in /api/toolkit: {error_msg}\n{error_trace}")
        # Return detailed error message for frontend
        raise HTTPException(
            status_code=500, 
            detail=error_msg
        )


@app.post("/api/agent_suggestions")
async def agent_suggestions(request: AgentSuggestionsRequest):
    """Generate personalized agent suggestions based on user context."""
    try:
        logger.info(f"Received agent suggestions request: toolkitCount={request.toolkitCount}, daysSinceLastQuiz={request.daysSinceLastQuiz}, location=({request.latitude}, {request.longitude})")
        
        result = await generate_agent_suggestions(
            last_quiz=request.lastQuiz,
            toolkit_count=request.toolkitCount,
            days_since_last_quiz=request.daysSinceLastQuiz,
            latitude=request.latitude,
            longitude=request.longitude,
            user_profile=request.userProfile,
            recent_actions=request.recentActions,
            action_stats=request.actionStats
        )
        
        logger.info(f"Generated {len(result.actions)} agent suggestions")
        
        # Log the actual response being sent to frontend
        response_dict = result.dict()
        for idx, action in enumerate(response_dict.get('actions', [])):
            if action.get('type') == 'create_calendar_block':
                logger.info(f"[Response] Calendar action {idx + 1} time_window: {action.get('params', {}).get('time_window', 'NOT_SET')}")
        
        return response_dict
    except Exception as exc:
        error_msg = str(exc)
        error_trace = traceback.format_exc()
        logger.error(f"Error in /api/agent_suggestions: {error_msg}\n{error_trace}")
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )


@app.post("/api/execute_action")
async def execute_action_endpoint(request: ExecuteActionRequest):
    """Execute a confirmed action."""
    try:
        logger.info(f"Executing action {request.action.get('type')} for user {request.userId}")
        
        # Validate action
        try:
            action = AgentAction(**request.action)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action format: {str(e)}"
            )
        
        # Execute the action
        result = await execute_action(action, request.userId)
        
        logger.info(f"Action execution result: success={result.get('success')}")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        error_msg = str(exc)
        error_trace = traceback.format_exc()
        logger.error(f"Error in /api/execute_action: {error_msg}\n{error_trace}")
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )


@app.get("/api/calendar_events")
async def get_calendar_events():
    """Get upcoming calendar events created by the Self-Care Toolkit."""
    try:
        events = await get_upcoming_calendar_events(max_results=20)
        logger.info(f"Fetched {len(events)} upcoming calendar events")
        return {"events": events}
    except Exception as exc:
        error_msg = str(exc)
        error_trace = traceback.format_exc()
        logger.error(f"Error in /api/calendar_events: {error_msg}\n{error_trace}")
        # Return empty list on error instead of raising exception
        return {"events": []}


@app.get("/api/free_slots")
async def get_free_slots(start_date: str, end_date: str, duration_minutes: int = 30):
    """Get free time slots in the user's calendar."""
    try:
        from calendar_service import get_free_slots as get_free_slots_service
        slots = await get_free_slots_service(start_date, end_date, duration_minutes)
        logger.info(f"Fetched {len(slots)} free slots")
        return {"free_slots": slots}
    except Exception as exc:
        error_msg = str(exc)
        error_trace = traceback.format_exc()
        logger.error(f"Error in /api/free_slots: {error_msg}\n{error_trace}")
        return {"free_slots": []}


@app.get("/api/journal_entries")
async def get_journal_entries():
    """Get recent journal entries created by the Self-Care Toolkit."""
    try:
        entries = await get_recent_journal_entries(max_results=3)
        logger.info(f"Fetched {len(entries)} recent journal entries")
        return {"entries": entries}
    except Exception as exc:
        error_msg = str(exc)
        error_trace = traceback.format_exc()
        logger.error(f"Error in /api/journal_entries: {error_msg}\n{error_trace}")
        # Return empty list on error instead of raising exception
        return {"entries": []}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
