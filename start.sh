#!/bin/bash
# Start Recce. Reads GROQ_API_KEY from .env if present.
cd "$(dirname "$0")"
lsof -ti:8010 | xargs kill -9 2>/dev/null
python3 -m uvicorn api:app --port 8010 --reload
