"""
Backend functions to fetch calendar events and journal entries created by the Self-Care Toolkit.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import json

logger = logging.getLogger(__name__)

# Google Calendar imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_APIS_AVAILABLE = True
except ImportError:
    GOOGLE_APIS_AVAILABLE = False
    logger.warning("Google API libraries not available. Calendar and journal features will not work.")

# Google Calendar and Docs setup
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/documents.readonly',
    'https://www.googleapis.com/auth/drive.readonly'
]

CREDENTIALS_FILE = None
TOKEN_FILE = None

def setup_google_paths():
    """Set up paths to credentials and token files."""
    global CREDENTIALS_FILE, TOKEN_FILE
    from pathlib import Path
    # Get project root (parent of backend directory)
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
    TOKEN_FILE = PROJECT_ROOT / "token.json"

def get_google_credentials():
    """Get authenticated Google credentials."""
    if not GOOGLE_APIS_AVAILABLE:
        raise RuntimeError("Google API libraries not installed")
    
    setup_google_paths()
    
    creds = None
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except ValueError:
            logger.warning("token.json is invalid. Re-authentication needed.")
            creds = None
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                logger.error(f"Error refreshing credentials: {e}")
                creds = None
        
        if not creds:
            raise RuntimeError("Google credentials not found. Please authenticate first.")
    
    # Save refreshed credentials
    if TOKEN_FILE:
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    
    return creds

def get_calendar_service():
    """Get Google Calendar service."""
    creds = get_google_credentials()
    return build('calendar', 'v3', credentials=creds)

def get_drive_service():
    """Get Google Drive service."""
    creds = get_google_credentials()
    return build('drive', 'v3', credentials=creds)

async def get_upcoming_calendar_events(max_results: int = 20) -> List[Dict[str, Any]]:
    """
    Fetch upcoming calendar events that were created by the Self-Care Toolkit.
    
    Events are identified by:
    - Description containing "Self-care activity from toolkit"
    - Or by checking agent_history (if we store event IDs there)
    
    Returns:
        List of event dictionaries with: id, title, start, end, html_link
    """
    if not GOOGLE_APIS_AVAILABLE:
        logger.warning("Google APIs not available, returning empty calendar events list")
        return []
    
    try:
        service = get_calendar_service()
        now = datetime.now(timezone.utc) if datetime.now().tzinfo is None else datetime.now()
        if now.tzinfo is None:
            import time
            offset_seconds = -time.timezone if time.daylight == 0 else -time.altzone
            now = now.replace(tzinfo=timezone(timedelta(seconds=offset_seconds)))
        
        # Get events from now onwards
        time_min = now.isoformat()
        # Look ahead 30 days
        time_max = (now + timedelta(days=30)).isoformat()
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results * 2,  # Get more to filter
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # Filter for toolkit events
        toolkit_events = []
        for event in events:
            description = event.get('description', '')
            summary = event.get('summary', '')
            
            # Check if it's a toolkit event
            is_toolkit_event = (
                'Self-care activity from toolkit' in description or
                'Self-care' in summary or
                'self-care' in summary.lower()
            )
            
            if is_toolkit_event:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                toolkit_events.append({
                    'id': event.get('id'),
                    'title': summary,
                    'start': start,
                    'end': end,
                    'html_link': event.get('htmlLink', ''),
                    'description': description
                })
                
                if len(toolkit_events) >= max_results:
                    break
        
        return toolkit_events
    
    except RuntimeError as e:
        # Credentials not found or not authenticated
        logger.warning(f"Google Calendar credentials not available: {e}")
        return []
    except Exception as e:
        logger.error(f"Error fetching calendar events: {e}", exc_info=True)
        return []

async def get_recent_journal_entries(max_results: int = 3) -> List[Dict[str, Any]]:
    """
    Fetch recent journal entries created by the Self-Care Toolkit.
    
    Journal entries are identified by title pattern: "Self-Care Journal Entry - {date}"
    
    Returns:
        List of journal entry dictionaries with: id, title, created_time, document_url
    """
    if not GOOGLE_APIS_AVAILABLE:
        logger.warning("Google APIs not available, returning empty journal entries list")
        return []
    
    try:
        drive_service = get_drive_service()
        
        # Search for documents with title starting with "Self-Care Journal Entry"
        query = "name contains 'Self-Care Journal Entry' and mimeType='application/vnd.google-apps.document' and trashed=false"
        
        results = drive_service.files().list(
            q=query,
            spaces='drive',
            fields='files(id, name, createdTime, webViewLink)',
            orderBy='createdTime desc',
            pageSize=max_results
        ).execute()
        
        journal_entries = []
        for file in results.get('files', []):
            journal_entries.append({
                'id': file.get('id'),
                'title': file.get('name'),
                'created_time': file.get('createdTime'),
                'document_url': file.get('webViewLink', '')
            })
        
        return journal_entries
    
    except RuntimeError as e:
        # Credentials not found or not authenticated
        logger.warning(f"Google Drive credentials not available: {e}")
        return []
    except HttpError as e:
        if e.resp.status == 403:
            logger.warning("Google Drive API access denied. Please check permissions.")
        else:
            logger.error(f"Error fetching journal entries: {e}", exc_info=True)
        return []
    except Exception as e:
        logger.error(f"Error fetching journal entries: {e}", exc_info=True)
        return []

