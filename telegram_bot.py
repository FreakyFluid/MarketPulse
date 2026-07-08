import os
import httpx
import pytz
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class TelegramBroadcaster:
    """Handles sending rich HTML alerts to the configured Telegram channel/chat."""
    
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.api_url = f"https://api.telegram.org/bot{self.token}/sendMessage" if self.token else None

    def send_raw_message(self, text: str) -> bool:
        """Sends a plain or formatted string via HTTP POST."""
        if not self.api_url or not self.chat_id:
            print("    [!] Telegram broadcaster not configured. Skipping notification.")
            return False
            
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        
        try:
            res = httpx.post(self.api_url, json=payload, timeout=10.0)
            if res.status_code == 200:
                return True
            else:
                print(f"    [❌] Telegram Send Error: HTTP {res.status_code} - {res.text}")
        except Exception as e:
            print(f"    [❌] Telegram connection failed: {e}")
            
        return False

    def broadcast_stock_catalyst(self, symbol: str, headline: str, label: str, score: float, link: str = None) -> bool:
        """Formats and broadcasts a stock-specific news catalyst alert."""
        badge = "🟢" if label == "POSITIVE" else "🔴"
        title = f"⚡ <b>CATALYST DETECTED — {symbol}</b> {badge}"
        
        body = (
            f"{title}\n\n"
            f"📰 <b>Headline:</b> {headline}\n\n"
            f"📊 <b>AI Sentiment:</b> {badge} {label} (Conf: {score:.2f})\n"
            f"⏱️ <b>Triggered:</b> {self._get_time_stamp()}\n"
        )
        
        if link:
            body += f"🔗 <a href=\"{link}\">Read Full Article</a>\n"
            
        return self.send_raw_message(body)

    def broadcast_sector_catalyst(self, sector_name: str, headline: str, label: str, score: float, impacted_stocks: list, link: str = None) -> bool:
        """Formats and broadcasts a sector-wide macro/commodity catalyst alert."""
        badge = "🟢" if label == "POSITIVE" else "🔴"
        title = f"⚡ <b>SECTOR CATALYST — {sector_name.upper()}</b> {badge}"
        
        stock_list_str = ""
        for s in impacted_stocks:
            stock_badge = "🟢" if label == "POSITIVE" else "🔴"
            # Override for specific inverse impact mapping if defined
            if s.get("impact") == "positive":
                stock_badge = "🟢"
            elif s.get("impact") == "negative":
                stock_badge = "🔴"
            stock_list_str += f"• {stock_badge} <code>{s['symbol']}</code>\n"
            
        body = (
            f"{title}\n\n"
            f"📰 <b>Headline:</b> {headline}\n\n"
            f"📊 <b>AI Sentiment:</b> {badge} {label} (Conf: {score:.2f})\n"
            f"📌 <b>Impacted Stocks:</b>\n{stock_list_str}\n"
            f"⏱️ <b>Triggered:</b> {self._get_time_stamp()}\n"
        )
        
        if link:
            body += f"🔗 <a href=\"{link}\">Read Full Article</a>\n"
            
        return self.send_raw_message(body)

    def _get_time_stamp(self) -> str:
        ist = pytz.timezone('Asia/Kolkata')
        return datetime.now(ist).strftime('%H:%M:%S IST')

if __name__ == "__main__":
    # Test layout
    broadcaster = TelegramBroadcaster()
    print("Testing local HTML layouts...")
    
    # Text-only dry run print
    mock_headline = "Wipro secures $150M cloud engineering deal from leading US healthcare provider"
    mock_stocks = [{"symbol": "WIPRO.NS", "impact": "direct"}]
    
    print("\n--- Dry Run Stock Alert ---")
    broadcaster.broadcast_stock_catalyst("WIPRO.NS", mock_headline, "POSITIVE", 0.92, "https://google.com")
    
    print("\n--- Dry Run Sector Alert ---")
    broadcaster.broadcast_sector_catalyst(
        "Oil & Gas", 
        "Brent Crude spikes above $90/barrel amid tensions in Middle East", 
        "POSITIVE", 
        0.87, 
        [{"symbol": "ONGC.NS", "impact": "positive"}, {"symbol": "ASIANPAINT.NS", "impact": "negative"}],
        "https://google.com"
    )
