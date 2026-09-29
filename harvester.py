import os
import re
import json
import urllib.request
import feedparser
from openai import OpenAI
from supabase import create_client

# Initialize AgentRouter client (OpenAI format)
client = OpenAI(
    base_url="https://agentrouter.org/v1",
    api_key=os.getenv("AGENTROUTER_API_KEY"),
)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

FEEDS = {
    "Prothom Alo": "https://www.prothomalo.com/feed/",
    "The Daily Star Bangla": "https://bangla.thedailystar.net/frontpage/rss.xml",
}

def get_article_content(url):
    if "/video/" in url:
        return None, None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
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

        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        clean = [re.sub(r'<[^>]+>', '', p).strip() for p in paras]
        text = "\n".join(p for p in clean if len(p) > 25)
        return (text, None) if len(text) >= 100 else (None, None)
    except Exception as e:
        print(f"Fetch failed for {url}: {e}")
        return None, None

def summarize_article(text):
    prompt = f"""
    Read the following Bengali news article. 
    1. Summarize it in exactly 50-60 words in pure Bengali. 
    2. Assign it ONE category from this list: [খেলাধুলা, রাজনীতি, প্রযুক্তি, বিনোদন, জাতীয়, আন্তর্জাতিক].
    Format your response EXACTLY like this:
    Category: [category]
    Summary: [summary]
    
    Article: {text}
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": prompt}],
        )
        # Handle string response or standard OpenAI completion object
        output = response if isinstance(response, str) else response.choices[0].message.content
        output = output.strip().replace("**", "")
    except Exception as e:
        print(f"LLM call failed: {e}")
        return None, None

    category, summary = "জাতীয়", output
    for line in output.splitlines():
        if line.lower().startswith("category:"):
            category = line.split(":", 1)[1].strip()
        elif line.lower().startswith("summary:"):
            summary = line.split(":", 1)[1].strip()
            
    return summary, category

for publisher, rss_url in FEEDS.items():
    feed = feedparser.parse(rss_url)
    for entry in feed.entries[:5]:
        print(f"Processing: {entry.title}")
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
            continue
        
        supabase.table("news").insert({
            "title_bangla": entry.title,
            "summary_bangla": summary,
            "image_url": image,
            "source_url": entry.link,
            "publisher_name": publisher,
            "category": category
        }).execute()
        print("Successfully added to database!")
