import os
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://router.huggingface.co/hf-inference/models/ProsusAI/finbert"

def query_hf_api(headline: str) -> dict:
    """Queries the Hugging Face Inference API for FinBERT classification."""
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("    [!] Warning: HF_TOKEN env variable not set. Using unauthenticated request.")
        headers = {}
    else:
        headers = {"Authorization": f"Bearer {hf_token}"}
        
    payload = {"inputs": headline}
    
    # Retry up to 3 times for cold starts (HTTP 503 model loading states)
    for attempt in range(3):
        try:
            response = httpx.post(API_URL, headers=headers, json=payload, timeout=20.0)
            if response.status_code == 200:
                data = response.json()
                # Expected format: [[{"label": "positive", "score": 0.95}, ...]]
                if isinstance(data, list) and len(data) > 0 and isinstance(data[0], list):
                    return data[0]
                elif isinstance(data, dict) and "error" in data:
                    print(f"    [!] HF API returned error: {data['error']}")
                else:
                    return data
            elif response.status_code == 503:
                # Model is loading on Hugging Face servers
                err_json = response.json()
                wait_time = err_json.get("estimated_time", 10.0)
                print(f"    [!] HF Model loading (503). Retrying in {wait_time:.1f}s... (Attempt {attempt+1}/3)")
                time.sleep(min(wait_time, 15.0))
            else:
                print(f"    [❌] HF API Error: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            print(f"    [❌] Connection failed: {e}")
            
    return [{"label": "neutral", "score": 1.0}]

def score_headline(headline: str) -> tuple[str, float]:
    """
    Classifies a headline and returns its predicted sentiment label and score.
    Returns: (label: POSITIVE/NEGATIVE/NEUTRAL, score: float)
    """
    raw_results = query_hf_api(headline)
    
    if not raw_results or not isinstance(raw_results, list):
        return "NEUTRAL", 0.0
        
    # Extract the highest probability label
    try:
        top_prediction = max(raw_results, key=lambda x: x.get("score", 0.0))
        label = top_prediction.get("label", "neutral").upper()
        score = top_prediction.get("score", 0.0)
        return label, score
    except Exception as e:
        print(f"    [!] Error parsing FinBERT predictions: {e}")
        return "NEUTRAL", 0.0

if __name__ == "__main__":
    # Test case (will run if executed directly, warning about connection if offline)
    test_headline = "Tata Motors profits surge 75% beating analysts estimations"
    print(f"Scoring: '{test_headline}'")
    lbl, scr = score_headline(test_headline)
    print(f"Result: {lbl} (Conf: {scr:.2f})")
