import json
import os
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import urllib.request
import urllib.parse

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from openai import OpenAI

# Google Calendar imports
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    GOOGLE_CALENDAR_AVAILABLE = False
    import sys
    print("WARNING: Google Calendar libraries not available. Calendar tools will not work.", file=sys.stderr)

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

# Google Calendar and Docs setup
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive.file'  # For creating files
]
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"


def get_google_credentials():
    """Get authenticated Google credentials for Calendar and Docs."""
    if not GOOGLE_CALENDAR_AVAILABLE:
        raise RuntimeError("Google API libraries not installed")
    
    creds = None
    # The file token.json stores the user's access and refresh tokens
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        except ValueError as e:
            # If token.json is corrupted or missing refresh_token, delete it and re-authenticate
            import sys
            print(f"WARNING: token.json is invalid ({e}). Deleting and re-authenticating...", file=sys.stderr)
            TOKEN_FILE.unlink()
            creds = None
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise RuntimeError(
                    f"Google API credentials not found. Please download credentials.json from "
                    f"Google Cloud Console and place it at {CREDENTIALS_FILE}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            # Configure OAuth to request offline access (refresh token)
            flow.redirect_uri = 'http://localhost:8080/'
            # Use a fixed port (8080) for web application OAuth clients
            # This requires adding http://localhost:8080/ to authorized redirect URIs
            # Note: The trailing slash is important - Google requires exact match
            import sys
            print("Starting OAuth flow on port 8080...", file=sys.stderr)
            print("Make sure http://localhost:8080/ is in your authorized redirect URIs", file=sys.stderr)
            print("Requesting offline access to get refresh token...", file=sys.stderr)
            creds = flow.run_local_server(
                port=8080, 
                open_browser=True,
                authorization_prompt_message='Please visit this URL to authorize this application: {url}',
                success_message='The authentication flow has completed. You may close this window.'
            )
        
        # Save the credentials for the next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
    
    return creds


def get_calendar_service():
    """Get authenticated Google Calendar service."""
    creds = get_google_credentials()
    return build('calendar', 'v3', credentials=creds)


def get_docs_service():
    """Get authenticated Google Docs service."""
    creds = get_google_credentials()
    return build('docs', 'v1', credentials=creds)


def get_drive_service():
    """Get authenticated Google Drive service."""
    creds = get_google_credentials()
    return build('drive', 'v3', credentials=creds)


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


@mcp.tool()
def calendar_get_free_slots(
    start_date: str,
    end_date: str,
    duration_minutes: int = 30,
) -> str:
    """
    Get free time slots in the user's Google Calendar.
    
    Args:
        start_date: Start date in ISO format (YYYY-MM-DD) or relative like "today", "tomorrow"
        end_date: End date in ISO format (YYYY-MM-DD) or relative like "today", "tomorrow"
        duration_minutes: Minimum duration of free slot in minutes (default: 30)
    
    Returns:
        JSON string with free slots: {"free_slots": [{"start": "ISO datetime", "end": "ISO datetime"}, ...]}
    """
    if not GOOGLE_CALENDAR_AVAILABLE:
        return json.dumps({"error": "Google Calendar not available", "free_slots": []})
    
    try:
        service = get_calendar_service()
        
        # Parse dates
        now = datetime.now()
        if start_date.lower() == "today":
            start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif start_date.lower() == "tomorrow":
            start_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=now.tzinfo)
        
        if end_date.lower() == "today":
            end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
        elif end_date.lower() == "tomorrow":
            end_dt = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
        else:
            end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=now.tzinfo)
        
        # Get calendar events
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_dt.isoformat(),
            timeMax=end_dt.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # Find free slots
        free_slots = []
        current_time = start_dt
        
        for event in events:
            event_start_str = event['start'].get('dateTime', event['start'].get('date'))
            event_end_str = event['end'].get('dateTime', event['end'].get('date'))
            
            # Parse event times
            if 'T' in event_start_str:
                event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00'))
            else:
                event_start = datetime.fromisoformat(event_start_str)
                event_start = event_start.replace(tzinfo=now.tzinfo)
            
            if 'T' in event_end_str:
                event_end = datetime.fromisoformat(event_end_str.replace('Z', '+00:00'))
            else:
                event_end = datetime.fromisoformat(event_end_str)
                event_end = event_end.replace(tzinfo=now.tzinfo)
            
            # Check if there's a gap before this event
            if current_time < event_start:
                gap_duration = (event_start - current_time).total_seconds() / 60
                if gap_duration >= duration_minutes:
                    free_slots.append({
                        "start": current_time.isoformat(),
                        "end": event_start.isoformat(),
                        "duration_minutes": int(gap_duration)
                    })
            
            # Move current time to end of event
            if event_end > current_time:
                current_time = event_end
        
        # Check for free time after last event
        if current_time < end_dt:
            gap_duration = (end_dt - current_time).total_seconds() / 60
            if gap_duration >= duration_minutes:
                free_slots.append({
                    "start": current_time.isoformat(),
                    "end": end_dt.isoformat(),
                    "duration_minutes": int(gap_duration)
                })
        
        return json.dumps({"free_slots": free_slots}, indent=2)
    
    except Exception as e:
        import sys
        error_msg = f"Error getting free slots: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return json.dumps({"error": error_msg, "free_slots": []})


@mcp.tool()
def calendar_create_event(
    title: str,
    start_time: str,
    duration_minutes: int,
    description: Optional[str] = None,
) -> str:
    """
    Create an event in the user's Google Calendar.
    
    Args:
        title: Event title
        start_time: Start time in ISO format (YYYY-MM-DDTHH:MM:SS) or relative like "today_afternoon"
        duration_minutes: Duration in minutes
        description: Optional event description
    
    Returns:
        JSON string with event details: {"event_id": "...", "html_link": "...", "start": "...", "end": "..."}
    """
    if not GOOGLE_CALENDAR_AVAILABLE:
        return json.dumps({"error": "Google Calendar not available"})
    
    try:
        service = get_calendar_service()
        
        # Parse start time
        # Use datetime.now() with timezone awareness
        from datetime import timezone
        now = datetime.now(timezone.utc) if datetime.now().tzinfo is None else datetime.now()
        # If still no timezone, use local timezone
        if now.tzinfo is None:
            # Get local timezone offset
            import time
            offset_seconds = -time.timezone if time.daylight == 0 else -time.altzone
            now = now.replace(tzinfo=timezone(timedelta(seconds=offset_seconds)))
        
        # Handle user-friendly time formats
        if start_time == "now":
            # Start immediately (round to next 5 minutes, minimum 5 minutes from now)
            start_dt = now.replace(second=0, microsecond=0)
            minutes = start_dt.minute
            # Round up to next 5-minute mark
            rounded_minutes = ((minutes // 5) + 1) * 5
            if rounded_minutes >= 60:
                # Move to next hour
                start_dt = (start_dt + timedelta(hours=1)).replace(minute=0)
            else:
                start_dt = start_dt.replace(minute=rounded_minutes)
            # Ensure it's at least 5 minutes from now
            if start_dt <= now:
                start_dt = now + timedelta(minutes=5)
                start_dt = start_dt.replace(second=0, microsecond=0)
        elif start_time == "in_1_hour":
            start_dt = now + timedelta(hours=1)
            start_dt = start_dt.replace(second=0, microsecond=0)
        elif start_time == "in_2_hours":
            start_dt = now + timedelta(hours=2)
            start_dt = start_dt.replace(second=0, microsecond=0)
        elif start_time == "today_morning":
            start_dt = now.replace(hour=9, minute=0, second=0, microsecond=0)
            # If 9 AM has already passed today, move to tomorrow
            if start_dt <= now:
                start_dt = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        elif start_time == "today_afternoon":
            start_dt = now.replace(hour=14, minute=0, second=0, microsecond=0)
            # If 2 PM has already passed today, move to tomorrow afternoon
            if start_dt <= now:
                start_dt = (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        elif start_time == "today_evening":
            start_dt = now.replace(hour=19, minute=0, second=0, microsecond=0)
            # If 7 PM has already passed today, move to tomorrow evening
            if start_dt <= now:
                start_dt = (now + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
        elif start_time == "tomorrow_morning":
            start_dt = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        elif start_time == "tomorrow_afternoon":
            start_dt = (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        else:
            # Try to parse as ISO format or datetime-local format
            try:
                # Handle datetime-local format (YYYY-MM-DDTHH:MM)
                if 'T' in start_time and len(start_time) == 16:
                    # Add seconds if missing
                    start_time = start_time + ':00'
                start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=now.tzinfo)
                # If parsed time is in the past, move to next day at same time
                if start_dt < now:
                    start_dt = start_dt + timedelta(days=1)
            except ValueError:
                raise ValueError(f"Invalid start_time format: {start_time}. Supported formats: 'now', 'in_1_hour', 'in_2_hours', 'today_morning', 'today_afternoon', 'today_evening', 'tomorrow_morning', 'tomorrow_afternoon', or ISO datetime format.")
        
        # Final safety check: ensure start_dt is in the future (at least 5 minutes from now)
        # Also ensure timezone is consistent
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=now.tzinfo)
        
        if start_dt <= now:
            # If somehow still in the past or exactly now, add 5 minutes to current time
            start_dt = now + timedelta(minutes=5)
            start_dt = start_dt.replace(second=0, microsecond=0)
            # Ensure timezone is set
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=now.tzinfo)
        
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        # Ensure end_dt has same timezone
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=now.tzinfo)
        
        # Get timezone string for Google Calendar
        # Google Calendar expects IANA timezone names like 'America/New_York'
        tz_str = 'America/New_York'  # Default
        if now.tzinfo:
            # Try to get timezone name
            tz_name = str(now.tzinfo)
            # Map common timezone strings to IANA names
            if 'UTC' in tz_name or 'GMT' in tz_name:
                tz_str = 'UTC'
            elif 'EST' in tz_name or 'EDT' in tz_name:
                tz_str = 'America/New_York'
            elif 'PST' in tz_name or 'PDT' in tz_name:
                tz_str = 'America/Los_Angeles'
            elif 'CST' in tz_name or 'CDT' in tz_name:
                tz_str = 'America/Chicago'
            else:
                # Try to extract from tzinfo
                try:
                    # For timezone objects, try to get the zone name
                    if hasattr(now.tzinfo, 'zone'):
                        tz_str = now.tzinfo.zone
                    elif hasattr(now.tzinfo, 'key'):
                        tz_str = now.tzinfo.key
                except:
                    pass
        
        # Create event
        event = {
            'summary': title,
            'description': description or '',
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': tz_str,
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': tz_str,
            },
        }
        
        event_result = service.events().insert(calendarId='primary', body=event).execute()
        
        return json.dumps({
            "event_id": event_result.get('id'),
            "html_link": event_result.get('htmlLink'),
            "start": event_result['start'].get('dateTime', event_result['start'].get('date')),
            "end": event_result['end'].get('dateTime', event_result['end'].get('date')),
            "title": event_result.get('summary', title)
        }, indent=2)
    
    except Exception as e:
        import sys
        error_msg = f"Error creating calendar event: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return json.dumps({"error": error_msg})


@mcp.tool()
def docs_create_journal_entry(
    title: str,
    prompt_template: str,
    user_context: Optional[str] = None,
) -> str:
    """
    Create a new Google Doc for journaling with a prompt template, or append to existing entry for today.
    
    Args:
        title: Title for the journal entry document (typically "Self-Care Journal Entry - {Month Day, Year}")
        prompt_template: The journal prompt/question to write in the document
        user_context: Optional context about the user (struggle, mood, etc.) to personalize the prompt
    
    Returns:
        JSON string with document details: {"document_id": "...", "document_url": "...", "title": "...", "appended": true/false}
    """
    if not GOOGLE_CALENDAR_AVAILABLE:
        return json.dumps({"error": "Google API libraries not installed"})
    
    try:
        docs_service = get_docs_service()
        drive_service = get_drive_service()
        
        # Check if a document with this title already exists today
        # Search for files with the exact title
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = now.replace(hour=23, minute=59, second=59, microsecond=999)
        
        # Search for documents with matching title
        try:
            query = f"name='{title}' and mimeType='application/vnd.google-apps.document' and trashed=false"
            results = drive_service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name, createdTime)',
                orderBy='createdTime desc'
            ).execute()
        except HttpError as e:
            if e.resp.status == 403 and 'accessNotConfigured' in str(e):
                error_msg = (
                    "Google Drive API is not enabled. Please enable it at: "
                    "https://console.developers.google.com/apis/api/drive.googleapis.com/overview?project=1051858206996"
                )
                import sys
                print(f"ERROR: {error_msg}", file=sys.stderr)
                return json.dumps({"error": error_msg})
            else:
                # For other errors, fall through to create new document
                import sys
                print(f"WARNING: Could not search for existing documents: {e}. Creating new document.", file=sys.stderr)
                results = {'files': []}
        
        existing_doc = None
        for file in results.get('files', []):
            # Check if file was created today
            # Google Drive API returns times in RFC 3339 format (ISO 8601)
            created_time_str = file['createdTime']
            # Parse the time (may have 'Z' for UTC or timezone offset)
            if created_time_str.endswith('Z'):
                created_time = datetime.fromisoformat(created_time_str.replace('Z', '+00:00'))
            else:
                created_time = datetime.fromisoformat(created_time_str)
            
            # Convert to local time for comparison (remove timezone for comparison)
            created_local = created_time.replace(tzinfo=None)
            if today_start <= created_local <= today_end:
                existing_doc = file
                break
        
        if existing_doc:
            # Append to existing document
            document_id = existing_doc['id']
            
            # Get current document to find end index
            doc = docs_service.documents().get(documentId=document_id).execute()
            end_index = doc.get('body', {}).get('content', [{}])[-1].get('endIndex', 1)
            
            # Prepare new content to append
            new_content = "\n\n" + "─" * 50 + "\n\n"
            if user_context:
                new_content += f"Context: {user_context}\n\n"
            new_content += f"Journal Prompt:\n{prompt_template}\n\n"
            new_content += "─" * 50 + "\n\n"
            new_content += "Your response:\n\n"
            
            # Insert new content at the end
            requests = [
                {
                    'insertText': {
                        'location': {
                            'index': end_index - 1,  # Insert before the last newline
                        },
                        'text': new_content
                    }
                }
            ]
            
            # Find and format "Journal Prompt:" labels
            # Get the full document text to find prompt positions
            full_text = ""
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    for para_elem in element['paragraph'].get('elements', []):
                        if 'textRun' in para_elem:
                            full_text += para_elem['textRun'].get('content', '')
            
            # Find all "Journal Prompt:" occurrences and format them
            search_text = full_text + new_content
            prompt_positions = []
            search_pos = 0
            while True:
                pos = search_text.find('Journal Prompt:', search_pos)
                if pos == -1:
                    break
                prompt_positions.append(pos)
                search_pos = pos + 1
            
            # Format the new "Journal Prompt:" label
            if prompt_positions:
                # The new prompt is at the last position
                new_prompt_start = len(full_text) + new_content.find('Journal Prompt:')
                new_prompt_end = new_prompt_start + len('Journal Prompt:')
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': new_prompt_start + 1,  # +1 because index is 1-based
                            'endIndex': new_prompt_end + 1
                        },
                        'textStyle': {
                            'bold': True
                        },
                        'fields': 'bold'
                    }
                })
            
            # Apply updates
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            
            document_url = f"https://docs.google.com/document/d/{document_id}/edit"
            
            return json.dumps({
                "document_id": document_id,
                "document_url": document_url,
                "title": title,
                "appended": True,
                "message": f"New prompt added to today's journal entry! You can continue writing at: {document_url}"
            }, indent=2)
        else:
            # Create a new document
            document_content = f"{title}\n\n"
            
            if user_context:
                document_content += f"Context: {user_context}\n\n"
            
            document_content += f"Journal Prompt:\n{prompt_template}\n\n"
            document_content += "─" * 50 + "\n\n"
            document_content += "Your response:\n\n"
            
            # Create a new Google Doc
            document = {
                'title': title
            }
            
            doc = docs_service.documents().create(body=document).execute()
            document_id = doc.get('documentId')
            
            # Write content to the document
            insert_request = {
                'insertText': {
                    'location': {
                        'index': 1,
                    },
                    'text': document_content
                }
            }
            
            # Execute insert first
            docs_service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': [insert_request]}
            ).execute()
            
            # Then format the document
            format_requests = []
            
            # Format the title as a heading (first line)
            title_end = len(title) + 1  # +1 for newline
            format_requests.append({
                'updateParagraphStyle': {
                    'range': {
                        'startIndex': 1,
                        'endIndex': title_end
                    },
                    'paragraphStyle': {
                        'namedStyleType': 'HEADING_1'
                    },
                    'fields': 'namedStyleType'
                }
            })
            
            # Format "Journal Prompt:" as bold
            prompt_label_start = document_content.find('Journal Prompt:')
            if prompt_label_start > 0:
                prompt_label_end = prompt_label_start + len('Journal Prompt:')
                format_requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': prompt_label_start + 1,  # +1 because index is 1-based after insert
                            'endIndex': prompt_label_end + 1
                        },
                        'textStyle': {
                            'bold': True
                        },
                        'fields': 'bold'
                    }
                })
            
            # Apply formatting
            if format_requests:
                docs_service.documents().batchUpdate(
                    documentId=document_id,
                    body={'requests': format_requests}
                ).execute()
            
            # Get the document URL
            document_url = f"https://docs.google.com/document/d/{document_id}/edit"
            
            return json.dumps({
                "document_id": document_id,
                "document_url": document_url,
                "title": title,
                "appended": False,
                "message": f"Journal entry created! You can start writing at: {document_url}"
            }, indent=2)
    
    except Exception as e:
        import sys
        error_msg = f"Error creating journal entry: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return json.dumps({"error": error_msg})


@mcp.tool()
def weather_get_forecast(
    latitude: float,
    longitude: float,
    days: int = 1,
) -> str:
    """
    Get weather forecast for a location using Open-Meteo API.
    
    Args:
        latitude: Latitude of the location (e.g., 40.7128 for New York)
        longitude: Longitude of the location (e.g., -74.0060 for New York)
        days: Number of days to forecast (default: 1, max: 7)
    
    Returns:
        JSON string with weather summary including:
        - current_weather: temperature, condition, wind
        - today_forecast: high/low, precipitation, conditions
        - suggestions: weather-appropriate activity suggestions
    """
    try:
        # Clamp days to valid range
        days = max(1, min(7, days))
        
        # Build Open-Meteo API URL
        base_url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "hourly": "temperature_2m,precipitation_probability,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
            "timezone": "auto",
            "forecast_days": days
        }
        
        url = f"{base_url}?{urllib.parse.urlencode(params)}"
        
        # Make API request
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode())
        
        # Parse current weather
        current = data.get("current", {})
        current_temp = current.get("temperature_2m", 0)
        weather_code = current.get("weather_code", 0)
        wind_speed = current.get("wind_speed_10m", 0)
        humidity = current.get("relative_humidity_2m", 0)
        
        # Parse daily forecast (today)
        daily = data.get("daily", {})
        daily_times = daily.get("time", [])
        daily_max_temp = daily.get("temperature_2m_max", [])
        daily_min_temp = daily.get("temperature_2m_min", [])
        daily_precip = daily.get("precipitation_sum", [])
        daily_precip_prob = daily.get("precipitation_probability_max", [])
        daily_weather_code = daily.get("weather_code", [])
        
        # Get today's forecast
        today_max = daily_max_temp[0] if daily_max_temp else current_temp
        today_min = daily_min_temp[0] if daily_min_temp else current_temp
        today_precip = daily_precip[0] if daily_precip else 0
        today_precip_prob = daily_precip_prob[0] if daily_precip_prob else 0
        today_weather_code = daily_weather_code[0] if daily_weather_code else weather_code
        
        # Weather code interpretation (WMO codes)
        def interpret_weather_code(code: int) -> str:
            if code == 0:
                return "Clear sky"
            elif code in [1, 2, 3]:
                return "Partly cloudy"
            elif code in [45, 48]:
                return "Foggy"
            elif code in [51, 53, 55]:
                return "Drizzle"
            elif code in [56, 57]:
                return "Freezing drizzle"
            elif code in [61, 63, 65]:
                return "Rain"
            elif code in [66, 67]:
                return "Freezing rain"
            elif code in [71, 73, 75]:
                return "Snow"
            elif code == 77:
                return "Snow grains"
            elif code in [80, 81, 82]:
                return "Rain showers"
            elif code in [85, 86]:
                return "Snow showers"
            elif code == 95:
                return "Thunderstorm"
            elif code in [96, 99]:
                return "Thunderstorm with hail"
            else:
                return "Unknown"
        
        current_condition = interpret_weather_code(weather_code)
        today_condition = interpret_weather_code(today_weather_code)
        
        # Generate activity suggestions based on weather
        suggestions = []
        is_nice_weather = (weather_code in [0, 1, 2] and today_precip_prob < 30 and current_temp > 10)
        is_rainy = (today_precip_prob > 50 or weather_code in [61, 63, 65, 66, 67, 80, 81, 82])
        is_cold = (current_temp < 5 or today_min < 5)
        is_hot = (current_temp > 30 or today_max > 30)
        
        if is_nice_weather and not is_cold:
            suggestions.append("Great weather for outdoor activities like walking, exercise, or spending time in nature")
        elif is_rainy:
            suggestions.append("Rainy weather - consider indoor activities like journaling, reading, or meditation")
        elif is_cold:
            suggestions.append("Cold weather - cozy indoor activities would be best")
        elif is_hot:
            suggestions.append("Hot weather - stay hydrated and consider early morning or evening activities")
        else:
            suggestions.append("Moderate weather conditions - good for both indoor and outdoor activities")
        
        # Build summary
        result = {
            "location": {
                "latitude": latitude,
                "longitude": longitude
            },
            "current_weather": {
                "temperature_celsius": round(current_temp, 1),
                "condition": current_condition,
                "wind_speed_kmh": round(wind_speed, 1),
                "humidity_percent": round(humidity, 0),
                "weather_code": weather_code
            },
            "today_forecast": {
                "high_celsius": round(today_max, 1),
                "low_celsius": round(today_min, 1),
                "condition": today_condition,
                "precipitation_mm": round(today_precip, 1),
                "precipitation_probability_percent": round(today_precip_prob, 0),
                "weather_code": today_weather_code
            },
            "activity_suggestions": suggestions,
            "summary": f"Current: {round(current_temp, 1)}°C, {current_condition}. Today: {round(today_min, 1)}-{round(today_max, 1)}°C, {today_condition}. Precipitation chance: {round(today_precip_prob, 0)}%."
        }
        
        return json.dumps(result, indent=2)
    
    except urllib.error.URLError as e:
        import sys
        error_msg = f"Error fetching weather data: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return json.dumps({"error": error_msg})
    except Exception as e:
        import sys
        error_msg = f"Error getting weather forecast: {str(e)}"
        print(f"ERROR: {error_msg}", file=sys.stderr)
        return json.dumps({"error": error_msg})


if __name__ == "__main__":
    try:
        mcp.run(transport="stdio")
    except Exception as e:
        import sys
        import traceback
        print(f"ERROR in MCP server: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
