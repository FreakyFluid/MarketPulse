import os
import sys
import time
import json
import html
import hashlib
import feedparser
import httpx
import pytz
import yfinance as yf
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Add project root/modules to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from resolver import resolve_catalyst
from sentiment import score_headline
from telegram_bot import TelegramBroadcaster

# --- Configuration ---
RSS_FEEDS = {
    "MoneyControl - Markets": "https://www.moneycontrol.com/rss/marketreports.xml",
    "MoneyControl - Business": "https://www.moneycontrol.com/rss/business.xml",
    "Economic Times - Stocks": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "Economic Times - Markets": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Business Standard - Markets": "https://www.business-standard.com/rss/markets-106.rss"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive"
}

UPSTOX_NEWS_URL = "https://api.upstox.com/v2/news"
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "processed_news.json")
POLL_INTERVAL_SECONDS = 60

class CatalystMonitor:
    def __init__(self):
        self.ist = pytz.timezone('Asia/Kolkata')
        self.broadcaster = TelegramBroadcaster()
        self.processed_hashes = self._load_cache()
        self.last_briefing_date = None

    def _load_cache(self) -> set:
        """Loads already processed headline hashes from local JSON cache."""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r") as f:
                    return set(json.load(f))
            except Exception as e:
                print(f"[!] Error loading cache: {e}")
        return set()

    def _save_cache(self):
        """Saves current processed hashes to JSON cache."""
        try:
            with open(CACHE_FILE, "w") as f:
                # Keep cache clean by only saving the last 500 items
                json.dump(list(self.processed_hashes)[-500:], f, indent=4)
        except Exception as e:
            print(f"[!] Error writing cache: {e}")

    def _get_hash(self, text: str) -> str:
        """Generates MD5 hash of a headline for deduplication."""
        return hashlib.md5(text.lower().strip().encode('utf-8')).hexdigest()

    def fetch_rss_headlines(self) -> list:
        """Polls financial RSS feeds for new articles."""
        headlines = []
        for name, url in RSS_FEEDS.items():
            try:
                with httpx.Client(headers=HEADERS, follow_redirects=True) as client:
                    response = client.get(url, timeout=15.0)
                    if response.status_code == 200:
                        feed = feedparser.parse(response.content)
                    else:
                        print(f"[!] Error fetching RSS feed '{name}': HTTP {response.status_code}")
                        continue
                
                for entry in feed.entries:
                    headline = entry.get("title", "")
                    link = entry.get("link", "")
                    
                    if not headline:
                        continue
                        
                    h_hash = self._get_hash(headline)
                    if h_hash in self.processed_hashes:
                        continue
                        
                    headlines.append({
                        "headline": headline,
                        "link": link,
                        "source": name,
                        "hash": h_hash
                    })
            except Exception as e:
                print(f"[!] Error parsing RSS feed '{name}': {e}")
        return headlines

    def fetch_upstox_headlines(self) -> list:
        """Polls the Upstox Corporate News feed if token is active."""
        token = os.getenv("UPSTOX_ACCESS_TOKEN")
        if not token or os.getenv("UPSTOX_SANDBOX", "false").lower() == "true":
            return []

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        headlines = []
        try:
            with httpx.Client() as client:
                response = client.get(UPSTOX_NEWS_URL, headers=headers, timeout=10.0)
                if response.status_code == 200:
                    data = response.json().get("data", [])
                    for item in data:
                        title = item.get("headline", "")
                        link = item.get("url", "")
                        if not title:
                            continue
                            
                        h_hash = self._get_hash(title)
                        if h_hash in self.processed_hashes:
                            continue
                            
                        headlines.append({
                            "headline": title,
                            "link": link,
                            "source": "Upstox News",
                            "hash": h_hash
                        })
                else:
                    # Token might be expired, print warning and proceed (RSS will still work)
                    print(f"[!] Upstox News API returned HTTP {response.status_code}. Skipping Upstox feed.")
        except Exception as e:
            print(f"[!] Upstox API connection failed: {e}")
            
        return headlines

    def process_feeds(self):
        """Scans all feeds, resolves targets, scores sentiment, and broadcasts alerts."""
        print(f"[*] Scanning feeds at {datetime.now(self.ist).strftime('%H:%M:%S IST')}...")
        
        new_items = self.fetch_rss_headlines() + self.fetch_upstox_headlines()
        if not new_items:
            return
            
        print(f"    Found {len(new_items)} new headlines. Processing...")
        
        for item in new_items:
            headline = html.unescape(html.unescape(item["headline"]))
            link = item["link"]
            h_hash = item["hash"]
            
            # Immediately add to cache to prevent reprocessing
            self.processed_hashes.add(h_hash)
            
            # Step 1: Resolve if this headline contains a targeted stock or sector catalyst
            direct_symbol, impacted_stocks, sector_name = resolve_catalyst(headline)
            
            # If no stock or sector was matched, skip it (Filter A)
            if not direct_symbol and not impacted_stocks:
                continue
                
            # Step 2: Score sentiment using FinBERT via Hugging Face API
            label, score = score_headline(headline)
            
            # Filter B: Reject weak or neutral headlines (Spam Prevention)
            if label == "NEUTRAL" or score < 0.70:
                print(f"    [Filtered] {headline} (Neutral/Low confidence: {score:.2f})")
                continue
                
            # Step 3: Broadcast the catalyst alert!
            print(f"    [💥 CATALYST DETECTED] {headline} ({label} - {score:.2f})")
            
            if direct_symbol:
                # Direct Stock Alert
                self.broadcaster.broadcast_stock_catalyst(
                    symbol=direct_symbol,
                    headline=headline,
                    label=label,
                    score=score,
                    link=link
                )
            elif sector_name:
                # Sector-wide Macro/Commodity Alert
                self.broadcaster.broadcast_sector_catalyst(
                    sector_name=sector_name,
                    headline=headline,
                    label=label,
                    score=score,
                    impacted_stocks=impacted_stocks,
                    link=link
                )
                
        # Save cache changes
        self._save_cache()

    def send_morning_briefing(self):
        """Fetches global macro indices and broadcasts a compact marquee style report."""
        print("[*] Compiling Morning Global Macro Briefing...")
        tickers = {
            "SP500": "^GSPC", "NSDQ": "^IXIC", "DOW": "^DJI",
            "GIFTNFT": "^NSEI", "NIKKEI": "^N225", "HSENG": "^HSI",
            "FTSE": "^FTSE", "DAX": "^GDAXI",
            "BRENT": "BZ=F", "GOLD": "GC=F", "COPPER": "HG=F",
            "USDINR": "INR=X"
        }
        
        data = {}
        for name, sym in tickers.items():
            try:
                t = yf.Ticker(sym)
                hist = t.history(period="2d")
                if not hist.empty and len(hist) >= 2:
                    c_prev = hist['Close'].iloc[-2]
                    c_curr = hist['Close'].iloc[-1]
                    pct = ((c_curr - c_prev) / c_prev) * 100
                    data[name] = {"price": round(c_curr, 2), "pct": round(pct, 2)}
                elif not hist.empty:
                    data[name] = {"price": round(hist['Close'].iloc[-1], 2), "pct": 0.0}
                else:
                    data[name] = {"price": "N/A", "pct": 0.0}
            except Exception as e:
                print(f"    [!] Error fetching {name} ({sym}): {e}")
                data[name] = {"price": "N/A", "pct": 0.0}

        def fmt(name, symbol_str):
            val = data.get(name, {"price": "N/A", "pct": 0.0})
            if val["price"] == "N/A":
                return f"{symbol_str} N/A"
            sign = "+" if val["pct"] >= 0 else ""
            arrow = "▲" if val["pct"] >= 0 else "▼"
            prefix = "$" if name in ["BRENT", "GOLD"] else ""
            return f"{symbol_str} {prefix}{val['price']} ({sign}{val['pct']}%) {arrow}"

        # Generate Morning Bias dynamically from actual fetched data
        nifty_val = data.get("GIFTNFT", {"pct": 0.0})
        nasdaq_val = data.get("NSDQ", {"pct": 0.0})
        brent_val = data.get("BRENT", {"pct": 0.0})

        if nifty_val["pct"] >= 0.25:
            bias_str = f"Positive open expected (GIFTNFT {'+' if nifty_val['pct'] >= 0 else ''}{nifty_val['pct']}%)."
        elif nifty_val["pct"] <= -0.25:
            bias_str = f"Negative open expected (GIFTNFT {nifty_val['pct']}%). Trade cautiously."
        else:
            bias_str = "Flat open expected."

        # Append dynamic sector notes
        if nasdaq_val["pct"] >= 0.5:
            bias_str += f" NASDAQ rally (+{nasdaq_val['pct']}%) may support IT stocks (TCS, INFY)."
        elif nasdaq_val["pct"] <= -0.5:
            bias_str += f" NASDAQ weakness ({nasdaq_val['pct']}%) may pressure IT stocks."

        if brent_val["pct"] >= 1.0:
            bias_str += f" Brent Crude spike (+{brent_val['pct']}%) — watch ASIANPAINT defensively, positive for ONGC."
        elif brent_val["pct"] <= -1.0:
            bias_str += f" Brent Crude drop ({brent_val['pct']}%) — tailwind for Paint and Aviation stocks."

        # Compile body
        body = (
            "🌎 <b>MORNING MACRO FEED — 08:15 IST</b> 📺\n\n"
            f"🇺🇸 {fmt('SP500', 'S&P500')} | 🇺🇸 {fmt('NSDQ', 'NSDQ')} | 🇺🇸 {fmt('DOW', 'DOW')}\n"
            f"🇮🇳 {fmt('GIFTNFT', 'GIFTNFT')} | 🇯🇵 {fmt('NIKKEI', 'NIKKEI')} | 🇭🇰 {fmt('HSENG', 'HSENG')}\n"
            f"🇬🇧 {fmt('FTSE', 'FTSE')} | 🇩🇪 {fmt('DAX', 'DAX')}\n"
            f"🛢️ {fmt('BRENT', 'BRENT')} | 🟡 {fmt('GOLD', 'GOLD')} | 🪨 {fmt('COPPER', 'COPPER')}\n"
            f"💵 {fmt('USDINR', 'USDINR')}\n\n"
            f"💡 <b>BIAS:</b> {bias_str}"
        )

        self.broadcaster.send_raw_message(body)
        print("[✅] Morning briefing broadcasted successfully.")

    def run_forever(self):
        """Infinite loop driving the daemon process."""
        print("==================================================")
        print("  REAL-TIME CATALYST FEED DAEMON ACTIVE")
        print(f"  System Time: {datetime.now(self.ist).strftime('%Y-%m-%d %H:%M:%S IST')}")
        print("==================================================\n")
        
        while True:
            try:
                # 8:15 AM Briefing Trigger (Mon-Fri only)
                now = datetime.now(self.ist)
                if now.hour == 8 and now.minute == 15:
                    current_date = now.strftime("%Y-%m-%d")
                    if self.last_briefing_date != current_date:
                        if now.weekday() < 5: # Monday = 0, Friday = 4
                            try:
                                self.send_morning_briefing()
                            except Exception as e:
                                print(f"[❌] Error sending morning briefing: {e}")
                        self.last_briefing_date = current_date

                self.process_feeds()
            except Exception as e:
                print(f"[❌] Critical error in processing loop: {e}")
            time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    monitor = CatalystMonitor()
    
    # Check if a single test run is requested
    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        monitor.process_feeds()
    else:
        monitor.run_forever()
