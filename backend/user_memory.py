"""
User memory module - processes user profile, action history, and feedback data.
Note: Data is stored in Firestore via frontend, this module processes it for prompts.
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def format_user_memory_for_prompt(
    user_profile: Optional[Dict[str, Any]] = None,
    recent_actions: Optional[List[Dict[str, Any]]] = None,
    action_stats: Optional[Dict[str, Any]] = None
) -> str:
    """
    Format user memory data into a string for the agent prompt.
    
    Args:
        user_profile: User profile with preferences, likes, dislikes, constraints
        recent_actions: List of recent actions (last 7)
        action_stats: Statistics about user's action history
        
    Returns:
        Formatted string to include in prompt
    """
    memory_parts = []
    
    # User profile (preferences, constraints)
    if user_profile:
        preferences = user_profile.get('preferences', [])
        likes = user_profile.get('likes', [])
        dislikes = user_profile.get('dislikes', [])
        constraints = user_profile.get('constraints', [])
        
        if preferences:
            memory_parts.append("User preferences:")
            for pref in preferences:
                memory_parts.append(f"  - {pref}")
        
        if likes:
            memory_parts.append("User likes:")
            for like in likes:
                memory_parts.append(f"  - {like}")
        
        if dislikes:
            memory_parts.append("User dislikes:")
            for dislike in dislikes:
                memory_parts.append(f"  - {dislike}")
        
        if constraints:
            memory_parts.append("User constraints:")
            for constraint in constraints:
                memory_parts.append(f"  - {constraint}")
    
    # Last 3 suggestions (most recent) - detailed format for natural referencing
    if recent_actions and len(recent_actions) > 0:
        # Get the last 3 actions (most recent first)
        last_3_actions = recent_actions[:3]
        memory_parts.append(f"\nLast {len(last_3_actions)} suggestions (most recent first):")
        for i, action in enumerate(last_3_actions, 1):
            action_type = action.get('actionType', 'unknown')
            action_message = action.get('actionMessage', '')
            outcome = action.get('outcome', 'unknown')
            
            # Format action type for readability
            action_name = action_type.replace('_', ' ').replace('create ', '').replace('suggest ', '')
            if 'calendar' in action_type:
                action_display = "scheduled block"
            elif 'journal' in action_type:
                action_display = "journaling"
            elif 'quiz' in action_type:
                action_display = "quiz retake"
            else:
                action_display = action_name
            
            # Format outcome
            if outcome == 'confirmed':
                outcome_display = "accepted"
            elif outcome == 'dismissed':
                outcome_display = "declined"
            else:
                outcome_display = outcome
            
            # Include message snippet if available (first 50 chars)
            message_snippet = action_message[:50] + "..." if len(action_message) > 50 else action_message
            
            memory_parts.append(f"  {i}. {action_display.title()}: \"{message_snippet}\" → {outcome_display}")
        
        # Also include summary of all recent actions for pattern recognition
        if len(recent_actions) > 3:
            action_summary = {}
            for action in recent_actions:
                action_type = action.get('actionType', 'unknown')
                outcome = action.get('outcome', 'unknown')
                # Count actions by type and outcome
                key = f"{action_type}_{outcome}"
                action_summary[key] = action_summary.get(key, 0) + 1
            
            memory_parts.append(f"\nPattern from last {len(recent_actions)} actions:")
            for key, count in action_summary.items():
                action_type, outcome = key.rsplit('_', 1)
                action_name = action_type.replace('_', ' ').title()
                if outcome == 'confirmed':
                    memory_parts.append(f"  - {count} {action_name} (accepted)")
                else:
                    memory_parts.append(f"  - {count} {action_name} (declined)")
    
    # Action statistics and preferences
    if action_stats:
        preferences = action_stats.get('preferences', [])
        average_ratings = action_stats.get('average_ratings', {})
        
        if preferences:
            memory_parts.append("\nUser behavior patterns:")
            for pref in preferences:
                memory_parts.append(f"  - {pref}")
        
        if average_ratings:
            memory_parts.append("\nAverage ratings by action type:")
            for action_type, avg_rating in average_ratings.items():
                action_name = action_type.replace('_', ' ').title()
                memory_parts.append(f"  - {action_name}: {avg_rating:.1f}/5")
    
    return "\n".join(memory_parts) if memory_parts else ""

