"""
EcoBot – Custom Action Server
MSc AI Assignment: Eco-Travel Advisor using Rasa Platform
Author: Chaithra Jaganath
"""

from __future__ import annotations
import os
import json
import logging
import requests
from typing import Any, Text, Dict, List, Optional
from datetime import datetime

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

logger = logging.getLogger(__name__)

# ─── Static eco-certification database (mocking external API) ────────────────
ECO_CERTIFIED_HOTELS = {
    "Amsterdam": [
        {"name": "The Dylan Amsterdam",          "gstc": True,  "price_per_night": 185, "lat": 52.367, "lon": 4.885},
        {"name": "Hotel V Nesplein",             "gstc": True,  "price_per_night": 120, "lat": 52.370, "lon": 4.894},
        {"name": "Conscious Hotel Westerpark",   "gstc": True,  "price_per_night": 95,  "lat": 52.388, "lon": 4.863},
        {"name": "Hilton Amsterdam",             "gstc": False, "price_per_night": 210, "lat": 52.356, "lon": 4.880},
    ],
    "Lisbon": [
        {"name": "Bairro Alto Hotel",            "gstc": True,  "price_per_night": 160, "lat": 38.712, "lon": -9.143},
        {"name": "Solar dos Mouros",             "gstc": True,  "price_per_night": 130, "lat": 38.713, "lon": -9.134},
        {"name": "Memmo Alfama",                 "gstc": False, "price_per_night": 145, "lat": 38.714, "lon": -9.133},
    ],
    "Copenhagen": [
        {"name": "Radisson Blu Royal Hotel",     "gstc": True,  "price_per_night": 175, "lat": 55.673, "lon": 12.566},
        {"name": "71 Nyhavn Hotel",              "gstc": True,  "price_per_night": 195, "lat": 55.679, "lon": 12.588},
    ],
    "Brussels": [
        {"name": "Hotel Metropole Brussels",     "gstc": True,  "price_per_night": 140, "lat": 50.849, "lon": 4.350},
        {"name": "Pillows Grand Hotel Place Rouppe", "gstc": True, "price_per_night": 165, "lat": 50.844, "lon": 4.346},
    ],
    "default": [
        {"name": "Eco Lodge International",      "gstc": True,  "price_per_night": 89,  "lat": 0.0, "lon": 0.0},
    ]
}

CARBON_OFFSET_PROGRAMS = [
    {"name": "Gold Standard – Cookstove Programme", "url": "https://www.goldstandard.org", "cost_per_tonne": 12.5},
    {"name": "Verra VCS – Reforestation Bolivia",   "url": "https://verra.org",             "cost_per_tonne": 8.0},
    {"name": "South Pole – Wind Energy India",      "url": "https://www.southpole.com",     "cost_per_tonne": 10.0},
]


# ─── Utility: weighted eco-scoring ──────────────────────────────────────────
def eco_score(carbon: float, price: float, eco_cert: bool,
              max_carbon: float = 500.0, max_price: float = 1000.0) -> float:
    """
    Returns a score in [0, 1] where higher = greener & cheaper.
    Weights: carbon 50%, price 30%, eco-certification 20%.
    """
    norm_carbon = min(carbon / max_carbon, 1.0)
    norm_price  = min(price  / max_price,  1.0)
    cert_bonus  = 1.0 if eco_cert else 0.0
    return (0.5 * (1 - norm_carbon)
          + 0.3 * (1 - norm_price)
          + 0.2 * cert_bonus)


def carbon_colour(co2_kg: float) -> str:
    """Return traffic-light colour based on carbon score."""
    if co2_kg < 50:
        return "green"
    elif co2_kg < 200:
        return "amber"
    else:
        return "red"


# ─── ACTION 1: Calculate Carbon Footprint ───────────────────────────────────
class ActionCalculateCarbon(Action):
    """
    Calls the Climatiq API to retrieve real-time carbon-emission data
    for the selected transport mode and route.
    """

    def name(self) -> Text:
        return "action_calculate_carbon"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        destination  = tracker.get_slot("destination")   or "unknown"
        departure    = tracker.get_slot("departure_city") or "unknown"
        mode         = tracker.get_slot("transport_mode") or "plane"
        passengers   = 1

        # Map friendly names to Climatiq activity IDs
        mode_map = {
            "train":    "passenger_transport-type_rail-fuel_source_na-distance_na-vehicle_age_na-passengers_na",
            "rail":     "passenger_transport-type_rail-fuel_source_na-distance_na-vehicle_age_na-passengers_na",
            "eurostar": "passenger_transport-type_rail-fuel_source_na-distance_na-vehicle_age_na-passengers_na",
            "plane":    "passenger_transport-type_plane-fuel_source_na-distance_na-vehicle_age_na-passengers_na",
            "flight":   "passenger_transport-type_plane-fuel_source_na-distance_na-vehicle_age_na-passengers_na",
            "coach":    "passenger_transport-type_coach-fuel_source_na-distance_na-vehicle_age_na-passengers_na",
            "bus":      "passenger_transport-type_coach-fuel_source_na-distance_na-vehicle_age_na-passengers_na",
            "car":      "passenger_transport-type_car-fuel_source_na-distance_na-vehicle_age_na-passengers_na",
        }
        activity_id = mode_map.get(mode.lower(), mode_map["plane"])

        try:
            api_key = os.environ.get("CLIMATIQ_API_KEY", "")
            if not api_key:
                raise ValueError("CLIMATIQ_API_KEY not set")

            response = requests.post(
                "https://api.climatiq.io/data/v1/estimate",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "emission_factor": {"activity_id": activity_id},
                    "parameters": {
                        "passengers": passengers,
                        "origin":      departure,
                        "destination": destination,
                    },
                },
                timeout=2,
            )
            response.raise_for_status()
            data  = response.json()
            co2   = round(data["co2e"], 1)
            unit  = data.get("co2e_unit", "kg")
            colour = carbon_colour(co2)

            # Contextual comparator (approximate: avg petrol car emits ~180g/km)
            km_equivalent = round(co2 / 0.18)

            msg = (
                f"Travelling from **{departure}** to **{destination}** "
                f"by {mode} emits approximately **{co2} {unit} CO₂e** per person. "
                f"That's roughly equivalent to driving {km_equivalent} km in a petrol car. "
            )
            if colour == "red":
                msg += "⚠️ This is a high-emission option — consider train or coach alternatives."
            elif colour == "amber":
                msg += "🟡 Moderate emissions — a reasonable choice if no low-carbon alternative exists."
            else:
                msg += "✅ Great choice — this is a low-emission option!"

            dispatcher.utter_message(text=msg, json_message={"carbon_colour": colour, "co2": co2})

        except requests.exceptions.Timeout:
            logger.warning("Climatiq API timed out for %s → %s via %s", departure, destination, mode)
            dispatcher.utter_message(
                text=(
                    "I couldn't retrieve live carbon data right now (API timeout). "
                    "As a general guide: rail emits ~90% less CO₂ than flying for European journeys."
                )
            )
        except Exception as exc:
            logger.error("Carbon calculation error: %s", exc)
            dispatcher.utter_message(
                text=(
                    "I'm having trouble calculating the carbon footprint right now. "
                    "Rail travel is generally the lowest-emission option for short-to-medium distances."
                )
            )

        return []


# ─── ACTION 2: Fetch Travel Options ─────────────────────────────────────────
class ActionFetchTravelOptions(Action):
    """
    Queries the Amadeus for Developers sandbox API for hotels and flights.
    Falls back to the static JSON database if API is unavailable.
    """

    def name(self) -> Text:
        return "action_fetch_travel_options"

    def _fetch_amadeus_hotels(self, destination: str, budget: Optional[float]) -> List[Dict]:
        """Query Amadeus Hotel Search API with exponential backoff on 429."""
        api_key    = os.environ.get("AMADEUS_API_KEY", "")
        api_secret = os.environ.get("AMADEUS_API_SECRET", "")

        if not (api_key and api_secret):
            return []

        import time
        # Step 1: Get OAuth token
        try:
            token_resp = requests.post(
                "https://test.api.amadeus.com/v1/security/oauth2/token",
                data={
                    "grant_type":    "client_credentials",
                    "client_id":     api_key,
                    "client_secret": api_secret,
                },
                timeout=3,
            )
            token_resp.raise_for_status()
            token = token_resp.json()["access_token"]
        except Exception as exc:
            logger.error("Amadeus token error: %s", exc)
            return []

        # Step 2: Hotel search with retry on 429
        headers = {"Authorization": f"Bearer {token}"}
        for attempt in range(3):
            try:
                resp = requests.get(
                    "https://test.api.amadeus.com/v2/shopping/hotel-offers",
                    headers=headers,
                    params={
                        "cityCode":   destination[:3].upper(),
                        "adults":     1,
                        "currency":   "EUR",
                        "bestRateOnly": True,
                    },
                    timeout=3,
                )
                if resp.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning("Amadeus rate limit hit, retrying in %ss", wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json().get("data", [])
                hotels = []
                for item in data[:5]:
                    price = float(item["offers"][0]["price"]["total"])
                    if budget and price > budget:
                        continue
                    hotels.append({
                        "name":              item["hotel"]["name"],
                        "price_per_night":   price,
                        "gstc":              False,  # Amadeus doesn't surface GSTC; checked against static DB
                    })
                return hotels
            except Exception as exc:
                logger.error("Amadeus hotel error (attempt %d): %s", attempt + 1, exc)
                return []
        return []

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        destination = tracker.get_slot("destination") or "default"
        budget      = tracker.get_slot("budget")

        # Try live Amadeus first, fall back to static DB
        live_hotels = self._fetch_amadeus_hotels(destination, budget)
        static_hotels = ECO_CERTIFIED_HOTELS.get(destination, ECO_CERTIFIED_HOTELS["default"])

        # Merge: if live data found, enrich with GSTC cert from static DB
        if live_hotels:
            static_names = {h["name"]: h for h in static_hotels}
            for h in live_hotels:
                if h["name"] in static_names:
                    h["gstc"] = static_names[h["name"]]["gstc"]
            hotels = live_hotels
        else:
            hotels = static_hotels

        # Filter by budget
        if budget:
            hotels = [h for h in hotels if h["price_per_night"] <= budget]
        if not hotels:
            hotels = static_hotels  # fallback: ignore budget filter

        # Store in slot for rank-and-recommend action
        return [SlotSet("fetched_hotels", json.dumps(hotels[:6]))]


# ─── ACTION 3: Rank and Recommend ───────────────────────────────────────────
class ActionRankAndRecommend(Action):
    """
    Applies the weighted eco-scoring function to produce a ranked list
    and sends a colour-coded carousel payload to the frontend.
    """

    def name(self) -> Text:
        return "action_rank_and_recommend"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        raw = tracker.get_slot("fetched_hotels")
        destination = tracker.get_slot("destination") or "your destination"
        sus_level   = tracker.get_slot("sustainability_level") or "medium"

        # Adjust weight on eco-cert based on sustainability preference
        cert_weight = {"low": 0.05, "medium": 0.20, "high": 0.35}.get(sus_level, 0.20)
        carbon_weight = 1.0 - 0.30 - cert_weight  # remaining to carbon

        hotels = json.loads(raw) if raw else ECO_CERTIFIED_HOTELS.get(destination, ECO_CERTIFIED_HOTELS["default"])

        # Mock carbon per night for accommodation (avg 10–40 kg CO2e per hotel night)
        for h in hotels:
            h["carbon_per_night"] = 15.0 if h.get("gstc") else 35.0

        # Score and sort
        for h in hotels:
            h["score"] = (
                carbon_weight   * (1 - min(h["carbon_per_night"] / 50.0, 1.0))
              + 0.30            * (1 - min(h["price_per_night"]  / 500.0, 1.0))
              + cert_weight     * (1.0 if h.get("gstc") else 0.0)
            )
        hotels.sort(key=lambda x: x["score"], reverse=True)

        # Build response
        if not hotels:
            dispatcher.utter_message(text=f"I couldn't find suitable accommodation in {destination}. Shall I connect you to a travel specialist?")
            return []

        # Text summary
        top = hotels[0]
        colour = "green" if top.get("gstc") else "amber"
        dispatcher.utter_message(
            text=(
                f"🏨 Top pick for {destination}: **{top['name']}** "
                f"at €{top['price_per_night']:.0f}/night. "
                + ("✅ GSTC eco-certified. " if top.get("gstc") else "")
                + f"Eco-score: {top['score']:.2f}/1.00"
            )
        )

        # Carousel payload for Webchat frontend
        carousel_items = []
        for h in hotels[:4]:
            item_colour = "green" if h.get("gstc") else ("amber" if h["price_per_night"] < 200 else "red")
            carousel_items.append({
                "title":    h["name"],
                "subtitle": f"€{h['price_per_night']:.0f}/night | {h['carbon_per_night']:.0f} kg CO₂e/night",
                "colour":   item_colour,
                "gstc":     h.get("gstc", False),
                "score":    round(h["score"], 2),
            })

        dispatcher.utter_message(
            json_message={
                "type":    "carousel",
                "items":   carousel_items,
                "heading": f"Recommended accommodation in {destination}",
            }
        )

        # Suggest carbon offset if high-emission transport was chosen
        transport = tracker.get_slot("transport_mode") or ""
        if transport.lower() in ["plane", "flight"]:
            offset = CARBON_OFFSET_PROGRAMS[0]
            dispatcher.utter_message(
                text=(
                    f"🌱 Since you're flying, consider offsetting your emissions via "
                    f"**{offset['name']}** at ~€{offset['cost_per_tonne']}/tonne CO₂. "
                    f"[Learn more]({offset['url']})"
                )
            )

        return []


# ─── ACTION 4: Human Handover ────────────────────────────────────────────────
class ActionHandoverToHuman(Action):
    """
    Packages full conversation context into a JSON handover payload
    and triggers the handover indicator in the frontend.
    In production this would POST to a CRM webhook.
    """

    def name(self) -> Text:
        return "action_handover_to_human"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        payload = {
            "handover_timestamp": datetime.utcnow().isoformat(),
            "conversation_id":    tracker.sender_id,
            "slots": {
                "destination":         tracker.get_slot("destination"),
                "departure_city":      tracker.get_slot("departure_city"),
                "travel_dates":        tracker.get_slot("travel_dates"),
                "budget":              tracker.get_slot("budget"),
                "sustainability_level":tracker.get_slot("sustainability_level"),
                "transport_mode":      tracker.get_slot("transport_mode"),
            },
            "last_user_message": tracker.latest_message.get("text", ""),
            "conversation_history": [
                {"sender": e.get("event"), "text": e.get("text", "")}
                for e in tracker.events[-20:]
                if e.get("event") in ("user", "bot")
            ],
        }

        # Write to log file (mock CRM webhook)
        log_path = os.environ.get("HANDOVER_LOG_PATH", "handover_log.json")
        try:
            logs = []
            if os.path.exists(log_path):
                with open(log_path) as f:
                    logs = json.load(f)
            logs.append(payload)
            with open(log_path, "w") as f:
                json.dump(logs, f, indent=2)
            logger.info("Handover written to %s", log_path)
        except Exception as exc:
            logger.error("Could not write handover log: %s", exc)

        # In production: POST to CRM webhook
        # webhook_url = os.environ.get("CRM_WEBHOOK_URL")
        # if webhook_url:
        #     requests.post(webhook_url, json=payload, timeout=3)

        dispatcher.utter_message(
            text="Connecting you to a sustainable travel specialist... 🔄 They will have the full context of our conversation.",
            json_message={"type": "handover_indicator", "active": True}
        )

        return [SlotSet("fallback_count", 0)]


# ─── ACTION 5: Reset Fallback Count ─────────────────────────────────────────
class ActionResetFallbackCount(Action):
    def name(self) -> Text:
        return "action_reset_fallback_count"

    def run(self, dispatcher, tracker, domain):
        return [SlotSet("fallback_count", 0)]
