import os
import re
import json
import urllib.request
import feedparser
from openai import OpenAI
from supabase import create_client

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

FEEDS = {
    "Prothom Alo": "https://www.prothomalo.com/feed/",
    "The Daily Star Bangla": "https://bangla.thedailystar.net/rss.xml",
    "The Daily Campus": "https://thedailycampus.com/"
}

LIMIT_PER_SITE = 10  # Up to 10 new articles per portal (up to 30 total per run)

def get_source_items(publisher, url):
    """Fetches list of articles from RSS feeds or homepage directly for The Daily Campus."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if "thedailycampus.com" in url:
        try:
            req = urllib.request.Request(url, headers=headers)
            html = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", errors="ignore")
            paths = list(dict.fromkeys(re.findall(r'href=[\'"](?:https://thedailycampus\.com)?/([a-zA-Z0-9_\-]+/\d+)[\'"]', html)))
            return [{"title": None, "link": f"https://thedailycampus.com/{p}"} for p in paths]
        except Exception as e:
            print(f"Error fetching The Daily Campus: {e}")
            return []
    else:
        feed = feedparser.parse(url)
        return [{"title": getattr(e, "title", None), "link": e.link} for e in feed.entries]

def get_article_content(url, default_title=None):
    if "/video/" in url:
        return None, None, None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
        
        # Extract title from <h1> if not present in feed
        title = default_title
        if not title:
            h1_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
            if h1_match:
                title = re.sub(r'<[^>]+>', '', h1_match.group(1)).strip()

        # 1. JSON-LD extraction
        for m in re.finditer(r'<script[^>]*type=[\'"]application/ld\+json[\'"][^>]*>(.*?)</script>', html, re.DOTALL):
            try:
                data = json.loads(m.group(1))
                if isinstance(data, list): data = data[0]
                if isinstance(data, dict) and "articleBody" in data:
                    img = data.get("image")
                    img_url = img.get("url") if isinstance(img, dict) else (img[0] if isinstance(img, list) else img)
                    return title, data["articleBody"], img_url
            except Exception:
                continue

        # 2. Fallback: <p> tags
        paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
        clean = [re.sub(r'<[^>]+>', '', p).strip() for p in paras]
        text = "\n".join(p for p in clean if len(p) > 25)
        return (title, text, None) if len(text) >= 100 else (None, None, None)
    except Exception as e:
        print(f"Fetch failed for {url}: {e}")
        return None, None, None

def summarize_article(text):
    prompt = f"""
    Read the following Bengali news article. 
    1. Summarize it in exactly 100-120 words in pure Bengali. 
    2. Assign it ONE category from this list: [খেলাধুলা, রাজনীতি, প্রযুক্তি, বিনোদন, জাতীয়, আন্তর্জাতিক].
    Format your response EXACTLY like this:
    Category: [category]
    Summary: [summary]
    
    Article: {text}
    """
    try:
        response = client.chat.completions.create(
            model="nvidia/nemotron-3-ultra-550b-a55b:free",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response if isinstance(response, str) else response.choices[0].message.content
        output = raw.strip().replace("**", "")
    except Exception as e:
        print(f"LLM call failed: {e}")
        return None, None

    category, summary = "জাতীয়", None
    for line in output.splitlines():
        line_clean = line.strip()
        if line_clean.lower().startswith("category:"):
            category = line_clean.split(":", 1)[1].strip()
        elif line_clean.lower().startswith("summary:"):
            summary = line_clean.split(":", 1)[1].strip()
            
    return (summary or output), category

# Process each portal
for publisher, source_url in FEEDS.items():
    print(f"\n--- Checking {publisher} ---")
    items = get_source_items(publisher, source_url)
    saved_count = 0
    
    for item in items:
        if saved_count >= LIMIT_PER_SITE:
            break
            
        link = item["link"]
        if "/video/" in link:
            continue
            
        # Check if already saved in Supabase
        existing = supabase.table("news").select("id").eq("source_url", link).execute()
        if existing.data:
            continue
            
        title, body, image = get_article_content(link, item["title"])
        if not body or not title:
            continue
            
        print(f"Processing: {title[:60]}...")
        summary, category = summarize_article(body)
        if not summary:
            print(f"Skipping: Summarization failed.")
            continue
        
        # Permanent upsert (ignores duplicates, keeps all history)
        try:
            supabase.table("news").upsert({
                "title_bangla": title,
                "summary_bangla": summary,
                "image_url": image,
                "source_url": link,
                "publisher_name": publisher,
                "category": category
            }, on_conflict="source_url", ignore_duplicates=True).execute()
            
            saved_count += 1
            print(f"[{saved_count}/{LIMIT_PER_SITE}] Saved for {publisher}!")
        except Exception as e:
            print(f"Save error: {e}")
