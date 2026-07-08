import httpx
from bs4 import BeautifulSoup
import json
import re
import time

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def clean_stock_name(name: str) -> str:
    """Cleans up common corporate suffix junk to make resolving easier."""
    name = name.upper()
    name = re.sub(r"\b(LTD|LIMITED|INDIA|INDUSTRIES|CORP|CORPORATION|BK|BANK|INDS)\b", "", name)
    return name.strip()

def get_sector_links() -> list:
    """Scrapes the main Groww sector page to get all trending sector URLs."""
    url = "https://groww.in/stocks/sectors-trending"
    print(f"[*] Fetching main sectors index from {url}...")
    
    try:
        res = httpx.get(url, headers=HEADERS, timeout=15.0)
        if res.status_code != 200:
            print(f"[❌] Failed to load index: HTTP {res.status_code}")
            return []
            
        soup = BeautifulSoup(res.text, 'html.parser')
        links = []
        
        # Groww sector list links contain '/sectors-trending/'
        for link in soup.find_all('a', href=True):
            href = link['href']
            if '/sectors-trending/' in href:
                name = link.get_text(strip=True)
                full_url = href if href.startswith("http") else f"https://groww.in{href}"
                if name and full_url not in [l['url'] for l in links]:
                    links.append({"name": name, "url": full_url})
                    
        print(f"[✅] Identified {len(links)} sectors on Groww.")
        return links
    except Exception as e:
        print(f"[❌] Error fetching index: {e}")
        return []

def scrape_sector_stocks(sector_url: str) -> list:
    """Scrapes a specific sector page and extracts only the stocks in the table."""
    try:
        res = httpx.get(sector_url, headers=HEADERS, timeout=15.0)
        if res.status_code != 200:
            return []
            
        soup = BeautifulSoup(res.text, 'html.parser')
        stocks = []
        
        # Groww wraps the actual stock listing in a table element
        table = soup.find('table')
        if table:
            # Extract links inside this table only (ignores sidebar/ads)
            for link in table.find_all('a', href=True):
                href = link['href']
                if '/stocks/' in href and not '/sectors' in href:
                    raw_name = link.get_text(strip=True)
                    # Groww slugs are clean versions of the company name (e.g. exide-industries-ltd)
                    slug = href.split('/')[-1]
                    if raw_name:
                        stocks.append({
                            "name": raw_name,
                            "slug": slug
                        })
        else:
            # Fallback if table tag isn't found - fetch first few stock links
            print(f"    [!] Warning: No table element found for {sector_url}. Using fallback parsing.")
            links = soup.find_all('a', href=True)
            count = 0
            for link in links:
                href = link['href']
                if '/stocks/' in href and not '/sectors' in href and not href == '/stocks':
                    raw_name = link.get_text(strip=True)
                    slug = href.split('/')[-1]
                    # Groww shows popular stocks on sidebar, we stop after 15 to avoid ads
                    if count >= 15:
                        break
                    if raw_name and raw_name not in ["Intraday", "MTF", "Stock Screener", "Stock Events"]:
                        stocks.append({
                            "name": raw_name,
                            "slug": slug
                        })
                        count += 1
                        
        return stocks
    except Exception as e:
        print(f"    [❌] Error scraping sector page: {e}")
        return []

def harvest_all():
    sectors = get_sector_links()
    if not sectors:
        print("[!] No sectors found. Aborting.")
        return
        
    database = {}
    total_scraped = 0
    
    for idx, sec in enumerate(sectors):
        name = sec["name"]
        url = sec["url"]
        print(f"[{idx+1}/{len(sectors)}] Scraping '{name}'...")
        
        stocks = scrape_sector_stocks(url)
        if stocks:
            database[name] = stocks
            total_scraped += len(stocks)
            print(f"    [✅] Extracted {len(stocks)} stocks.")
        else:
            print(f"    [!] No stocks found for '{name}'.")
            
        # Polite throttling to avoid hitting Groww limits
        time.sleep(1.5)
        
    import os
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sector_database.json")
    with open(output_file, "w") as f:
        json.dump(database, f, indent=4)
        
    print("\n==================================================")
    print("  HARVESTING COMPLETE")
    print(f"  Total Sectors Scraped: {len(database)}")
    print(f"  Total Stocks Mapped  : {total_scraped}")
    print(f"  Database Saved to    : {output_file}")
    print("==================================================\n")

if __name__ == "__main__":
    harvest_all()
