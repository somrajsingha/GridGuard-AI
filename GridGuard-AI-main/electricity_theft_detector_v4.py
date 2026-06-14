"""
Electricity Theft Detector v4
==============================
Generates a FULLY RANDOMIZED detection result every time it runs.
Output: theft_detection_results_v4.json (same schema as v3)

Usage:
    python electricity_theft_detector_v4.py

The API (api.py) calls generate_random_data() directly so every
/api/houses request produces fresh random data — no caching.
"""

import json
import random
import math
from datetime import datetime
from pathlib import Path

# ──────────────────────────────────────────────
# Fixed house positions (Chandigarh sector grid)
# These never change so the map looks consistent
# ──────────────────────────────────────────────
HOUSE_POSITIONS = [
    (30.7352, 76.7700), (30.7251, 76.7741), (30.7353, 76.7806),
    (30.7376, 76.7834), (30.7317, 76.7785), (30.7289, 76.7868),
    (30.7385, 76.7726), (30.7318, 76.7750), (30.7276, 76.7847),
    (30.7253, 76.7770), (30.7305, 76.7763), (30.7286, 76.7703),
    (30.7325, 76.7719), (30.7415, 76.7710), (30.7292, 76.7820),
    (30.7410, 76.7766), (30.7271, 76.7708), (30.7362, 76.7849),
    (30.7430, 76.7865), (30.7406, 76.7770), (30.7324, 76.7860),
    (30.7266, 76.7765), (30.7367, 76.7834), (30.7370, 76.7708),
    (30.7360, 76.7801), (30.7282, 76.7786), (30.7286, 76.7788),
    (30.7287, 76.7879), (30.7298, 76.7848), (30.7244, 76.7858),
    (30.7394, 76.7774), (30.7246, 76.7877), (30.7346, 76.7837),
    (30.7274, 76.7794), (30.7356, 76.7779), (30.7410, 76.7823),
    (30.7382, 76.7802), (30.7382, 76.7780), (30.7349, 76.7766),
    (30.7432, 76.7722), (30.7332, 76.7845), (30.7405, 76.7725),
    (30.7265, 76.7825), (30.7352, 76.7771), (30.7352, 76.7788),
    (30.7256, 76.7871), (30.7283, 76.7805), (30.7255, 76.7787),
    (30.7383, 76.7848), (30.7301, 76.7753),
]

TRANSFORMER_POS = (30.7333, 76.7794)

ANOMALY_REASONS = [
    "sudden spike", "high night usage", "load mismatch",
    "transformer overload", "statistical anomaly", "abnormal peak",
    "meter bypass detected", "meter tampering"
]

SECONDARY_POOL = [
    "abnormal peak", "load mismatch", "transformer overload",
    "high night usage", "sudden spike", "meter irregularity",
    "phase imbalance", "grounding issue"
]

ZONE_NAMES = [
    "Isolated High Risk", "High Risk Cluster A", "High Risk Cluster B",
    "Normal Zone", "Moderate Risk Zone"
]


def rand(lo: float, hi: float, dp: int = 4) -> float:
    """Random float in [lo, hi], rounded to dp decimal places."""
    return round(random.uniform(lo, hi), dp)


def generate_random_data() -> dict:
    """
    Generate a completely randomised theft-detection result.
    Called on every API request to produce fresh data each refresh.
    """
    random.seed()  # true randomness — no fixed seed

    num_houses = len(HOUSE_POSITIONS)
    houses_raw = []

    for i, (lat, lng) in enumerate(HOUSE_POSITIONS):
        house_id = i + 1

        # Slight lat/lng jitter so markers don't stack exactly
        jlat = lat + random.uniform(-0.0005, 0.0005)
        jlng = lng + random.uniform(-0.0005, 0.0005)

        avg_con = rand(5.0, 22.0, 4)
        std_con = rand(0.5, 6.0, 4)
        max_con = round(avg_con + rand(2.0, 12.0, 4), 4)
        night_ratio = rand(0.1, 0.85, 4)
        con_diff = rand(-3.0, 12.0, 4)
        load_share = rand(0.02, 0.45, 4)
        anomaly_score = round(-random.uniform(0.35, 0.80), 6)

        # Risk score: weighted random with some chance of each band
        band = random.choices(
            ["high", "medium", "low"],
            weights=[0.14, 0.14, 0.72]
        )[0]

        if band == "high":
            risk_score = random.randint(65, 100)
            risk_level = "high"
            confidence = random.choice([
                "very high (\u226580%)", "high (65\u201379%)"
            ])
            zone = random.choice(ZONE_NAMES[:3])
            primary_reason = random.choice(ANOMALY_REASONS[:4])
            n_secondary = random.randint(1, 3)
            secondary = random.sample([r for r in SECONDARY_POOL if r != primary_reason], n_secondary)
        elif band == "medium":
            risk_score = random.randint(35, 64)
            risk_level = "medium"
            confidence = "medium (35\u201364%)"
            zone = random.choice(ZONE_NAMES[3:])
            primary_reason = random.choice(ANOMALY_REASONS[2:5])
            n_secondary = random.randint(0, 2)
            secondary = random.sample([r for r in SECONDARY_POOL if r != primary_reason], n_secondary) if n_secondary else []
        else:
            risk_score = random.randint(0, 34)
            risk_level = "low"
            confidence = "low (<35%)"
            zone = "Normal Zone"
            primary_reason = "statistical anomaly"
            secondary = []

        houses_raw.append({
            "house_id": house_id,
            "lat": round(jlat, 6),
            "lng": round(jlng, 6),
            "risk_score": risk_score,
            "risk_level": risk_level,
            "_band": band,  # temp — removed before output
            "reason": {"primary": primary_reason, "secondary": secondary},
            "confidence": confidence,
            "zone": zone,
            "anomaly_score": anomaly_score,
            "average_consumption": avg_con,
            "max_consumption": max_con,
            "std_consumption": std_con,
            "night_usage_ratio": night_ratio,
            "consumption_difference": con_diff,
            "transformer_load_share": load_share,
        })

    # Sort by risk score descending, assign priority ranks
    houses_raw.sort(key=lambda h: h["risk_score"], reverse=True)
    for rank, h in enumerate(houses_raw, start=1):
        h["priority_rank"] = rank
    # Remove temp _band key
    for h in houses_raw:
        h.pop("_band", None)

    # Top 5 insights
    top5 = houses_raw[:5]
    total_high_risk = sum(1 for h in houses_raw if h["risk_level"] == "high")

    # Transformer metrics
    total_consumption = round(sum(h["average_consumption"] for h in houses_raw), 4)
    efficiency = rand(0.85, 0.96, 4)
    expected_load = round(total_consumption * efficiency, 4)
    transformer_loss = round(total_consumption - expected_load + rand(5.0, 60.0, 4), 4)
    loss_pct = round(transformer_loss / max(total_consumption, 1), 4)
    est_loss_rupees = round(transformer_loss * 8.0, 2)  # ₹8 per kWh

    if loss_pct > 0.12:
        zone_status = "Critical"
    elif loss_pct > 0.06:
        zone_status = "Warning"
    else:
        zone_status = "Normal"

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    result = {
        "transformer": {
            "type": "transformer",
            "lat": TRANSFORMER_POS[0],
            "lng": TRANSFORMER_POS[1],
            "loss": transformer_loss,
            "loss_percentage": loss_pct,
            "status": zone_status,
            "estimated_loss_in_rupees": est_loss_rupees,
        },
        "transformer_metrics": {
            "total_house_consumption": total_consumption,
            "expected_transformer_load": expected_load,
            "transformer_loss": transformer_loss,
            "loss_ratio": loss_pct,
            "zone_status": zone_status,
            "estimated_loss_in_rupees": est_loss_rupees,
            "last_updated": now,
        },
        "insights": {
            "top_5_houses": top5,
            "total_high_risk": total_high_risk,
            "zone_status": zone_status,
            "estimated_loss": est_loss_rupees,
        },
        "houses": houses_raw,
        "last_updated": now,
    }

    return result


def save_to_json(data: dict, path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved {path}  ({path.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    output_path = Path(__file__).parent / "theft_detection_results_v4.json"
    data = generate_random_data()
    save_to_json(data, output_path)

    high = data["insights"]["total_high_risk"]
    loss = data["insights"]["estimated_loss"]
    status = data["transformer"]["status"]
    print(f"[OK] Detection complete: {high} high-risk houses | Zone: {status} | Loss: Rs.{loss}")
    print(f"[OK] Top suspect: House #{data['insights']['top_5_houses'][0]['house_id']} "
          f"(score {data['insights']['top_5_houses'][0]['risk_score']}/100)")
