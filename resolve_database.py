import sqlite3
import json
import os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GROWW_DB_PATH = os.path.join(BASE_DIR, "sector_database.json")
RESOLVED_DB_PATH = os.path.join(BASE_DIR, "resolved_sector_database.json")
INSTRUMENTS_DB_PATH = "/home/vinnie/upstox-mcp/instruments.db"

def clean_company_name(name: str) -> str:
    """Cleans up names to maximize matching probability in SQL."""
    name = name.upper()
    # Strip common suffixes and characters
    name = re.sub(r"\b(LTD|LIMITED|CORP|CORPORATION|INDS|INDUSTRIES|INDIA)\b", "", name)
    name = re.sub(r"[^\w\s]", "", name)
    return " ".join(name.split())

# Specific manual overrides for demerged or tricky companies
MANUAL_OVERrides = {
    "TATA MOTORS PASSENGER VEHICLES": "TMPV.NS",
    "TATA MOTORS COMMERCIAL VEHICLES": "TMCV.NS",
    "TATA MOTORS": "TMCV.NS",
    "LT TECHNOLOGY SERVICES": "LTTS.NS",
    "ORACLE FINANCIAL SERVICES SOFTWARE": "OFSS.NS"
}

def resolve_tickers():
    if not os.path.exists(GROWW_DB_PATH):
        print(f"[❌] Groww database not found at {GROWW_DB_PATH}")
        return
        
    if not os.path.exists(INSTRUMENTS_DB_PATH):
        print(f"[❌] Instruments database not found at {INSTRUMENTS_DB_PATH}")
        return
        
    print(f"[*] Loading scraped data from {GROWW_DB_PATH}...")
    with open(GROWW_DB_PATH, "r") as f:
        groww_data = json.load(f)
        
    print(f"[*] Connecting to database {INSTRUMENTS_DB_PATH}...")
    conn = sqlite3.connect(INSTRUMENTS_DB_PATH)
    cursor = conn.cursor()
    
    resolved_database = {}
    total_resolved = 0
    total_unresolved = 0
    
    for sector, companies in groww_data.items():
        print(f"Resolving sector: '{sector}'...")
        resolved_companies = []
        
        for company in companies:
            name = company["name"]
            slug = company["slug"]
            
            # Step 1: Direct Name Match
            cleaned = clean_company_name(name)
            
            # Check manual overrides first
            if cleaned in MANUAL_OVERrides:
                ticker = MANUAL_OVERrides[cleaned]
                total_resolved += 1
                resolved_companies.append({
                    "name": name,
                    "ticker": ticker
                })
                continue
                
            # Try a progressive SQL search (starts-with, contains, then fallback matches)
            ticker = None
            row = None
            
            # Query 1: Exact Name prefix match (fastest and most accurate)
            cursor.execute(
                "SELECT trading_symbol FROM instruments WHERE segment = 'NSE_EQ' AND instrument_type IN ('EQ', 'BE', 'SM', 'ST') AND name LIKE ? LIMIT 1",
                (f"{cleaned}%",)
            )
            row = cursor.fetchone()
            
            # Query 2: Try exact name parts matching
            if not row:
                cursor.execute(
                    "SELECT trading_symbol FROM instruments WHERE segment = 'NSE_EQ' AND instrument_type IN ('EQ', 'BE', 'SM', 'ST') AND name LIKE ? LIMIT 1",
                    (f"%{cleaned}%",)
                )
                row = cursor.fetchone()
                
            # Query 3: Match using slug keywords
            if not row:
                slug_keywords = clean_company_name(slug.replace('-', ' '))
                cursor.execute(
                    "SELECT trading_symbol FROM instruments WHERE segment = 'NSE_EQ' AND instrument_type IN ('EQ', 'BE', 'SM', 'ST') AND name LIKE ? LIMIT 1",
                    (f"%{slug_keywords}%",)
                )
                row = cursor.fetchone()
                
            # Query 4: Try matching by first two words if name is long (handles abbreviations like MOB vs MOBILITY)
            if not row:
                words = cleaned.split()
                if len(words) >= 2:
                    first_two = f"{words[0]} {words[1]}"
                    if first_two not in ["TATA", "ADANI", "RELIANCE", "BIRLA", "JINDAL"]:
                        cursor.execute(
                            "SELECT trading_symbol FROM instruments WHERE segment = 'NSE_EQ' AND instrument_type IN ('EQ', 'BE', 'SM', 'ST') AND name LIKE ? LIMIT 1",
                            (f"{first_two}%",)
                        )
                        row = cursor.fetchone()
                
            if row:
                ticker = f"{row[0]}.NS"
                total_resolved += 1
                resolved_companies.append({
                    "name": name,
                    "ticker": ticker
                })
            else:
                # Add to unresolved logs for manual audit if needed
                total_unresolved += 1
                
        if resolved_companies:
            resolved_database[sector] = resolved_companies
            
    conn.close()
    
    # Save the output
    with open(RESOLVED_DB_PATH, "w") as f:
        json.dump(resolved_database, f, indent=4)
        
    print("\n==================================================")
    print("  RESOLVER COMPILATION COMPLETE")
    print(f"  Total Resolved Tickers  : {total_resolved}")
    print(f"  Total Unresolved        : {total_unresolved}")
    print(f"  Success Rate            : {(total_resolved/(total_resolved+total_unresolved))*100:.1f}%")
    print(f"  Saved Finalized DB to   : {RESOLVED_DB_PATH}")
    print("==================================================\n")

if __name__ == "__main__":
    resolve_tickers()
