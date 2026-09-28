import os
import feedparser
from newspaper import Article
import google-generativeai as genai
from supabase import create_client

# Load keys securely from Render Environment Variables
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# ... rest of your harvester logic
