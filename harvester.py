import os
import re
import json
import time
import urllib.request
import feedparser
from google import genai
from supabase import create_client

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

FEEDS = {
    "Prothom Alo": "https://www.prothomalo.com/feed/",
    "The Daily Star Bangla": "https://bangla.thedailystar.net/frontpage/rss.xml",
    "The Daily Campus": "https://thedailycampus.com/"
}

def get_article_content(url):
    """Extracts text and image using JSON-LD metadata or fallback <p> tags."""
    if "/video/" in url:
        return None, None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
        
        # 1. Stdlib JSON-LD extraction (Prothom Alo & standard publishers)
        for m in re.finditer(r'<script[^>]*type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                if isinstance(data, list): data = data[0]
                if isinstance(data, dict) and "articleBody" in data:
                    img = data.get("image")
                    img_url = img.get("url") if isinstance(img, dict) else (img[0] if isinstance(img, list) else img)
                    return data["articleBody"], img_url
            except Exception:
                continue

        # 2. Fallback: join paragraph tags
        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        clean_paras = [re.sub(r'<[^>]+>', '', p).strip() for p in paras]
        text = "\n".join(p for p in clean_paras if len(p) > 25)
        return (text, None) if len(text) >= 100 else (None, None)
    except Exception as e:
        print(f"Fetch failed for {url}: {e}")
        return None, None

def summarize_article(text):
    prompt = f"""
    Read the following Bengali news article. 
    1. Summarize it in exactly 50-60 words in pure Bengali. 
    2. Assign it ONE category from this list: [খেলাধুla, রাজনীতি, প্রযুক্তি, বিনোদন, জাতীয়, আন্তর্জাতিক].
    Format your response EXACTLY like this:
    Category: [category]
    Summary: [summary]
    
    Article: {text}
    """
    
    # Retry once on transient 503 / network spike
    response = None
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=prompt
            )
            break
        except Exception as e:
            if attempt == 0:
                print(f"Gemini busy, retrying in 3s... ({e})")
                time.sleep(3)
            else:
                print(f"Gemini call failed: {e}")
                return None, None

    if not response or not response.text:
        return None, None

    output = response.text.strip().replace("**", "")
    category, summary = "জাতীয়", output
    for line in output.splitlines():
        if line.lower().startswith("category:"):
            category = line.split(":", 1)[1].strip()
        elif line.lower().startswith("summary:"):
            summary = line.split(":", 1)[1].strip()
            
    return summary, category

# Loop through feeds and process news
for publisher, rss_url in FEEDS.items():
    feed = feedparser.parse(rss_url)
    
    # Skip if feed has no entries
    if not feed.entries:
        continue
        
    for entry in feed.entries[:5]:
        print(f"Processing: {entry.title}")
        
        # Check if already in database to avoid duplicates
        existing = supabase.table("news").select("id").eq("source_url", entry.link).execute()
        if existing.data:
            print("Already in database, skipping...")
            continue
            
        body, image = get_article_content(entry.link)
        if not body:
            print(f"Skipping {entry.link}: No readable text found.")
            continue
            
        summary, category = summarize_article(body)
        if not summary:
            print(f"Skipping {entry.link}: Summarization failed.")
            continue
        
        # Insert into Supabase
        supabase.table("news").insert({
            "title_bangla": entry.title,
            "summary_bangla": summary,
            "image_url": image,
            "source_url": entry.link,
            "publisher_name": publisher,
            "category": category
        }).execute()
        print("Successfully added to database!")
