import logging
import traceback
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

from mcp_agent import request_toolkit_async

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)
