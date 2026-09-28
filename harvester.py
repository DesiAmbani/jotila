import os
import feedparser
from newspaper import Article
import google-generativeai as genai
from supabase import create_client

# Load keys securely from Render Environment Variables
genai.configure(api_key=os.getenv("AQ.Ab8RN6IFnbYnls7va06IYm7iPQtTHesaRfUeBrn2u99LpMKTWg"))
supabase = create_client(os.getenv("https://htpedzblxupxwufmrnuo.supabase.co"), os.getenv("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imh0cGVkemJseHVweHd1Zm1ybnVvIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MDYwNzIyMSwiZXhwIjoyMTA2MTgzMjIxfQ.r0I_GlJ1Mo_g6iS39Zpt1s6vvDg-XF0OW6bj-eCkSDc"))
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# ... rest of your harvester logic
