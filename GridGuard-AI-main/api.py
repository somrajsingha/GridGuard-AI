"""
Electricity Theft Detection System - FastAPI Backend v4
=======================================================
• Every GET /api/houses call runs the detector fresh → random data on every refresh.
• The static theft_detection_results_v4.json is only written on startup (and by
  electricity_theft_detector_v4.py when run standalone).
• POST /api/simulate applies boost factors on top of one fresh random baseline.
• GET /api/explanation?house_id=<id> calls Google Gemini for a human-readable analysis,
  with a 5-minute server-side cache and graceful fallback if key is missing.
"""
import json
import os
import time
import copy
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Load .env so GEMINI_API_KEY is available without setting env vars manually
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass  # python-dotenv not installed; rely on system environment variables

# Import the v4 generator
import sys
sys.path.insert(0, str(Path(__file__).parent))
from electricity_theft_detector_v4 import generate_random_data, save_to_json

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────
app = FastAPI(
    title="Electricity Theft Detection API",
    description="Real-time electricity theft detection powered by ML (v4 - random data + GPT explanations)",
    version="4.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Paths & config
# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
JSON_PATH = BASE_DIR / "theft_detection_results_v4.json"

# ─── Gemini API Key ───────────────────────────────────────────────────────────
# To change/update the key: edit the .env file in this same folder.
# Set:  GEMINI_API_KEY=AIzaSy...
# Then restart the server for the change to take effect.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# In-memory explanation cache: {house_id: (text, source, timestamp)}
# ─────────────────────────────────────────────
_explanation_cache: dict[int, tuple[str, str, float]] = {}
CACHE_TTL = 300  # 5 minutes


# ─────────────────────────────────────────────
# Startup
# ─────────────────────────────────────────────
@app.on_event("startup")
def startup_event():
    data = generate_random_data()
    save_to_json(data, JSON_PATH)
    has_key = "YES" if GEMINI_API_KEY else "NO (fallback mode)"
    print(f"[API v4.1] Startup data written -> {JSON_PATH.name}")
    print(f"[API v4.1] Gemini key present: {has_key}")


# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────
class SimulateRequest(BaseModel):
    percent: float  # 0-100


# ─────────────────────────────────────────────
# Helper: simulate theft increase
# ─────────────────────────────────────────────
def simulate_theft_increase(base_data: dict, percent: float) -> dict:
    """
    Boost risk scores so map colours change visibly.
    Low  (<35):  factor 3.5
    Med  (35-64): factor 1.8
    High (>=65):  factor 0.6
    """
    data = copy.deepcopy(base_data)
    p = percent / 100.0

    updated_houses = []
    for house in data["houses"]:
        h = copy.deepcopy(house)
        base_risk = h["risk_score"]

        if base_risk < 35:
            factor = 3.5
        elif base_risk < 65:
            factor = 1.8
        else:
            factor = 0.6

        new_risk = base_risk * (1 + p * factor)
        h["risk_score"] = min(100, round(new_risk))

        if h["risk_score"] >= 65:
            h["risk_level"] = "high"
        elif h["risk_score"] >= 35:
            h["risk_level"] = "medium"
        else:
            h["risk_level"] = "low"

        h["average_consumption"] = round(h["average_consumption"] * (1 + p * 0.5), 4)
        h["max_consumption"] = round(h["max_consumption"] * (1 + p * 0.6), 4)
        h["consumption_difference"] = round(h["consumption_difference"] * (1 + p * 0.4), 4)

        updated_houses.append(h)

    updated_houses.sort(key=lambda x: x["risk_score"], reverse=True)
    for idx, h in enumerate(updated_houses):
        h["priority_rank"] = idx + 1

    top5 = [copy.deepcopy(h) for h in updated_houses[:5]]

    base_loss = base_data["transformer"]["loss"]
    base_loss_pct = base_data["transformer"]["loss_percentage"]
    base_est_loss = base_data["transformer"]["estimated_loss_in_rupees"]

    loss_multiplier = 1 + p * 1.5
    loss_boost = round(base_loss * loss_multiplier, 4)
    loss_pct = round(base_loss_pct * loss_multiplier, 4)
    est_loss = round(base_est_loss * loss_multiplier, 2)

    new_status = "Normal"
    if loss_pct > 0.12:
        new_status = "Critical"
    elif loss_pct > 0.06:
        new_status = "Warning"

    data["transformer"]["loss"] = loss_boost
    data["transformer"]["loss_percentage"] = loss_pct
    data["transformer"]["estimated_loss_in_rupees"] = est_loss
    data["transformer"]["status"] = new_status

    data["transformer_metrics"]["transformer_loss"] = loss_boost
    data["transformer_metrics"]["loss_ratio"] = loss_pct
    data["transformer_metrics"]["estimated_loss_in_rupees"] = est_loss
    data["transformer_metrics"]["zone_status"] = new_status
    data["transformer_metrics"]["total_house_consumption"] = round(
        base_data["transformer_metrics"]["total_house_consumption"] * (1 + p * 0.3), 4
    )

    high_count = sum(1 for h in updated_houses if h["risk_level"] == "high")
    data["insights"]["top_5_houses"] = top5
    data["insights"]["total_high_risk"] = high_count
    data["insights"]["estimated_loss"] = est_loss
    data["insights"]["zone_status"] = new_status
    data["houses"] = updated_houses

    return data


# ─────────────────────────────────────────────
# Helper: build rule-based fallback explanation + solution
# ─────────────────────────────────────────────
def build_fallback_explanation(house: dict) -> dict:
    """Returns dict with 'explanation' and 'solution' keys."""
    risk_level = house.get("risk_level", "unknown")
    risk_score = house.get("risk_score", 0)
    primary = house.get("reason", {}).get("primary", "statistical anomaly")
    secondary = house.get("reason", {}).get("secondary", [])
    avg_c = house.get("average_consumption", 0)
    max_c = house.get("max_consumption", 0)
    night = house.get("night_usage_ratio", 0)
    diff = house.get("consumption_difference", 0)
    zone = house.get("zone", "Unknown Zone")
    confidence = house.get("confidence", "N/A")

    sec_str = ""
    if secondary:
        sec_str = f" with additional indicators including {', '.join(secondary[:2])}"

    if risk_level == "high":
        action = (
            "Immediate field inspection and meter audit are strongly recommended. "
            "Consider temporary disconnection pending verification."
        )
    elif risk_level == "medium":
        action = (
            "Schedule a routine inspection within the next billing cycle. "
            "Cross-check meter readings against logged consumption data."
        )
    else:
        action = (
            "Monitor closely over the next 30 days. "
            "No immediate action required unless patterns worsen."
        )

    explanation = (
        f"House shows {primary}{sec_str}, scoring {risk_score}/100 ({confidence}). "
        f"Average consumption is {avg_c:.1f} kWh with a peak of {max_c:.1f} kWh; "
        f"night usage constitutes {night*100:.0f}% of total load — "
        f"{'notably high for residential premises' if night > 0.5 else 'within normal range'}. "
        f"Consumption difference of {diff:.2f} kWh suggests "
        f"{'significant meter tampering or bypass' if diff > 5 else 'minor discrepancy worth monitoring'}. "
        f"Zone: {zone}. {action}"
    )

    # Build a targeted solution based on the primary theft pattern
    primary_lower = primary.lower()
    if "bypass" in primary_lower or "tamper" in primary_lower:
        solution = (
            "Replace the existing mechanical meter with a tamper-proof smart meter equipped with anti-bypass seals and real-time alerts. "
            "Install a secondary CT (current transformer) clamp at the service entry point to cross-validate readings independently. "
            "File an FIR if bypassing is physically confirmed during the field visit, and initiate recovery billing for the estimated theft period."
        )
    elif "night" in primary_lower or "night usage" in primary_lower:
        solution = (
            "Deploy a smart meter with time-of-use (ToU) tariff enforcement to log and bill nocturnal consumption accurately. "
            "Install a load-limiter relay that triggers an alert when night-time load exceeds the registered contract demand. "
            "Cross-check with neighbours' night profiles and inspect for illegal sub-connections or shared hookups in the premises."
        )
    elif "mismatch" in primary_lower or "load" in primary_lower:
        solution = (
            "Conduct a transformer-level energy audit: compare aggregate meter readings against the transformer output over one full billing cycle. "
            "Upgrade the distribution transformer with an IoT-enabled monitoring module to detect unaccounted load in real time. "
            "Map all service connections on the feeder to identify any unregistered or unofficially added consumers drawing unmetered power."
        )
    elif "spike" in primary_lower or "peak" in primary_lower:
        solution = (
            "Install a waveform-logging power quality analyser at the meter point to capture and timestamp anomalous consumption spikes. "
            "Cross-reference spike events with local weather data and business activity logs to rule out legitimate causes. "
            "If spikes are unexplained, issue a show-cause notice and schedule a surprise meter verification within 48 hours."
        )
    elif "phase" in primary_lower or "imbalance" in primary_lower:
        solution = (
            "Dispatch a line technician to physically inspect the phase connections and verify that all three phases are metered correctly. "
            "Replace single-phase meters with a 3-phase smart meter and enable per-phase consumption logging to catch load shifted to an unmetered phase. "
            "Seal all meter terminal blocks with tamper-evident epoxy and schedule quarterly phase-balance audits for this cluster."
        )
    else:
        solution = (
            f"Initiate a structured field investigation: verify the meter seal integrity, inspect wiring between the service entry and meter, "
            f"and compare physical appliance load against the recorded demand of {avg_c:.1f} kWh avg / {max_c:.1f} kWh peak. "
            f"If discrepancies persist, replace the existing meter with a certified smart meter and enroll the consumer in a monthly energy audit programme."
        )

    return {"explanation": explanation, "solution": solution}


# ─────────────────────────────────────────────
# Helper: call Google Gemini API (sync, simple http)
# Returns dict with 'explanation' and 'solution' keys
# Retries up to 3 times on 429 rate-limit with exponential backoff
# ─────────────────────────────────────────────
def call_gemini(house: dict) -> dict:
    import urllib.request
    import ssl
    import urllib.error

    prompt = (
        "You are an electricity theft detection expert assisting a government electricity board.\n\n"
        f"Analyze the following house data:\n"
        f"- Risk Score: {house.get('risk_score')}/100\n"
        f"- Risk Level: {house.get('risk_level')}\n"
        f"- Average Consumption: {house.get('average_consumption')} kWh\n"
        f"- Max Consumption: {house.get('max_consumption')} kWh\n"
        f"- Night Usage Ratio: {house.get('night_usage_ratio'):.2f} ({house.get('night_usage_ratio', 0)*100:.0f}% at night)\n"
        f"- Consumption Difference: {house.get('consumption_difference')} kWh\n"
        f"- Transformer Load Share: {house.get('transformer_load_share')}\n"
        f"- Primary Reason Flagged: {house.get('reason', {}).get('primary', 'N/A')}\n"
        f"- Secondary Reasons: {', '.join(house.get('reason', {}).get('secondary', [])) or 'None'}\n\n"
        "Respond ONLY with a valid JSON object (no markdown, no extra text) with exactly these two fields:\n"
        "{\n"
        '  "explanation": "2-3 sentences: why this house is suspicious, which patterns indicate theft, and what field action to take.",\n'
        '  "solution": "2-3 sentences: concrete step-by-step remediation to stop the theft — specific to the detected pattern (e.g. meter bypass → tamper-proof smart meter + FIR; high night usage → ToU tariff + load-limiter relay; load mismatch → transformer audit + IoT monitor; phase imbalance → 3-phase smart meter + seal; etc.)."\n'
        "}\n"
    )

    # Read the key fresh here so it always picks up what dotenv loaded
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    # Gemini 2.5 Flash Lite — fastest model available on this key's quota tier
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash-lite:generateContent?key={api_key}"
    )

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "maxOutputTokens": 300,
            "temperature": 0.3,
        },
    }).encode("utf-8")

    # Build an SSL context — try certifi first, fall back to unverified
    try:
        import certifi
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ssl_ctx = ssl._create_unverified_context()
        print("[SSL] certifi not found — using unverified SSL context")

    MAX_RETRIES = 3
    for attempt in range(1, MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                # Gemini response: candidates[0].content.parts[0].text
                content = body["candidates"][0]["content"]["parts"][0]["text"].strip()
                parsed = json.loads(content)
                print(f"[Gemini] House #{house.get('house_id')}: succeeded on attempt {attempt}")
                return {
                    "explanation": parsed.get("explanation", "").strip(),
                    "solution": parsed.get("solution", "").strip(),
                }
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")[:300]
            except Exception:
                pass
            print(f"[Gemini] Attempt {attempt}/{MAX_RETRIES} — HTTP {e.code}: {err_body}")
            if e.code == 429 and attempt < MAX_RETRIES:
                wait_sec = 2 ** attempt  # 2s, 4s, 8s
                print(f"[Gemini] Rate limited (429) — waiting {wait_sec}s before retry...")
                time.sleep(wait_sec)
                continue
            raise
        except Exception as e:
            print(f"[Gemini] Attempt {attempt}/{MAX_RETRIES} — error: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise


# ─────────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "Electricity Theft Detection API v4.1 - Online"}


@app.get("/api/houses")
def get_all_houses():
    """
    Generates fresh random detection data on EVERY call.
    This means the map, charts, and risk scores refresh with new data each time.
    Also persists the result to theft_detection_results_v4.json.
    """
    data = generate_random_data()
    save_to_json(data, JSON_PATH)
    return data


@app.get("/api/insights")
def get_insights():
    """Returns top 5 houses, total high risk count, estimated loss - freshly generated."""
    data = generate_random_data()
    return {
        "top_5_houses": data["insights"]["top_5_houses"],
        "total_high_risk": data["insights"]["total_high_risk"],
        "estimated_loss": data["insights"]["estimated_loss"],
        "zone_status": data["insights"]["zone_status"],
    }


@app.get("/api/transformer")
def get_transformer():
    """Returns transformer node data - freshly generated."""
    data = generate_random_data()
    return {
        "transformer": data["transformer"],
        "transformer_metrics": data["transformer_metrics"],
    }


@app.post("/api/simulate")
def simulate(req: SimulateRequest):
    """
    Simulates a theft increase by the given percentage ON TOP of a fresh random baseline.
    Input: { "percent": 20 }
    Returns: updated full dataset with new risk levels.
    """
    if req.percent < 0 or req.percent > 100:
        raise HTTPException(status_code=400, detail="percent must be between 0 and 100")

    base = generate_random_data()
    result = simulate_theft_increase(base, req.percent)
    return result


@app.get("/api/explanation")
def get_explanation(house_id: int = Query(..., ge=1, le=100)):
    """
    Returns an AI-powered explanation + solution for the given house.

    - If Gemini key is configured: calls Gemini 1.5 Flash for structured JSON with
      'explanation' (why suspicious / what patterns) and 'solution' (how to fix it).
    - If no key or Gemini fails: returns rich rule-based fallback for both fields.
    - Results cached server-side for 5 minutes per house_id.
    """
    # Check cache first
    if house_id in _explanation_cache:
        cached = _explanation_cache[house_id]
        if time.time() - cached["ts"] < CACHE_TTL:
            return {
                "house_id": house_id,
                "ai_explanation": cached["explanation"],
                "solution": cached["solution"],
                "source": cached["source"],
            }
        else:
            del _explanation_cache[house_id]

    # Get fresh house data
    data = generate_random_data()
    house = next((h for h in data["houses"] if h["house_id"] == house_id), None)
    if not house:
        raise HTTPException(status_code=404, detail=f"House {house_id} not found")

    source = "fallback"
    result = {"explanation": "", "solution": ""}

    # Try Gemini if key is present (re-read fresh in case dotenv loaded after module init)
    if os.environ.get("GEMINI_API_KEY", "").strip():
        try:
            result = call_gemini(house)
            source = "gemini"
            print(f"[Gemini] House #{house_id}: explanation+solution generated via Gemini")
        except Exception as e:
            print(f"[Gemini] House #{house_id}: Gemini failed ({e}), using fallback")
            result = build_fallback_explanation(house)
    else:
        print(f"[Gemini] No GEMINI_API_KEY — using rule-based fallback for house #{house_id}")
        result = build_fallback_explanation(house)

    # Store in cache (new dict-based format)
    _explanation_cache[house_id] = {
        "explanation": result["explanation"],
        "solution": result["solution"],
        "source": source,
        "ts": time.time(),
    }

    return {
        "house_id": house_id,
        "ai_explanation": result["explanation"],
        "solution": result["solution"],
        "source": source,
    }


# ─────────────────────────────────────────────
# Dev runner
# ─────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
