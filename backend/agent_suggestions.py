"""
Agent suggestions module - generates personalized action suggestions using the MCP agent.
"""
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone

from mcp_agent import _run_agent
from actions import AgentAction, AgentSuggestionsResponse, CreateCalendarBlockParams
from user_memory import format_user_memory_for_prompt

logger = logging.getLogger(__name__)


def build_suggestion_prompt(
    last_quiz: Optional[Dict[str, Any]] = None,
    toolkit_count: int = 0,
    last_login: Optional[datetime] = None,
    days_since_last_quiz: Optional[int] = None,
    weather_data: Optional[Dict[str, Any]] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    recent_actions: Optional[List[Dict[str, Any]]] = None,
    action_stats: Optional[Dict[str, Any]] = None
) -> str:
    """
    Build a prompt for the agent to generate suggestions based on user context.
    
    Args:
        last_quiz: Last quiz data (struggle, mood, focus, etc.)
        toolkit_count: Number of items in user's toolkit
        last_login: Last login timestamp
        days_since_last_quiz: Days since last quiz was taken
        
    Returns:
        Formatted prompt string
    """
    context_parts = []
    
    if last_quiz:
        context_parts.append(f"Last quiz results:")
        context_parts.append(f"  - Struggle: {last_quiz.get('struggle', 'N/A')}")
        context_parts.append(f"  - Mood: {last_quiz.get('mood', 'N/A')}")
        context_parts.append(f"  - Focus: {last_quiz.get('focus', 'N/A')}")
        context_parts.append(f"  - Energy level: {last_quiz.get('energyLevel', 'N/A')}")
    
    if toolkit_count > 0:
        context_parts.append(f"User has {toolkit_count} saved toolkit items.")
    else:
        context_parts.append("User has no saved toolkit items yet.")
    
    if days_since_last_quiz is not None:
        if days_since_last_quiz == 0:
            context_parts.append("User took a quiz today.")
        elif days_since_last_quiz < 7:
            context_parts.append(f"User last took a quiz {days_since_last_quiz} days ago.")
        else:
            context_parts.append(f"User hasn't taken a quiz in {days_since_last_quiz} days.")
    
    if weather_data:
        weather_summary = weather_data.get("summary", "")
        activity_suggestions = weather_data.get("activity_suggestions", [])
        current_temp = weather_data.get("current_weather", {}).get("temperature_celsius")
        condition = weather_data.get("current_weather", {}).get("condition", "")
        precip_prob = weather_data.get("today_forecast", {}).get("precipitation_probability_percent", 0)
        
        if weather_summary:
            context_parts.append(f"Current Weather: {weather_summary}")
        if current_temp is not None:
            context_parts.append(f"Temperature: {current_temp}°C, Condition: {condition}")
        if precip_prob > 0:
            context_parts.append(f"Precipitation chance: {precip_prob}%")
        if activity_suggestions:
            context_parts.append(f"Weather-based activity suggestions: {', '.join(activity_suggestions)}")
    
    context_str = "\n".join(context_parts) if context_parts else "This is a new user with no history."
    
    # Add user memory (preferences, recent actions, statistics)
    user_memory = format_user_memory_for_prompt(
        user_profile=user_profile,
        recent_actions=recent_actions,
        action_stats=action_stats
    )
    
    if user_memory:
        context_str += "\n\n" + "="*50 + "\nUSER MEMORY & PREFERENCES:\n" + "="*50 + "\n" + user_memory
    
    prompt = f"""MISSION: You are the Self-Care Toolkit Agent—a calm, trustworthy companion that supports college students during moments of stress, overwhelm, and emotional uncertainty. Your purpose is to transform how they feel right now into clear, personalized, and practical next steps. You reduce decision fatigue, offer grounded guidance when self-care feels hard to figure out, and help students build a flexible collection of supportive strategies they can rely on during challenging times.

CORE APPROACH:
- Remember the user's patterns and honor their emotional state
- Suggest small, doable actions that feel manageable
- Always make suggestions optional—never overwhelming or prescriptive
- Personalize every suggestion based on their history, preferences, and current context
- Act as a calm companion, never generic or overwhelming

You have long-term memory of this user. Based on the following user context, suggest 1-2 actionable steps that would help their wellbeing right now. You should ALWAYS provide at least one suggestion unless there is truly no helpful action (which should be extremely rare).

{context_str}

Your goal is to provide personalized, helpful suggestions that transform their current state into clear next steps. Consider:
- What they've been struggling with
- Their energy level and preferences
- User's stated preferences, likes, dislikes, and constraints (from USER MEMORY section)
- Recent actions they've taken and their patterns (what they accept vs. decline)
- Historical ratings and feedback (favor action types they rate highly)
- Current weather conditions (if provided):
  * On nice, sunny days with low precipitation: suggest outdoor activities like walks, exercise, or nature time
  * On rainy/cold days: suggest indoor activities like journaling, reading, meditation, or cozy self-care
  * On hot days: suggest early morning or evening activities, staying hydrated
  * Use weather data to make suggestions more relevant and actionable
- Whether they might benefit from taking the quiz again
- Whether they could use help organizing their time
- Whether reflection/journaling might help

IMPORTANT: Use the USER MEMORY section to personalize your suggestions. For example:
- If they tend to accept journaling but decline calendar events, you can still suggest both types - preferences are guidance, not strict rules
- If they rate certain action types highly, favor those
- Respect their stated constraints (e.g., "doesn't like mornings" means avoid morning suggestions)
- Reference their past actions naturally in your messages (e.g., "You usually say yes to journaling...")
- **Use the "Last 3 suggestions" section to reference specific past interactions naturally**, for example:
  * "Last time you said no to a scheduled block but yes to journaling — want to stick with journaling today?"
  * "I noticed you declined the calendar suggestion yesterday. Would a journal entry work better for you?"
  * "You accepted the journaling prompt last time — want to continue that practice?"
- **Note: Since there are limited action types available, it's okay to suggest actions that were declined before. Context and timing matter - a declined suggestion yesterday might be helpful today.**

IMPORTANT: Do NOT use any tools. Simply respond directly with JSON.

Return your response as a JSON object with an "actions" array. Each action must follow this exact schema:

{{
  "actions": [
      {{
      "type": "create_calendar_block",
      "message": "A friendly, personalized message explaining why this helps",
      "requires_confirmation": true,
      "params": {{
        "duration_minutes": 25,
        "purpose": "focused study time"
      }}
    }},
    {{
      "type": "create_journal_entry",
      "message": "A friendly, personalized message about why journaling might help based on their context",
      "requires_confirmation": true,
      "params": {{
        "prompt_template": "A personalized journal prompt based on their struggle, mood, and quiz responses. Make it specific and helpful."
      }}
    }},
    {{
      "type": "suggest_retake_quiz",
      "message": "A friendly message suggesting they retake the quiz",
      "requires_confirmation": true,
      "params": {{
        "reason": "optional reason"
      }}
    }}
  ]
}}

Available action types:
- "create_calendar_block": Schedule a focused time block in Google Calendar (params: duration_minutes: 5-240, purpose: string)
  - NOTE: Do NOT include a time_window parameter. The backend will automatically find the best free slot starting from 1 hour from now, considering the user's preferred times based on their past self-care activities.
  - The backend will intelligently select a time that matches when the user typically does self-care activities.
  - The calendar.create_event tool will be used to create the actual event
- "create_journal_entry": Create a Google Doc journal entry with a personalized prompt (params: prompt_template: string)
  - The docs_create_journal_entry tool will create a Google Doc with the prompt, ready for the user to write
  - The prompt should be personalized based on the user's quiz responses (struggle, mood, etc.)
- "suggest_retake_quiz": Suggest retaking the self-care quiz (params: empty object)

Available MCP tools (you can use these in your reasoning, but return actions in the JSON format above):
- weather.get_forecast: Get weather forecast for a location (weather data is already included in context if available)
- calendar.get_free_slots: Check when the user has free time
- calendar.create_event: Create a calendar event (used automatically when user confirms calendar_block action)
- docs_create_journal_entry: Create a Google Doc with journal prompts (used automatically when user confirms journal_entry action)

Important:
- Return 1-2 actions (ALWAYS at least 1, unless there is truly no helpful action - which should be extremely rare)
- Make messages personal and specific to their context
- Always try to find at least one helpful suggestion based on:
  * Their current context (quiz results, mood, struggles)
  * Their preferences and past behavior
  * Current weather conditions
  * Time since last quiz
- If the user just took a quiz today, suggest journaling or calendar organization
- If they haven't taken a quiz in a while, suggesting a retake makes sense
- If they have no quiz data, suggest taking the quiz
- Be thoughtful but always provide at least one actionable suggestion

SAFETY & WELLBEING GUARDRAILS:
You are a calm, trustworthy companion that helps students care for their mental, emotional, and physical wellbeing—always optional, always personalized, never generic or overwhelming. You are NOT a medical professional or crisis counselor. Follow these guidelines:

DO NOT:
- Diagnose any mental health conditions
- Provide crisis advice or emergency intervention
- Replace professional medical or mental health care
- Make claims about curing or treating conditions
- Suggest actions that could be harmful or dangerous
- Be generic or overwhelming—always personalize

DO:
- Transform feelings into clear, practical next steps
- Suggest small, low-pressure, reversible actions (e.g., "Would you like to try...?" not "You must...")
- Keep suggestions gentle, optional, and personalized
- Honor the user's emotional state and energy level
- Remember their patterns and preferences to personalize suggestions
- Reduce decision fatigue by offering grounded guidance
- Encourage reaching out to a trusted person or professional if the user's context suggests serious distress
- Focus on supportive, practical self-care activities that help build flexible strategies
- Respect user autonomy - all suggestions require confirmation
- If user context suggests crisis or serious distress, acknowledge their feelings and gently suggest: "If you're experiencing a crisis, please reach out to a trusted person or professional. You can also contact a crisis helpline for immediate support."

Remember: You are a supportive companion for everyday self-care that helps students build flexible strategies they can rely on during challenging times. You are not a replacement for professional help.

Return ONLY valid JSON, no other text."""
    
    return prompt


def analyze_preferred_times(recent_actions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Analyze user's past calendar actions to determine preferred times for self-care.
    
    Returns:
        Dict with preferred hour ranges and patterns:
        {
            "preferred_hours": [9, 14, 19],  # Hours when user typically schedules self-care
            "preferred_time_of_day": "afternoon",  # "morning", "afternoon", "evening"
            "has_pattern": True
        }
    """
    if not recent_actions:
        return {"preferred_hours": [], "preferred_time_of_day": None, "has_pattern": False}
    
    # Extract hours from past calendar actions
    scheduled_hours = []
    for action in recent_actions:
        if action.get('actionType') == 'create_calendar_block' and action.get('outcome') == 'confirmed':
            params = action.get('params', {})
            time_window = params.get('time_window', '')
            
            # Try to extract hour from ISO datetime
            if 'T' in time_window:
                try:
                    dt = datetime.fromisoformat(time_window.replace('Z', '+00:00'))
                    scheduled_hours.append(dt.hour)
                except (ValueError, AttributeError):
                    pass
            # Or from relative time strings
            elif 'morning' in time_window:
                scheduled_hours.append(9)
            elif 'afternoon' in time_window:
                scheduled_hours.append(14)
            elif 'evening' in time_window:
                scheduled_hours.append(19)
    
    if not scheduled_hours:
        return {"preferred_hours": [], "preferred_time_of_day": None, "has_pattern": False}
    
    # Find most common hours
    from collections import Counter
    hour_counts = Counter(scheduled_hours)
    most_common_hours = [hour for hour, count in hour_counts.most_common(3)]
    
    # Determine preferred time of day
    avg_hour = sum(scheduled_hours) / len(scheduled_hours)
    if avg_hour < 12:
        preferred_time_of_day = "morning"
    elif avg_hour < 17:
        preferred_time_of_day = "afternoon"
    else:
        preferred_time_of_day = "evening"
    
    return {
        "preferred_hours": most_common_hours,
        "preferred_time_of_day": preferred_time_of_day,
        "has_pattern": len(scheduled_hours) >= 2
    }


def select_best_free_slot(
    free_slots: List[Dict[str, Any]],
    preferred_times: Dict[str, Any],
    duration_minutes: int
) -> Optional[Dict[str, Any]]:
    """
    Select the best free slot based on user preferences.
    
    Args:
        free_slots: List of free slots from calendar
        preferred_times: User's preferred times from analyze_preferred_times()
        duration_minutes: Required duration
        
    Returns:
        Best free slot dict or None
    """
    if not free_slots:
        return None
    
    # Filter slots that are at least the required duration
    suitable_slots = [slot for slot in free_slots if slot.get('duration_minutes', 0) >= duration_minutes]
    
    if not suitable_slots:
        return None
    
    # If user has preferred times, prioritize slots close to those hours
    if preferred_times.get('has_pattern') and preferred_times.get('preferred_hours'):
        preferred_hours = preferred_times['preferred_hours']
        
        # Score each slot based on how close it is to preferred hours
        scored_slots = []
        for slot in suitable_slots:
            try:
                slot_dt = datetime.fromisoformat(slot['start'].replace('Z', '+00:00'))
                slot_hour = slot_dt.hour
                
                # Calculate distance to nearest preferred hour
                min_distance = min(abs(slot_hour - ph) for ph in preferred_hours)
                # Lower distance = higher score
                score = 24 - min_distance
                
                scored_slots.append((score, slot))
            except (ValueError, KeyError):
                # If we can't parse, give it a neutral score
                scored_slots.append((12, slot))
        
        # Sort by score (highest first) and return the best one
        scored_slots.sort(key=lambda x: x[0], reverse=True)
        return scored_slots[0][1]
    
    # No preferences, just return the first suitable slot
    return suitable_slots[0]


async def generate_agent_suggestions(
    last_quiz: Optional[Dict[str, Any]] = None,
    toolkit_count: int = 0,
    last_login: Optional[datetime] = None,
    days_since_last_quiz: Optional[int] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    recent_actions: Optional[List[Dict[str, Any]]] = None,
    action_stats: Optional[Dict[str, Any]] = None
) -> AgentSuggestionsResponse:
    """
    Generate agent suggestions using the MCP agent.
    For calendar suggestions, we'll fetch free slots and update the time_window
    to use an actual free slot time.
    """
    """
    Generate agent suggestions using the MCP agent.
    
    Args:
        last_quiz: Last quiz data
        toolkit_count: Number of toolkit items
        last_login: Last login time
        days_since_last_quiz: Days since last quiz
        latitude: Optional latitude for weather data
        longitude: Optional longitude for weather data
        
    Returns:
        AgentSuggestionsResponse with actions
    """
    try:
        # Fetch weather data if location is provided
        weather_data = None
        if latitude is not None and longitude is not None:
            try:
                from mcp_agent import _run_agent
                # Call the weather tool directly via MCP
                weather_prompt = f"Use the weather.get_forecast tool to get weather for coordinates {latitude}, {longitude}. Return the full weather data."
                weather_result = await _run_agent(weather_prompt)
                
                # Parse weather result - the tool returns JSON string that gets parsed
                if isinstance(weather_result, dict):
                    # Check if it's wrapped in a "text" field (tool output format)
                    if "text" in weather_result:
                        import json
                        try:
                            weather_data = json.loads(weather_result["text"])
                        except (json.JSONDecodeError, TypeError):
                            weather_data = weather_result
                    elif "error" not in weather_result:
                        weather_data = weather_result
                    else:
                        logger.warning(f"Weather API error: {weather_result.get('error')}")
                elif isinstance(weather_result, str):
                    # Try to parse as JSON
                    import json
                    try:
                        weather_data = json.loads(weather_result)
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse weather result as JSON: {weather_result[:200]}")
                
                if weather_data and "error" not in weather_data:
                    logger.info(f"Weather data retrieved: {weather_data.get('summary', 'N/A')}")
                elif weather_data:
                    logger.warning(f"Weather API returned error: {weather_data.get('error')}")
                    weather_data = None
            except Exception as e:
                logger.warning(f"Failed to fetch weather data: {e}", exc_info=True)
                # Continue without weather data
        
        prompt = build_suggestion_prompt(
            last_quiz=last_quiz,
            toolkit_count=toolkit_count,
            last_login=last_login,
            days_since_last_quiz=days_since_last_quiz,
            weather_data=weather_data,
            user_profile=user_profile,
            recent_actions=recent_actions,
            action_stats=action_stats
        )
        
        logger.info("Generating agent suggestions...")
        logger.info(f"Prompt context: toolkit_count={toolkit_count}, days_since_last_quiz={days_since_last_quiz}")
        result = await _run_agent(prompt)
        
        logger.info(f"Agent result type: {type(result)}")
        logger.info(f"Agent result: {result}")
        
        # Parse the result - it should be a dict with "actions" key
        if isinstance(result, dict) and "actions" in result:
            actions_data = result["actions"]
            logger.info(f"Found actions key with {len(actions_data)} actions")
        elif isinstance(result, dict):
            # Try to find actions in the response
            logger.info(f"Result keys: {list(result.keys())}")
            actions_data = result.get("actions", [])
            if not actions_data:
                logger.warning(f"No 'actions' key found in result. Full result: {result}")
        else:
            logger.warning(f"Unexpected result format: {type(result)}, value: {result}")
            actions_data = []
        
        # Validate and parse actions
        actions = []
        logger.info(f"[Agent Suggestions] Processing {len(actions_data)} actions from agent")
        for idx, action_data in enumerate(actions_data):
            try:
                action_type = action_data.get('type', 'unknown')
                logger.info(f"[Agent Suggestions] Processing action {idx + 1}/{len(actions_data)}: type={action_type}")
                
                # For calendar actions, remove time_window if provided by agent (we'll set it ourselves)
                if action_type == 'create_calendar_block':
                    if 'time_window' in action_data.get('params', {}):
                        logger.info(f"[Calendar Action] Agent provided time_window: {action_data['params']['time_window']} - will be replaced with free slot")
                        # Remove time_window so backend can set it from free slots
                        action_data['params'].pop('time_window', None)
                    else:
                        logger.info(f"[Calendar Action] No time_window provided by agent - will find free slot")
                
                action = AgentAction(**action_data)
                
                # If this is a calendar action, automatically find the best free slot starting from 1 hour from now
                if action.type == "create_calendar_block":
                    try:
                        from calendar_service import get_free_slots
                        
                        # action.params is a dict, not a Pydantic model, so access it as a dict
                        params_dict = action.params if isinstance(action.params, dict) else action.params.dict() if hasattr(action.params, 'dict') else {}
                        duration = params_dict.get('duration_minutes', 30)
                        # Get original time_window if it exists (should be None after our removal above)
                        original_time_window = params_dict.get('time_window') or 'NOT_SET'
                        purpose = params_dict.get('purpose', 'N/A')
                        
                        logger.info(f"[Calendar Action Processing] Processing calendar action:")
                        logger.info(f"  - Duration: {duration} minutes")
                        logger.info(f"  - Original time_window from agent: {original_time_window}")
                        logger.info(f"  - Purpose: {purpose}")
                        
                        # Analyze user's preferred times from past actions
                        preferred_times = analyze_preferred_times(recent_actions)
                        logger.info(f"  - User preferred times: {preferred_times}")
                        
                        # Calculate start time: 1 hour from now (in Pacific time)
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
                        
                        start_from = now + timedelta(hours=1)
                        start_from_str = start_from.isoformat()
                        
                        # Get free slots starting from 1 hour from now, looking ahead 7 days
                        logger.info(f"  - Searching for free slots starting from {start_from_str} (1 hour from now)")
                        free_slots = await get_free_slots(start_from_str, "7 days", duration)
                        logger.info(f"  - Found {len(free_slots)} total free slots")
                        
                        if free_slots and len(free_slots) > 0:
                            # Filter slots that are at least 1 hour from now
                            future_slots = [
                                slot for slot in free_slots
                                if datetime.fromisoformat(slot['start'].replace('Z', '+00:00')) >= start_from
                            ]
                            logger.info(f"  - Found {len(future_slots)} slots at least 1 hour from now")
                            
                            if future_slots:
                                # Select the best slot based on user preferences
                                best_slot = select_best_free_slot(future_slots, preferred_times, duration)
                                
                                if best_slot:
                                    # Update the time_window in the params dict
                                    action.params['time_window'] = best_slot["start"]
                                    logger.info(f"  - ✅ Selected best free slot: {best_slot['start']} (replaced '{original_time_window}')")
                                    logger.info(f"  - ✅ Action.params after update: {action.params}")
                                else:
                                    # Fallback to first future slot if selection failed
                                    action.params['time_window'] = future_slots[0]["start"]
                                    logger.info(f"  - ✅ Using first available free slot: {future_slots[0]['start']} (replaced '{original_time_window}')")
                                    logger.info(f"  - ✅ Action.params after update: {action.params}")
                            else:
                                # No slots found that are at least 1 hour from now
                                logger.warning(f"  - ❌ No free slots found at least 1 hour from now. Skipping calendar suggestion.")
                                continue  # Skip this suggestion
                        else:
                            # No free slots found in the next 7 days
                            logger.warning(f"  - ❌ No free slots found in the next 7 days. Skipping calendar suggestion.")
                            continue  # Skip this suggestion
                    except Exception as e:
                        logger.error(f"  - ❌ ERROR fetching free slots: {e}", exc_info=True)
                        # If we can't check for free slots, skip this calendar suggestion to avoid conflicts
                        logger.warning("Skipping calendar suggestion due to error checking free slots")
                        continue
                    
                    # CRITICAL: Ensure calendar actions have a valid ISO datetime time_window
                    # If time_window is still None or a relative string, skip this action
                    final_params = action.params if isinstance(action.params, dict) else action.params.dict() if hasattr(action.params, 'dict') else {}
                    final_time_window = final_params.get('time_window')
                    if not final_time_window or (final_time_window and not ('T' in final_time_window and len(final_time_window) > 16)):
                        logger.error(f"  - ❌ Calendar action still has invalid time_window: {final_time_window}. Skipping.")
                        continue
                    logger.info(f"  - ✅ Final time_window validated: {final_time_window}")
                    
                    # Log the action params before adding to ensure time_window is set
                    final_params_check = action.params if isinstance(action.params, dict) else action.params.dict() if hasattr(action.params, 'dict') else {}
                    logger.info(f"  - ✅ Action params before adding: time_window={final_params_check.get('time_window')}, duration={final_params_check.get('duration_minutes')}, purpose={final_params_check.get('purpose')}")
                    
                    # Recreate the AgentAction to ensure Pydantic properly serializes the updated params
                    # This ensures the dict modification is properly reflected in the model
                    action = AgentAction(
                        type=action.type,
                        message=action.message,
                        requires_confirmation=action.requires_confirmation,
                        params=action.params  # This is now a dict with the updated time_window
                    )
                    logger.info(f"  - ✅ Recreated AgentAction with updated params: {action.params.get('time_window') if isinstance(action.params, dict) else 'N/A'}")
                
                actions.append(action)
            except Exception as e:
                logger.warning(f"Invalid action data: {action_data}, error: {e}")
                continue
        
        # Ensure at least one suggestion is returned
        if len(actions) == 0:
            logger.warning("Agent returned 0 actions, creating fallback suggestion")
            # Create a fallback suggestion based on context
            fallback_message = "How are you feeling today? Would you like to take a moment to reflect or check in with yourself?"
            
            # Prefer journaling if user has history of accepting it, otherwise suggest quiz
            if action_stats and action_stats.get('acceptance_rates', {}).get('create_journal_entry', 0) >= 0.5:
                fallback_action = AgentAction(
                    type="create_journal_entry",
                    message=fallback_message + " I can create a quick journal entry for you to reflect.",
                    requires_confirmation=True,
                    params={
                        "prompt_template": "Take a moment to check in with yourself. How are you feeling right now? What's one thing you're grateful for today?"
                    }
                )
            else:
                # Default to suggesting quiz if no strong preference
                fallback_action = AgentAction(
                    type="suggest_retake_quiz",
                    message=fallback_message + " Taking our self-care quiz can help identify what you need right now.",
                    requires_confirmation=True,
                    params={
                        "reason": "Regular check-ins help maintain wellbeing"
                    }
                )
            actions.append(fallback_action)
        
        logger.info(f"Generated {len(actions)} valid actions")
        return AgentSuggestionsResponse(actions=actions)
        
    except Exception as e:
        logger.error(f"Error generating agent suggestions: {e}", exc_info=True)
        # Return a fallback suggestion on error rather than empty
        fallback_action = AgentAction(
            type="suggest_retake_quiz",
            message="We had trouble generating personalized suggestions. Would you like to take our self-care quiz to get started?",
            requires_confirmation=True,
            params={
                "reason": "Get personalized recommendations"
            }
        )
        return AgentSuggestionsResponse(actions=[fallback_action])

