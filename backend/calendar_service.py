"""
Direct calendar service that calls MCP calendar tools without going through the agent.
This provides more reliable and predictable calendar event creation.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Import Google Calendar functions directly from the MCP server module
try:
    import sys
    from pathlib import Path
    
    # Add the MCP server directory to the path
    PROJECT_ROOT = Path(__file__).resolve().parents[1]
    MCP_DIR = PROJECT_ROOT / "selfcare-mcp-agent" / "mcp-server"
    sys.path.insert(0, str(MCP_DIR))
    
    # Import the MCP server module
    import importlib.util
    spec = importlib.util.spec_from_file_location("selfcare_mcp", MCP_DIR / "selfcare_mcp.py")
    selfcare_mcp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(selfcare_mcp)
    
    get_calendar_service = selfcare_mcp.get_calendar_service
    get_google_credentials = selfcare_mcp.get_google_credentials
    GOOGLE_CALENDAR_AVAILABLE = selfcare_mcp.GOOGLE_CALENDAR_AVAILABLE
    
    CALENDAR_AVAILABLE = GOOGLE_CALENDAR_AVAILABLE
except (ImportError, AttributeError) as e:
    logger.warning(f"Could not import calendar functions: {e}")
    CALENDAR_AVAILABLE = False


async def get_free_slots(
    start_date: str,
    end_date: str,
    duration_minutes: int = 30
) -> List[Dict[str, Any]]:
    """
    Get free time slots in the user's Google Calendar.
    
    Args:
        start_date: Start date in ISO format (YYYY-MM-DD) or relative like "today", "tomorrow"
        end_date: End date in ISO format (YYYY-MM-DD) or relative like "today", "tomorrow"
        duration_minutes: Minimum duration of free slot in minutes (default: 30)
    
    Returns:
        List of free slots: [{"start": "ISO datetime", "end": "ISO datetime", "duration_minutes": int}, ...]
    """
    if not CALENDAR_AVAILABLE:
        logger.warning("Google Calendar not available")
        return []
    
    try:
        service = get_calendar_service()
        
        # Parse dates - use Pacific time as default
        try:
            from zoneinfo import ZoneInfo
            pacific_tz = ZoneInfo('America/Los_Angeles')
            now = datetime.now(pacific_tz)
        except (ImportError, Exception):
            # Fallback to UTC if zoneinfo not available
            now = datetime.now(timezone.utc) if datetime.now().tzinfo is None else datetime.now()
            if now.tzinfo is None:
                import time
                offset_seconds = -time.timezone if time.daylight == 0 else -time.altzone
                now = now.replace(tzinfo=timezone(timedelta(seconds=offset_seconds)))
        
        if start_date.lower() == "today":
            start_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif start_date.lower() == "tomorrow":
            start_dt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            try:
                # Try parsing as ISO datetime first (includes time)
                start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
                if start_dt.tzinfo is None:
                    start_dt = start_dt.replace(tzinfo=now.tzinfo)
                # If the parsed datetime is in the past, use current time instead
                if start_dt < now:
                    start_dt = now
            except ValueError:
                try:
                    # Try parsing as date only
                    start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=now.tzinfo)
                    start_dt = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                except ValueError:
                    # If all parsing fails, default to now
                    logger.warning(f"Could not parse start_date '{start_date}', using current time")
                    start_dt = now
        
        if end_date.lower() == "today":
            end_dt = now.replace(hour=23, minute=59, second=59, microsecond=0)
        elif end_date.lower() == "tomorrow":
            end_dt = (now + timedelta(days=1)).replace(hour=23, minute=59, second=59, microsecond=0)
        elif "days" in end_date.lower() or "day" in end_date.lower():
            # Handle "7 days" or "7 days from now" format
            import re
            match = re.search(r'(\d+)', end_date)
            if match:
                days_ahead = int(match.group(1))
                end_dt = (now + timedelta(days=days_ahead)).replace(hour=23, minute=59, second=59, microsecond=0)
            else:
                # Default to 7 days if no number found
                end_dt = (now + timedelta(days=7)).replace(hour=23, minute=59, second=59, microsecond=0)
        else:
            try:
                end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=now.tzinfo)
            except ValueError:
                # Try parsing as date only
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=now.tzinfo)
                end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=0)
        
        # Get calendar events
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_dt.isoformat(),
            timeMax=end_dt.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        
        # Find free slots - ensure we only return future times
        # Get current time in Pacific timezone for filtering
        try:
            from zoneinfo import ZoneInfo
            pacific_tz = ZoneInfo('America/Los_Angeles')
            now_pacific = datetime.now(pacific_tz)
        except (ImportError, Exception):
            # Fallback: use the 'now' variable we already have
            now_pacific = now
        
        free_slots = []
        
        # Convert start_dt to Pacific timezone for comparison
        if start_dt.tzinfo:
            current_time_pacific = start_dt.astimezone(pacific_tz)
        else:
            current_time_pacific = start_dt.replace(tzinfo=pacific_tz)
        
        # If start_dt is in the past, start from now instead
        if current_time_pacific < now_pacific:
            current_time_pacific = now_pacific
            logger.info(f"[Free Slots] Adjusted start time from past to now (Pacific): {current_time_pacific.isoformat()}")
        
        for event in events:
            event_start_str = event['start'].get('dateTime', event['start'].get('date'))
            event_end_str = event['end'].get('dateTime', event['end'].get('date'))
            
            # Parse event times
            if 'T' in event_start_str:
                event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00'))
            else:
                event_start = datetime.fromisoformat(event_start_str)
                if event_start.tzinfo is None:
                    event_start = event_start.replace(tzinfo=now.tzinfo)
            
            if 'T' in event_end_str:
                event_end = datetime.fromisoformat(event_end_str.replace('Z', '+00:00'))
            else:
                event_end = datetime.fromisoformat(event_end_str)
                if event_end.tzinfo is None:
                    event_end = event_end.replace(tzinfo=now.tzinfo)
            
            # Convert event times to Pacific timezone for comparison
            if event_start.tzinfo:
                event_start_pacific = event_start.astimezone(pacific_tz)
            else:
                event_start_pacific = event_start.replace(tzinfo=pacific_tz)
            
            if event_end.tzinfo:
                event_end_pacific = event_end.astimezone(pacific_tz)
            else:
                event_end_pacific = event_end.replace(tzinfo=pacific_tz)
            
            # Check if there's a gap before this event
            # Only include slots that are in the future (in Pacific time)
            if current_time_pacific < event_start_pacific and event_start_pacific > now_pacific:
                gap_duration = (event_start_pacific - current_time_pacific).total_seconds() / 60
                if gap_duration >= duration_minutes:
                    # Ensure the slot start is in the future
                    slot_start = max(current_time_pacific, now_pacific)
                    free_slots.append({
                        "start": slot_start.isoformat(),
                        "end": event_start_pacific.isoformat(),
                        "duration_minutes": int(gap_duration)
                    })
            
            # Move current time to end of event (in Pacific time)
            if event_end_pacific > current_time_pacific:
                current_time_pacific = event_end_pacific
        
        # Convert end_dt to Pacific timezone for comparison
        if end_dt.tzinfo:
            end_dt_pacific = end_dt.astimezone(pacific_tz)
        else:
            end_dt_pacific = end_dt.replace(tzinfo=pacific_tz)
        
        # Check for free time after last event
        # Only include slots that are in the future (in Pacific time)
        if current_time_pacific < end_dt_pacific:
            gap_duration = (end_dt_pacific - current_time_pacific).total_seconds() / 60
            if gap_duration >= duration_minutes:
                # Ensure the slot start is in the future
                slot_start = max(current_time_pacific, now_pacific)
                if slot_start < end_dt_pacific:
                    free_slots.append({
                        "start": slot_start.isoformat(),
                        "end": end_dt_pacific.isoformat(),
                        "duration_minutes": int(gap_duration)
                    })
        
        # Final filter: remove any slots that are in the past
        # Use proper datetime comparison for accuracy
        future_slots = []
        for slot in free_slots:
            slot_start_str = slot['start']
            try:
                # Parse the slot start time
                slot_start_dt = datetime.fromisoformat(slot_start_str.replace('Z', '+00:00'))
                if slot_start_dt.tzinfo is None:
                    slot_start_dt = slot_start_dt.replace(tzinfo=now_pacific.tzinfo)
                # Normalize both to same timezone for comparison
                slot_start_normalized = slot_start_dt.astimezone(now_pacific.tzinfo)
                if slot_start_normalized > now_pacific:
                    future_slots.append(slot)
            except (ValueError, AttributeError) as e:
                # If parsing fails, log and skip this slot
                logger.warning(f"[Free Slots] Could not parse slot start time '{slot_start_str}': {e}")
                continue
        
        logger.info(f"[Free Slots] Filtered {len(free_slots)} slots to {len(future_slots)} future slots (now: {now_pacific.isoformat()})")
        
        return future_slots
    
    except Exception as e:
        logger.error(f"Error getting free slots: {e}", exc_info=True)
        return []


async def check_time_conflict(
    start_dt: datetime,
    end_dt: datetime
) -> tuple[bool, Optional[str]]:
    """
    Check if a time slot conflicts with existing calendar events.
    
    Returns:
        (has_conflict: bool, conflict_message: Optional[str])
    """
    if not CALENDAR_AVAILABLE:
        return False, None
    
    try:
        service = get_calendar_service()
        
        # IMPORTANT: Query for events that might overlap with our time slot
        # We need to query a wider range to catch events that:
        # - Start before our start but end during our event
        # - Start during our event but end after our end
        # Query from 1 hour before our start to 1 hour after our end
        query_start = start_dt - timedelta(hours=1)
        query_end = end_dt + timedelta(hours=1)
        
        # Format for Google Calendar API (RFC3339)
        time_min = query_start.isoformat()
        time_max = query_end.isoformat()
        
        logger.info(f"Checking conflicts: querying events from {time_min} to {time_max}")
        logger.info(f"Our event: {start_dt.isoformat()} to {end_dt.isoformat()}")
        
        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        logger.info(f"Found {len(events)} events in query range")
        
        # Check for overlaps
        for event in events:
            # Skip all-day events (they use 'date' instead of 'dateTime')
            if 'dateTime' not in event['start']:
                continue
                
            event_start_str = event['start'].get('dateTime')
            event_end_str = event['end'].get('dateTime')
            
            if not event_start_str or not event_end_str:
                continue
            
            # Parse event times - Google Calendar returns times in RFC3339 format
            try:
                # Handle 'Z' suffix (UTC) or timezone offset
                if event_start_str.endswith('Z'):
                    event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00'))
                else:
                    event_start = datetime.fromisoformat(event_start_str)
                
                if event_end_str.endswith('Z'):
                    event_end = datetime.fromisoformat(event_end_str.replace('Z', '+00:00'))
                else:
                    event_end = datetime.fromisoformat(event_end_str)
                
                # Normalize all times to Pacific timezone for consistent comparison and display
                try:
                    from zoneinfo import ZoneInfo
                    pacific_tz = ZoneInfo('America/Los_Angeles')
                except (ImportError, Exception):
                    # Fallback: use UTC if zoneinfo not available
                    pacific_tz = timezone.utc
                
                # Convert all times to Pacific timezone for comparison
                if start_dt.tzinfo:
                    start_dt_pacific = start_dt.astimezone(pacific_tz)
                else:
                    start_dt_pacific = start_dt.replace(tzinfo=pacific_tz)
                
                if end_dt.tzinfo:
                    end_dt_pacific = end_dt.astimezone(pacific_tz)
                else:
                    end_dt_pacific = end_dt.replace(tzinfo=pacific_tz)
                
                if event_start.tzinfo:
                    event_start_pacific = event_start.astimezone(pacific_tz)
                else:
                    event_start_pacific = event_start.replace(tzinfo=pacific_tz)
                
                if event_end.tzinfo:
                    event_end_pacific = event_end.astimezone(pacific_tz)
                else:
                    event_end_pacific = event_end.replace(tzinfo=pacific_tz)
                
                # Check for overlap: events overlap if they share any time
                # Our event overlaps if: start_dt < event_end AND end_dt > event_start
                if (start_dt_pacific < event_end_pacific and end_dt_pacific > event_start_pacific):
                    event_title = event.get('summary', 'Untitled Event')
                    # Format times in Pacific timezone for display
                    conflict_msg = f"Time slot conflicts with existing event: '{event_title}' ({event_start_pacific.strftime('%I:%M %p')} - {event_end_pacific.strftime('%I:%M %p')} PST)"
                    logger.warning(f"CONFLICT DETECTED (Pacific time): {conflict_msg}")
                    logger.info(f"  Our event: {start_dt_pacific.strftime('%I:%M %p')} - {end_dt_pacific.strftime('%I:%M %p')} PST")
                    logger.info(f"  Existing event: {event_start_pacific.strftime('%I:%M %p')} - {event_end_pacific.strftime('%I:%M %p')} PST")
                    return True, conflict_msg
                    
            except (ValueError, AttributeError) as e:
                logger.warning(f"Error parsing event time: {e}, event_start_str: {event_start_str}, event_end_str: {event_end_str}")
                continue
        
        logger.info("No conflicts detected")
        return False, None
    
    except Exception as e:
        logger.error(f"Error checking for conflicts: {e}", exc_info=True)
        # Don't block event creation if conflict check fails
        return False, None


async def create_calendar_event(
    title: str,
    start_time: str,
    duration_minutes: int,
    description: Optional[str] = None,
    check_conflicts: bool = True
) -> Dict[str, Any]:
    """
    Create an event in the user's Google Calendar.
    
    Args:
        title: Event title
        start_time: Start time in ISO format (YYYY-MM-DDTHH:MM:SS) or relative like "now", "in_1_hour", "today_afternoon", etc.
        duration_minutes: Duration in minutes
        description: Optional event description
    
    Returns:
        Dict with event details: {"event_id": "...", "html_link": "...", "start": "...", "end": "..."}
    """
    if not CALENDAR_AVAILABLE:
        return {"error": "Google Calendar not available"}
    
    try:
        service = get_calendar_service()
        
        # Get local timezone properly - default to Pacific time
        local_tz_name = 'America/Los_Angeles'  # Default to Pacific time
        try:
            # Try to use zoneinfo (Python 3.9+)
            from zoneinfo import ZoneInfo
            import time
            # Get system timezone name
            if sys.platform == 'win32':
                # Windows: use time.tzname
                tz_name = time.tzname[time.daylight]
                # Map common Windows timezone names to IANA names
                tz_map = {
                    'EST': 'America/New_York',
                    'EDT': 'America/New_York',
                    'CST': 'America/Chicago',
                    'CDT': 'America/Chicago',
                    'MST': 'America/Denver',
                    'MDT': 'America/Denver',
                    'PST': 'America/Los_Angeles',
                    'PDT': 'America/Los_Angeles',
                }
                local_tz_name = tz_map.get(tz_name, 'America/Los_Angeles')  # Default to Pacific
            else:
                # Unix: try to read /etc/timezone or use TZ env var
                import os
                tz_env = os.environ.get('TZ')
                if tz_env:
                    local_tz_name = tz_env
                else:
                    # Default fallback to Pacific time
                    local_tz_name = 'America/Los_Angeles'
            
            local_tz = ZoneInfo(local_tz_name)
            now = datetime.now(local_tz)
        except (ImportError, Exception):
            # Fallback: use Pacific time zone
            from zoneinfo import ZoneInfo
            try:
                local_tz = ZoneInfo('America/Los_Angeles')
                now = datetime.now(local_tz)
                local_tz_name = 'America/Los_Angeles'
            except:
                # Last resort: use time.timezone to get offset
                import time
                offset_seconds = -time.timezone if time.daylight == 0 else -time.altzone
                now = datetime.now(timezone(timedelta(seconds=offset_seconds)))
                # Default to Pacific time
                local_tz_name = 'America/Los_Angeles'
        
        # Handle user-friendly time formats
        if start_time == "now":
            # Start immediately (round to next 5 minutes, minimum 5 minutes from now)
            start_dt = now.replace(second=0, microsecond=0)
            minutes = start_dt.minute
            rounded_minutes = ((minutes // 5) + 1) * 5
            if rounded_minutes >= 60:
                start_dt = (start_dt + timedelta(hours=1)).replace(minute=0)
            else:
                start_dt = start_dt.replace(minute=rounded_minutes)
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
            if start_dt <= now:
                start_dt = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        elif start_time == "today_afternoon":
            start_dt = now.replace(hour=14, minute=0, second=0, microsecond=0)
            if start_dt <= now:
                start_dt = (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        elif start_time == "today_evening":
            start_dt = now.replace(hour=19, minute=0, second=0, microsecond=0)
            if start_dt <= now:
                start_dt = (now + timedelta(days=1)).replace(hour=19, minute=0, second=0, microsecond=0)
        elif start_time == "tomorrow_morning":
            start_dt = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        elif start_time == "tomorrow_afternoon":
            start_dt = (now + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)
        else:
            # Try to parse as ISO format or datetime-local format
            try:
                # Handle datetime-local format (YYYY-MM-DDTHH:MM) - may include timezone info
                # Format from frontend: "YYYY-MM-DDTHH:MM+TZ:MM|TimezoneName" or "YYYY-MM-DDTHH:MM+TZ:MM" or "YYYY-MM-DDTHH:MM"
                if 'T' in start_time:
                    tz_name_from_frontend = None
                    datetime_part = None
                    
                    # Check if timezone name was included (format: "...|TimezoneName")
                    if '|' in start_time:
                        # Format: "YYYY-MM-DDTHH:MM+TZ:MM|TimezoneName" or "YYYY-MM-DDTHH:MM|TimezoneName"
                        parts = start_time.split('|')
                        datetime_with_offset = parts[0]  # This might still have timezone offset
                        tz_name_from_frontend = parts[1] if len(parts) > 1 else None
                        
                        # Extract just the datetime part (YYYY-MM-DDTHH:MM) by removing timezone offset
                        # Timezone offset format: +HH:MM or -HH:MM
                        import re
                        # Match pattern: YYYY-MM-DDTHH:MM followed by optional timezone offset
                        match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})([+-]\d{2}:\d{2})?', datetime_with_offset)
                        if match:
                            datetime_part = match.group(1)  # Just the YYYY-MM-DDTHH:MM part
                        else:
                            # Fallback: try to extract first 16 characters
                            datetime_part = datetime_with_offset[:16] if len(datetime_with_offset) >= 16 else datetime_with_offset
                    else:
                        # No timezone name, but might have offset
                        # Check if it has timezone offset pattern (+HH:MM or -HH:MM)
                        import re
                        match = re.match(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})([+-]\d{2}:\d{2})?', start_time)
                        if match:
                            datetime_part = match.group(1)  # Just the YYYY-MM-DDTHH:MM part
                        else:
                            # No timezone offset, use as-is (should be exactly 16 chars: YYYY-MM-DDTHH:MM)
                            datetime_part = start_time[:16] if len(start_time) >= 16 else start_time
                    
                    # Parse the datetime part (should be exactly YYYY-MM-DDTHH:MM now)
                    start_dt_naive = datetime.strptime(datetime_part, '%Y-%m-%dT%H:%M')
                    
                    # Apply timezone - prefer frontend timezone name if provided
                    try:
                        from zoneinfo import ZoneInfo
                        if tz_name_from_frontend:
                            # Use timezone name from frontend (most accurate)
                            user_tz = ZoneInfo(tz_name_from_frontend)
                            start_dt = start_dt_naive.replace(tzinfo=user_tz)
                            logger.info(f"Using frontend timezone: {tz_name_from_frontend}")
                        else:
                            # Use server's detected timezone
                            local_tz_obj = ZoneInfo(local_tz_name)
                            start_dt = start_dt_naive.replace(tzinfo=local_tz_obj)
                            logger.info(f"Using server timezone: {local_tz_name}")
                    except (ImportError, Exception) as e:
                        # Fallback: use now's timezone
                        start_dt = start_dt_naive.replace(tzinfo=now.tzinfo)
                        logger.warning(f"Could not use ZoneInfo, using fallback: {e}")
                    
                    # Log for debugging
                    logger.info(f"Parsed datetime-local input '{start_time}' -> datetime_part: '{datetime_part}' -> final: {start_dt} (timezone: {start_dt.tzinfo})")
                elif 'T' in start_time:
                    # ISO format with or without timezone
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    if start_dt.tzinfo is None:
                        start_dt = start_dt.replace(tzinfo=now.tzinfo)
                else:
                    raise ValueError(f"Unrecognized time format: {start_time}")
                
                # If parsed time is in the past, move to next day at same time
                if start_dt < now:
                    start_dt = start_dt + timedelta(days=1)
            except ValueError as e:
                raise ValueError(f"Invalid start_time format: {start_time}. Supported formats: 'now', 'in_1_hour', 'in_2_hours', 'today_morning', 'today_afternoon', 'today_evening', 'tomorrow_morning', 'tomorrow_afternoon', or ISO datetime format. Error: {e}")
        
        # Final safety check: ensure start_dt is in the future (at least 5 minutes from now)
        if start_dt.tzinfo is None:
            start_dt = start_dt.replace(tzinfo=now.tzinfo)
        
        if start_dt <= now:
            start_dt = now + timedelta(minutes=5)
            start_dt = start_dt.replace(second=0, microsecond=0)
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=now.tzinfo)
        
        end_dt = start_dt + timedelta(minutes=duration_minutes)
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=now.tzinfo)
        
        # Get timezone string for Google Calendar
        # Use the local timezone name we determined earlier
        tz_str = local_tz_name  # Use the timezone we detected
        
        # Log for debugging
        logger.info(f"Creating event at {start_dt} (timezone: {tz_str})")
        
        # Check for conflicts before creating
        if check_conflicts:
            has_conflict, conflict_msg = await check_time_conflict(start_dt, end_dt)
            if has_conflict:
                return {
                    "error": conflict_msg,
                    "conflict": True
                }
        
        # Create event
        # For Google Calendar API:
        # - dateTime should be in RFC3339 format (ISO 8601 with timezone)
        # - timeZone should match the timezone of the dateTime
        # Important: We want to preserve the local time the user selected, so we format
        # the datetime in the local timezone without converting it
        
        # Format as RFC3339 (ISO 8601 with timezone) - use the datetime as-is in its timezone
        start_rfc3339 = start_dt.isoformat()
        end_rfc3339 = end_dt.isoformat()
        
        logger.info(f"Event times - Start: {start_rfc3339} (timezone: {tz_str}), End: {end_rfc3339}")
        logger.info(f"Start datetime components - Year: {start_dt.year}, Month: {start_dt.month}, Day: {start_dt.day}, Hour: {start_dt.hour}, Minute: {start_dt.minute}")
        
        event = {
            'summary': title,
            'description': description or 'Self-care activity from toolkit',
            'start': {
                'dateTime': start_rfc3339,
                'timeZone': tz_str,
            },
            'end': {
                'dateTime': end_rfc3339,
                'timeZone': tz_str,
            },
        }
        
        created_event = service.events().insert(calendarId='primary', body=event).execute()
        
        return {
            "event_id": created_event.get('id'),
            "html_link": created_event.get('htmlLink'),
            "start": created_event['start'].get('dateTime', created_event['start'].get('date')),
            "end": created_event['end'].get('dateTime', created_event['end'].get('date')),
        }
    
    except Exception as e:
        logger.error(f"Error creating calendar event: {e}", exc_info=True)
        return {"error": str(e)}

