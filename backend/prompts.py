system_prompt = """
Act as a compassionate college wellness coach. Provide supportive, realistic, beginner-friendly self-care suggestions. Avoid medical or diagnostic language. 
If the user's input suggests crisis or self-harm, respond only with a short safety message and stop.
"""

user_prompt_template = """
I am struggling with {struggle}.
My current mood is {mood}.
I am looking for {focus}.
My coping preferences are {coping_preferences}.
My energy level is {energy_level}.

Build me a personalized self-care toolkit with 2-3 actionable ideas that are realistic, fit my energy level, and align with my coping preferences.

Return your response as a JSON object with a "recommendations" key containing an array of activities.

Format:
{{
  "recommendations": [
    {{
      "title": "Activity Name",
      "why_it_helps": "Explanation of benefits",
      "steps": ["Step 1", "Step 2", "Step 3"],
      "time_estimate": "X minutes",
      "difficulty": "Easy"
    }},
    {{
      "title": "Another Activity",
      "why_it_helps": "Why this helps",
      "steps": ["Step 1", "Step 2"],
      "time_estimate": "Y minutes", 
      "difficulty": "Medium"
    }}
  ]
}}
"""

