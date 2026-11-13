# 🌊 Flood Intelligence Platform (FIP)

### AI-Powered Urban Flood Intelligence, Monitoring & Response for Mumbai

**Predict · Analyse · Verify · Respond**

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-Frontend-3178C6?logo=typescript)](https://www.typescriptlang.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-4169E1?logo=postgresql)](https://www.postgresql.org/)
[![PostGIS](https://img.shields.io/badge/PostGIS-Geospatial-336791)](https://postgis.net/)
[![Redis](https://img.shields.io/badge/Redis-Queue%20%26%20Cache-DC382D?logo=redis)](https://redis.io/)

---

## Overview

Flood Intelligence Platform (FIP) is a geospatial intelligence and flood-monitoring platform designed to improve urban flood situational awareness and emergency response across Mumbai.

Mumbai experiences recurring urban flooding due to intense monsoon rainfall, low-lying terrain, drainage limitations, tidal influence, and localized water accumulation. Traditional weather monitoring alone cannot provide sufficient ground-level visibility into these conditions.

FIP combines weather intelligence, rainfall observations, geospatial analysis, citizen-generated reports, computer vision, multilingual NLP, and ward-level risk assessment into a unified platform.

It is designed to help citizens and operators:

- Monitor flood-related conditions across Mumbai.
- Identify potentially vulnerable municipal wards.
- Submit and review ground-level flood reports.
- Analyse flood-related images and textual descriptions.
- Understand ward-level risk and predictive outlooks.
- Manage geographically targeted emergency notifications.

**The objective is to move from isolated flood observations to a unified, location-aware intelligence and response system.**

---

## Core Capabilities

### 1. Geospatial Flood Intelligence Dashboard

- Interactive Mumbai map powered by Mapbox GL and Deck.gl.
- Ward-level flood intelligence across Mumbai's municipal wards.
- Visualization of citizen reports and identified hotspots.
- Spatial filtering and location-based analysis.
- Flood-risk and predictive-outlook visualization.
- Operational command-center interface.

### 2. Weather & Rainfall Intelligence

- Automated weather ingestion pipeline.
- Current weather and forecast integration.
- Daily and hourly rainfall data processing.
- Maharashtra Surface Water Department rainfall datasets.
- Rainfall quality-control and anomaly flagging.
- Weather freshness and provenance tracking.
- Background processing through Celery and Redis.

### 3. Citizen Flood Reporting

Citizens can submit ground-level flood observations through the reporting workflow.

Features include:

- GPS-based incident submission.
- Automatic municipal ward identification using PostGIS.
- Water-depth classification:
  - Ankle
  - Knee
  - Waist
  - Submerged
- Optional image uploads.
- Citizen-reported water-depth preservation.
- Duplicate report detection using spatial and temporal proximity.
- Operator review and verification workflow.
- Report summaries and ward-level intelligence.

### 4. Computer Vision Flood Analysis

The computer vision pipeline analyses submitted flood-related images.

Capabilities include:

- YOLO-based object detection integration.
- Flood image analysis.
- Visual water-depth estimation.
- Confidence-based inference.
- Separate storage of CV-estimated depth.
- Evidence-based operator review.

CV estimates remain distinct from citizen-reported observations and are not treated as official ground truth.

### 5. Ward-Level Flood Risk Intelligence

The platform combines available environmental and geospatial signals to calculate ward-level risk assessments.

Features include:

- Ward-level risk scoring.
- Weather and rainfall feature integration.
- Freshness-aware environmental inputs.
- Risk computation through background tasks.
- Persisted ward risk snapshots.
- Missing-data handling and provenance tracking.

The current risk engine uses a calibrated hydrological heuristic. It should not be represented as a fully trained or validated flood-prediction model.

### 6. Predictive Flood Outlook

The predictive outlook provides scenario-based ward-level assessments across multiple future horizons.

Supported horizons:

- 1 hour
- 3 hours
- 6 hours
- 12 hours
- 24 hours

Features include:

- Ward-level predictive features.
- Weather forecast integration.
- Scenario-based risk indicators.
- Forecast freshness tracking.
- Missing-input handling.
- Explicit separation between heuristic outlooks and validated probabilities.

### 7. Multilingual NLP Flood Intelligence

The platform integrates NLP processing into citizen reports and social-post processing.

Supported languages:

- English
- Hindi
- Marathi

Capabilities include:

- Flood-related and waterlogging classification.
- Text-based water-depth extraction.
- Emergency and distress signal detection.
- Language identification.
- Spam and unrelated-content detection.
- Mumbai locality and landmark extraction.
- Ward mapping using a spatial gazetteer.
- NLP provenance and confidence tracking.
- Reprocessing of previously analysed records.

The current NLP engines use heuristic lexical classification, multilingual phrase matching, and gazetteer-based entity extraction. They are not presented as trained transformer models.

NLP outputs are advisory signals. They cannot independently verify an incident or establish official flood confirmation.

### 8. Social Intelligence

The social intelligence module provides an architecture for processing flood-related public signals.

Features include:

- Reddit and X provider adapters.
- Configurable locality and keyword matching.
- Social-post classification.
- Mumbai locality extraction.
- Ward association for sufficiently confident matches.
- Derived NLP artifact persistence.
- Data lifecycle and retention controls.
- Operator-facing social intelligence APIs.

**Live social collection is disabled by default.** Provider permissions, policy approval, credentials, and applicable retention requirements must be satisfied before enabling collection.

### 9. Citizen Notifications & Geographic Alerting

The notification infrastructure supports location-aware flood alert management.

Implemented capabilities include:

- Citizen notification subscriptions.
- Explicit location and notification consent.
- Web Push provider integration.
- Configurable geographic targeting with a default 5 km radius.
- PostGIS-based recipient selection.
- Alert approval and lifecycle management.
- Delivery tracking and audit records.
- Retry and idempotency controls.
- CAP v1.2 alert generation.
- Notification opt-out and subscription management.

Public notification dispatch is disabled by default through:

`ALERT_DISPATCH_ENABLED=false`

Provider configuration and operational approval are required before real public delivery.

### 10. Operator Verification & Evidence Management

The operator workflow supports structured review of incoming flood reports.

Features include:

- Protected operator access.
- Report triage and verification.
- Confirmation and rejection workflows.
- Review history and audit logging.
- Evidence storage integration.
- Coordinate and timestamp corrections.
- Separation of operator verification from AI-generated assessments.

Operator confirmation does not automatically represent official BMC confirmation.

---

## System Architecture

```text
                 DATA SOURCES
                      |
       +--------------+--------------+
       |              |              |
    Weather        Rainfall       GIS / Ward
    Forecasts      Stations        Boundaries
       |              |              |
       +--------------+--------------+
                      |
               DATA INGESTION
                      |
              DATA PROCESSING
                      |
               FASTAPI BACKEND
                      |
       +--------------+--------------+
       |              |              |
   PostgreSQL      Redis          PostGIS
   + PostGIS       Celery         Spatial Queries
       |              |              |
       +--------------+--------------+
                      |
             INTELLIGENCE ENGINES
                      |
       +--------------+--------------+
       |              |              |
   Risk Engine    Computer Vision    NLP
       |              |              |
       +--------------+--------------+
                      |
              FLOOD INTELLIGENCE
                      |
       +--------------+--------------+
       |              |              |
   Ward Risk     Citizen Reports   Alerts
   & Outlook     & Verification    & CAP
       |              |              |
       +--------------+--------------+
                      |
              APPLICATION LAYER
                      |
           +----------+----------+
           |                     |
      NEXT.JS WEB            ANDROID
      DASHBOARD              SCAFFOLD
```

---

## Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | Next.js 15, React 18, TypeScript |
| Styling | Tailwind CSS |
| Mapping | Mapbox GL, Deck.gl |
| Data Visualization | Recharts |
| Backend | Python, FastAPI |
| API Server | Uvicorn |
| ORM | SQLAlchemy 2.0 |
| Database | PostgreSQL |
| Geospatial Database | PostGIS, GeoAlchemy2 |
| Spatial Processing | GeoPandas, Shapely, PyProj |
| Background Tasks | Celery |
| Cache & Broker | Redis |
| Machine Learning | scikit-learn, XGBoost integration |
| Computer Vision | YOLO, OpenCV |
| NLP | Custom multilingual heuristic NLP pipelines |
| AI Integration | Google Gemini API |
| Evidence Storage | AWS S3 |
| Android Project | Kotlin, Jetpack Compose |
| Build System | Gradle |
| Containerization | Docker, Docker Compose |
| Version Control | Git, GitHub |

---

## Rainfall Data Pipeline

The rainfall processing pipeline uses regional datasets from the Maharashtra Surface Water Department.

### Source datasets

| Dataset | Resolution |
|---|---|
| Maharashtra Daily Rainfall | Daily |
| Maharashtra Telemetry Rainfall | Hourly |

### Processing workflow

```text
Raw Rainfall CSV Files
          |
          v
    Data Cleaning
          |
          v
  Spatial Station Analysis
          |
          v
   Mumbai Region Extraction
          |
          v
    Data Validation
          |
          v
   Anomaly Detection
          |
          v
     Quality Control
          |
          v
  Unified Rainfall Dataset
```

### Processed dataset statistics

| Metric | Value |
|---|---:|
| Unified rainfall observations | 82,034 |
| Unique stations | 70 |
| Daily observations | 15,895 |
| Hourly observations | 66,139 |
| Daily stations | 62 |
| Hourly stations | 23 |

**Data limitations:** These are regional observations, not direct measurements within every BMC ward. Station coverage is uneven, and rainfall anomalies require appropriate source-level validation. Missing observations must not be interpreted as zero rainfall.

---

## Project Structure

```text
flood-intelligence/
│
├── backend/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── alerts.py
│   │   │   ├── intelligence.py
│   │   │   ├── predictions.py
│   │   │   ├── reports.py
│   │   │   ├── social.py
│   │   │   ├── wards.py
│   │   │   └── weather.py
│   │   │
│   │   └── websocket.py
│   │
│   ├── models/
│   ├── schemas/
│   ├── services/
│   │   ├── evidence_storage.py
│   │   ├── predictive_features.py
│   │   └── report_intelligence.py
│   │
│   ├── pipeline/
│   │   ├── alert_dispatcher.py
│   │   ├── cap_builder.py
│   │   └── social_collection.py
│   │
│   ├── ml/
│   │   ├── engine_a/
│   │   ├── engine_b/
│   │   └── engine_c/
│   │
│   ├── tasks/
│   ├── migrations/
│   ├── tests/
│   ├── data/
│   ├── config.py
│   ├── main.py
│   └── requirements.txt
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── public/
│   │   └── data/
│   │       └── mumbai-wards.geojson
│   └── package.json
│
├── app/
│   └── src/
│       └── main/
│           ├── AndroidManifest.xml
│           └── java/
│
├── docker-compose.yml
├── metadata.json
├── .gitignore
└── README.md
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 20+
- npm
- PostgreSQL with PostGIS
- Redis
- Docker and Docker Compose (recommended)
- Git

### 1. Clone the repository

```bash
git clone https://github.com/harshhdubeyy/flood-intelligence.git

cd flood-intelligence
```

### 2. Configure environment variables

Create a backend `.env` file and configure the required database, Redis, provider, and security settings.

Example development configuration:

```env
ENVIRONMENT=development
DEBUG=true

DATABASE_URL=postgresql+asyncpg://fip_user:fip_password@localhost:5432/fip_db
DATABASE_SYNC_URL=postgresql://fip_user:fip_password@localhost:5432/fip_db

REDIS_URL=redis://localhost:6379/0

JWT_SECRET_KEY=replace_with_a_secure_secret
FLOOD_OPERATOR_TOKENS=

GEMINI_API_KEY=
OPENWEATHERMAP_API_KEY=
OPENTOPOGRAPHY_API_KEY=

AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-south-1

VERIFICATION_EVIDENCE_STORAGE=local
VERIFICATION_EVIDENCE_S3_BUCKET=

SOCIAL_COLLECTION_ENABLED=false
SOCIAL_LIFECYCLE_ENABLED=false
SOCIAL_REDDIT_POLICY_APPROVED=false
SOCIAL_X_POLICY_APPROVED=false

ALERT_DISPATCH_ENABLED=false
ALERT_DEFAULT_RADIUS_KM=5.0

VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=
```

Use secure, unique production secrets. Never commit `.env` files, access tokens, passwords, or private keys.

### 3. Start infrastructure

```bash
docker compose up -d postgres redis
```

Ensure PostgreSQL and Redis are healthy before starting the application.

### 4. Backend setup

Create a virtual environment:

```bash
python3 -m venv backend/venv

source backend/venv/bin/activate
```

Install dependencies:

```bash
pip install -r backend/requirements.txt
```

Start the backend from the repository root:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend:

`http://localhost:8000`

API documentation:

`http://localhost:8000/docs`

Health endpoint:

`http://localhost:8000/health`

### 5. Frontend setup

Open another terminal:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
NEXT_PUBLIC_MAPBOX_TOKEN=your_mapbox_public_token
```

Start the frontend:

```bash
npm run dev
```

Frontend:

`http://localhost:3000`

---

## Database Migrations

Database schema changes are maintained using Alembic.

Migration files are located in:

```text
backend/migrations/versions/
```

Apply migrations using the project's configured Alembic environment:

```bash
alembic -c backend/migrations/alembic.ini upgrade head
```

Review migration configuration and database connectivity before applying migrations to a production database.

---

## Testing

Backend tests:

```bash
PYTHONPATH=. backend/venv/bin/pytest backend/tests/
```

Frontend TypeScript validation:

```bash
cd frontend
npx tsc --noEmit
```

Frontend production build:

```bash
npm run build
```

The project includes tests for report processing, computer vision, NLP integration, predictive features, risk computation, social data lifecycle, weather scheduling, evidence storage, and notification workflows.

---

## Configuration & Operational Safety

FIP includes integrations that require external credentials, provider permissions, or operational approval.

Important default safeguards:

| Capability | Default |
|---|---|
| Social collection | Disabled |
| Social lifecycle processing | Disabled |
| Social provider policy approval | Disabled |
| Public alert dispatch | Disabled |
| Default alert radius | 5 km |
| Evidence storage | Local unless configured |

Real notification delivery requires configured provider credentials and explicit operational approval.

Social collection requires appropriate provider permissions and policy compliance.

AI-generated assessments, NLP classifications, citizen reports, and heuristic risk scores must not be treated as official BMC confirmation.

---

## Development Status

| Module | Status |
|---|---|
| FastAPI backend | Implemented |
| Next.js geospatial dashboard | Implemented |
| PostgreSQL and PostGIS integration | Implemented |
| Rainfall processing pipeline | Implemented |
| Weather ingestion automation | Implemented |
| Citizen flood reporting | Implemented |
| Computer vision integration | Implemented |
| Duplicate report detection | Implemented |
| Operator verification workflow | Implemented |
| Evidence storage integration | Implemented |
| Ward-level risk intelligence | Implemented using a heuristic engine |
| Predictive flood outlook | Implemented using scenario-based heuristics |
| Multilingual NLP integration | Implemented using heuristic pipelines |
| Social intelligence processing | Implemented; live collection gated |
| Historical flood event acquisition | Source and verification pipeline; licensed data pending |
| Citizen notification infrastructure | Implemented; public dispatch gated |
| Android application | Initial scaffold; application features pending |

Implementation status does not imply that every external provider is authorized, configured, or operating in production.

---

## Current Limitations

FIP is an actively developed urban flood intelligence prototype.

- Rainfall station coverage is geographically uneven.
- Rainfall data is not available directly inside every municipal ward.
- Historical verified flood-event labels are not yet sufficient for defensible supervised flood prediction.
- Current ward risk assessments use a calibrated heuristic rather than a validated trained model.
- Predictive outlooks are scenario-based and should not be interpreted as calibrated probabilities.
- NLP outputs are heuristic advisory signals, not authoritative incident verification.
- Social collection depends on provider permissions and policy approval.
- Real public notification delivery remains gated by configuration, provider setup, and operational approval.
- Citizen reports and computer-vision outputs require appropriate operator review.

**FIP is not an official emergency warning service and must not replace instructions from authorized disaster-management authorities.**

---

## Contributing

Contributions, suggestions, and improvements are welcome.

1. Fork the repository.
2. Create a feature branch.
3. Implement your changes.
4. Add or update tests.
5. Verify the backend and frontend.
6. Submit a pull request.

---

## License

A license should be added to the repository before others redistribute or reuse the project. Until then, no open-source license is specified.

---

## Project

**Flood Intelligence Platform (FIP)**

*Building localized intelligence for a more flood-resilient Mumbai.*

Repository: https://github.com/harshhdubeyy/flood-intelligence
