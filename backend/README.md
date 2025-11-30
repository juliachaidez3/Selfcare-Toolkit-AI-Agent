# Self-Care Toolkit Backend

FastAPI backend for the Self-Care Toolkit AI Agent application.

## Features

- FastAPI REST API
- OpenAI GPT-5-nano integration
- CORS enabled for frontend communication
- Error handling and validation

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the backend directory:
```
OPENAI_API_KEY=your_api_key_here
```

3. Run the server:
```bash
python main.py
```

Or using uvicorn directly:
```bash
uvicorn main:app --reload --port 5000
```

The API will be available at `http://localhost:5000`

## API Endpoints

### POST /api/toolkit

Generates personalized self-care recommendations.

**Request Body:**
```json
{
  "struggle": "string",
  "mood": "string",
  "focus": "string",
  "copingPreferences": ["string"],
  "energyLevel": "string"
}
```

**Response:**
```json
{
  "items": [
    {
      "title": "Activity Name",
      "why_it_helps": "Explanation",
      "steps": ["Step 1", "Step 2"],
      "time_estimate": "X minutes",
      "difficulty": "Easy"
    }
  ]
}
```

## Development

The server runs on port 5000 by default. Make sure your frontend is configured to proxy API requests to this port.

