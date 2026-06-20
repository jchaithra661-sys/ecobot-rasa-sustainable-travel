# EcoBot – Eco-Travel Advisor Chatbot (Rasa)

**MSc in Artificial Intelligence | BSBI / UCA | 2026**
**Author:** Chaithra Jaganath

A conversational agent for sustainable tourism planning built on the Rasa Open Source platform.

---

## Quick Start

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd ecobot_rasa
cp .env.example .env
# Edit .env and add your API keys
```

### 2. Get API keys (all free tiers)

| API | Sign-up | Used for |
|-----|---------|----------|
| [Climatiq](https://www.climatiq.io) | Free – 500 calls/month | Carbon emission calculations |
| [Amadeus for Developers](https://developers.amadeus.com) | Free sandbox | Hotel & flight data |
| [OpenCage](https://opencagedata.com) | Free – 2,500 calls/day | GPS geocoding |

### 3. Run with Docker Compose

```bash
docker compose up --build
```

- Rasa server → http://localhost:5005
- Action server → http://localhost:5055 (internal only)
- Frontend → http://localhost:3000

### 4. Train the model

```bash
docker exec ecobot_rasa rasa train
```

---

## Project Structure

```
ecobot_rasa/
├── data/
│   ├── nlu.yml        # Intent training examples
│   ├── stories.yml    # Dialogue stories
│   └── rules.yml      # Deterministic rules
├── actions/
│   └── actions.py     # Custom action server
├── frontend/
│   └── index.html     # Rasa Webchat UI
├── config.yml         # NLU pipeline + policies
├── domain.yml         # Intents, slots, responses
├── endpoints.yml      # Action server URL
├── credentials.yml    # Channel config (REST + SocketIO)
├── docker-compose.yml
├── Dockerfile.actions
├── .env.example
└── README.md
```

---

## Testing

```bash
# NLU accuracy (80/20 split + cross-validation)
docker exec ecobot_rasa rasa test nlu --cross-validation

# Dialogue story accuracy
docker exec ecobot_rasa rasa test core

# Unit tests for custom actions
pip install pytest responses
pytest tests/test_actions.py -v
```

---

## Deploy to HuggingFace Spaces (recommended – zero cost)

1. Create a new Space → select **Docker** SDK
2. Push this repository to the Space's git remote
3. Add secrets in Space Settings: `CLIMATIQ_API_KEY`, `AMADEUS_API_KEY`, `AMADEUS_API_SECRET`
4. HuggingFace builds and serves the containers automatically

---

## Architecture

```
User (Browser)
   ↕ WebSocket (Rasa Webchat)
Rasa Server (port 5005) ── NLU: DIETClassifier pipeline
   ↕ REST
Action Server (port 5055)
   ├── action_calculate_carbon   → Climatiq API
   ├── action_fetch_travel_options → Amadeus API + static JSON DB
   ├── action_rank_and_recommend  → eco-scoring function
   └── action_handover_to_human   → handover_log.json
```

---

## Eco-Scoring Formula

```
Score = 0.5 × (1 − norm_carbon) + 0.3 × (1 − norm_price) + 0.2 × eco_cert_bonus
```

- Higher score = greener and more affordable option
- Weights adjust based on user's `sustainability_level` slot

---

## Ethical Notes

- Carbon estimates sourced from Climatiq; approximate nature is always disclosed
- Eco-certifications sourced only from GSTC and EU Ecolabel (independently verified)
- No personal data stored beyond the session (GDPR compliant)
- API keys never committed to version control
