import os
import feedparser
from newspaper import Article
import google.generativeai as genai
from supabase import create_client
import nltk

# Download required natural language processors for newspaper3k
nltk.download('punkt')
nltk.download('punkt_tab')

# Load keys securely from GitHub Environment Variables
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
gemini_model = genai.GenerativeModel('gemini-1.5-flash')

# RSS Feeds for your chosen portals
FEEDS = {
    "Prothom Alo": "https://www.prothomalo.com/feed/",
    "The Daily Star Bangla": "https://bangla.thedailystar.net/frontpage/rss.xml"
}

def summarize_article(article_url):
    try:
        # Extract full text
        article = Article(article_url)
        article.download()
        article.parse()
        
        if len(article.text) < 100:
            print(f"Skipping {article_url}: Article too short or blocked.")
            return None

        # Prompt Gemini for a Bangla summary and a Category tag
        prompt = f"""
        Read the following Bengali news article. 
        1. Summarize it in exactly 50-60 words in pure Bengali. 
        2. Assign it ONE category from this list: [খেলাধুলা, রাজনীতি, প্রযুক্তি, বিনোদন, জাতীয়, আন্তর্জাতিক].
        Format your response EXACTLY like this:
        Category: [category]
        Summary: [summary]
        
        Article: {article.text}
        """
        response = gemini_model.generate_content(prompt)
        
        # BULLETPROOF PARSING
        text = response.text.strip().replace("**", "") # Remove accidental bolding
        
        # Default fallbacks
        category = "জাতীয়" 
        summary = text
        
        for line in text.split('\n'):
            if "Category:" in line or "category:" in line:
                category = line.split(":", 1)[1].strip()
            elif "Summary:" in line or "summary:" in line:
                summary = line.split(":", 1)[1].strip()
        
        return {"summary": summary, "category": category, "image": article.top_image}
    except Exception as e:
        print(f"FAILED on {article_url}: {str(e)}")
        return None

# Loop through feeds and process news
for publisher, rss_url in FEEDS.items():
    feed = feedparser.parse(rss_url)
    
    # Process the top 5 latest news items per portal
    for entry in feed.entries[:5]:
        print(f"Processing: {entry.title}")
        
        # Check if already in database to avoid duplicates
        existing = supabase.table("news").select("id").eq("source_url", entry.link).execute()
        if len(existing.data) > 0:
            print("Already in database, skipping...")
            continue
            
        ai_data = summarize_article(entry.link)
        
        if ai_data:
            # Insert into Supabase
            supabase.table("news").insert({
                "title_bangla": entry.title,
                "summary_bangla": ai_data["summary"],
                "image_url": ai_data["image"],
                "source_url": entry.link,
                "publisher_name": publisher,
                "category": ai_data["category"]
            }).execute()
            print("Successfully added to database!")
