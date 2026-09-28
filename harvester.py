import os
import feedparser
import nltk
from newspaper import Article, Config
from google import genai
from supabase import create_client

# Download required natural language processors for newspaper3k
nltk.download('punkt', quiet=True)
nltk.download('punkt_tab', quiet=True)

# Configure Newspaper with a modern browser User-Agent
config = Config()
config.browser_user_agent = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
config.request_timeout = 15

# Initialize Clients
# genai.Client() automatically picks up GEMINI_API_KEY from environment variables
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# RSS Feeds for your chosen portals
FEEDS = {
    "Prothom Alo": "https://www.prothomalo.com/feed/",
    "The Daily Star Bangla": "https://bangla.thedailystar.net/frontpage/rss.xml",
    "The Daily Campus": "https://thedailycampus.com/"
}

def summarize_article(article_url):
    # Prothom Alo video links don't have article bodies
    if "/video/" in article_url:
        print(f"Skipping {article_url}: Video entry, no text.")
        return None

    try:
        # Extract full text using browser config
        article = Article(article_url, config=config)
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

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        
        # BULLETPROOF PARSING
        text = response.text.strip().replace("**", "") # Remove accidental bolding
        
        # Default fallbacks
        category = "জাতীয়" 
        summary = text
        
        for line in text.split('\n'):
            line_clean = line.strip()
            if line_clean.lower().startswith("category:"):
                category = line_clean.split(":", 1)[1].strip()
            elif line_clean.lower().startswith("summary:"):
                summary = line_clean.split(":", 1)[1].strip()
        
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
        if existing.data and len(existing.data) > 0:
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
