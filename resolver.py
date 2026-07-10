import json
import os
import re
from typing import List, Dict, Tuple, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resolved_sector_database.json")

# --- Common words that are also company names (must not match as a single word) ---
GENERIC_DISTRACTORS = {
    "DOLLAR", "GOLD", "SILVER", "STEEL", "POWER", "CABLE", "GLASS", 
    "PAPER", "CARBON", "STAR", "SUN", "BEST", "WELL", "COAL", "GAS", "SHREE"
}

# --- Famous Abbreviations (Priority 0 Matches) ---
FAMOUS_ABBREVIATIONS = {
    "TCS": "TCS.NS",
    "INFY": "INFY.NS",
    "SBI": "SBIN.NS",
    "HDFC": "HDFCBANK.NS",
    "ICICI": "ICICIBANK.NS",
    "RELIANCE": "RELIANCE.NS",
    "RIL": "RELIANCE.NS",
    "ITC": "ITC.NS",
    "ONGC": "ONGC.NS",
    "BPCL": "BPCL.NS",
    "HAL": "HAL.NS",
    "BEL": "BEL.NS",
    "L&T": "LT.NS",
    "LT": "LT.NS",
    "M&M": "M&M.NS"
}

class CatalystResolver:
    def __init__(self):
        self.sector_data = self._load_database()
        self.company_map, self.sector_map = self._build_lookup_tables()

    def _load_database(self) -> dict:
        """Loads the compiled resolved sector database."""
        if os.path.exists(DB_PATH):
            try:
                with open(DB_PATH, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[!] Error loading resolved database: {e}")
        else:
            print(f"[!] Warning: Resolved database not found at {DB_PATH}. Using empty lookup.")
        return {}

    def _build_lookup_tables(self) -> Tuple[Dict[str, str], Dict[str, dict]]:
        """Compiles flat lookup maps for O(1) matching speed."""
        company_map = {}
        sector_map = {}
        
        for sector, stocks in self.sector_data.items():
            # Build sector-specific details
            sector_map[sector] = {
                "keywords": self._get_sector_keywords(sector),
                "stocks": [{"symbol": s["ticker"], "impact": "neutral"} for s in stocks]
            }
            
            # Build direct company lookup
            for s in stocks:
                name = s["name"].upper()
                ticker = s["ticker"]
                
                # Strip common corporate suffixes to get clean matching names
                clean_name = re.sub(r"\b(LTD|LIMITED|CORP|CORPORATION|INDS|INDUSTRIES|INDIA)\b", "", name)
                clean_name = " ".join(clean_name.split()).strip()
                
                if len(clean_name) > 3: # Ignore tiny names to prevent false positive matches
                    # Only allow single-word match if it's not a generic distractor
                    if clean_name not in GENERIC_DISTRACTORS:
                        company_map[clean_name] = ticker
                    else:
                        # For generic words, require the full corporate name (e.g. "DOLLAR INDUSTRIES")
                        full_clean = " ".join(name.split()).strip()
                        company_map[full_clean] = ticker
                    
                    # Heuristic: Add first two words for long names (e.g. "AMARA RAJA ENERGY" -> "AMARA RAJA")
                    words = clean_name.split()
                    if len(words) >= 3:
                        short_name = " ".join(words[:2])
                        # Ignore generic brand names to prevent false positive crossovers
                        if short_name not in ["TATA", "ADANI", "RELIANCE", "BIRLA", "JINDAL", "ADANI GREEN", "TATA POWER"] and short_name not in GENERIC_DISTRACTORS:
                            company_map[short_name] = ticker
                    
        return company_map, sector_map

    def _get_sector_keywords(self, sector: str) -> List[str]:
        """Maps sector names to a list of keyword variations."""
        # Split sector names into keyword variations (e.g. "Information Technology" -> ["information technology", "it"])
        name = sector.lower()
        kws = [name]
        
        # Custom short-forms/aliases for common sectors
        aliases = {
            "information technology": ["it services", "software deal", "cloud deal", "digitization"],
            "banks": ["bank", "npa", "rbi", "repo rate", "lending", "credit policy"],
            "auto manufacturers": ["auto", "car sale", "suv", "ev sale"],
            "oil": ["crude", "brent", "refinery", "petroleum"],
            "metals & mining": ["steel", "iron ore", "aluminum", "copper", "coal", "mining"],
            "gas distribution": ["cng", "piped gas", "natural gas"],
            "defence": ["weapon", "warship", "fighter jet", "hal", "bel", "drdo"],
            "jewellery": ["jewel", "gold price", "silver price"]
        }
        
        if name in aliases:
            kws.extend(aliases[name])
            
        return [k.upper() for k in kws]

    def resolve(self, headline: str) -> Tuple[Optional[str], List[Dict], Optional[str]]:
        """
        Resolves a headline to a direct stock or indirect sector catalyst.
        Returns: (Direct Stock Symbol, List of Impacted Stocks, Sector Name)
        """
        headline_upper = headline.upper()
        
        # 0. Priority 0: Check famous abbreviations
        for abbr, ticker in FAMOUS_ABBREVIATIONS.items():
            pattern = r'\b' + re.escape(abbr) + r'\b'
            if re.search(pattern, headline_upper):
                return ticker, [{"symbol": ticker, "impact": "direct"}], None
                
        # 1. First priority: Check direct company name match
        for company_name, ticker in self.company_map.items():
            pattern = r'\b' + re.escape(company_name) + r'\b'
            if re.search(pattern, headline_upper):
                return ticker, [{"symbol": ticker, "impact": "direct"}], None
                
        # 2. Second priority: Check sector/commodity mapping
        for sector_name, info in self.sector_map.items():
            for kw in info["keywords"]:
                pattern = r'\b' + re.escape(kw) + r'\b'
                if re.search(pattern, headline_upper):
                    impacted_stocks = []
                    for stock in info["stocks"]:
                        symbol = stock["symbol"]
                        impact = stock["impact"]
                        
                        # Apply custom macro rules
                        if "CRUDE" in headline_upper or "BRENT" in headline_upper:
                            if symbol == "ONGC.NS":
                                impact = "positive"
                            elif symbol == "ASIANPAINT.NS":
                                impact = "negative"
                                
                        impacted_stocks.append({"symbol": symbol, "impact": impact})
                        
                    return None, impacted_stocks[:5], sector_name # Limit to top 5 stocks to avoid Telegram formatting limits

        return None, [], None

# Instantiate a global resolver object
resolver = CatalystResolver()

def resolve_catalyst(headline: str) -> Tuple[Optional[str], List[Dict], Optional[str]]:
    """Backward-compatible wrapper for the global resolver instance."""
    return resolver.resolve(headline)

if __name__ == "__main__":
    # Test cases
    test_headlines = [
        "Exide Industries secures massive battery export contract from Germany",
        "Amara Raja plans ₹9,000 Crore investment in EV battery Gigafactory in Telangana",
        "Brent crude drops below $75/barrel as production rises",
        "HAL gets ₹50,000 Crore proposal from Ministry for fighter jet upgrades"
    ]
    
    print("Testing Updated Dynamic Resolver:")
    for h in test_headlines:
        direct, impacted, sector = resolve_catalyst(h)
        print(f"\nHeadline: {h}")
        print(f"  Direct Stock : {direct}")
        print(f"  Sector       : {sector}")
        print(f"  Impact List  : {impacted}")
