# 🌊 Flood Intelligence Platform (FIP)

### AI-Powered Urban Flood Intelligence, Monitoring & Response for Mumbai

**Predict · Analyse · Verify · Respond**

Flood Intelligence Platform (FIP) is a geospatial intelligence platform designed to support urban flood monitoring and emergency response across Mumbai. It combines weather observations, rainfall datasets, geographic information, ward-level risk analysis, citizen-generated reports, social intelligence and computer vision to provide localized flood intelligence.

The platform aims to help citizens and authorities understand flood conditions, identify vulnerable locations and coordinate faster responses.

---

## 🚀 Project Overview

Urban flooding in Mumbai is influenced by multiple interacting factors:

- Heavy and localized monsoon rainfall
- Low-lying terrain and elevation differences
- Drainage infrastructure limitations
- Coastal influence and tidal conditions
- River overflow and water accumulation
- Historical waterlogging hotspots
- Delayed ground-level incident reporting

Traditional weather monitoring alone cannot explain where water will accumulate or which locations require immediate attention.

FIP addresses this challenge through a unified geospatial platform that brings environmental, spatial and citizen-generated information together.

**Core workflow:**

`DATA COLLECTION → PROCESSING → INTELLIGENCE → RISK ASSESSMENT → ALERTS → RESPONSE`

---

## ✨ Key Features

### 1. Geospatial Flood Intelligence Dashboard

- Interactive Mumbai map interface.
- Ward-level flood intelligence.
- Geospatial visualization of flood-related information.
- Location-based monitoring and analysis.
- Operational dashboard for flood situational awareness.

### 2. Weather & Rainfall Intelligence

- Weather data ingestion pipeline.
- Current weather and forecast integration.
- Maharashtra Surface Water Department rainfall datasets.
- Daily and hourly rainfall processing.
- Rainfall quality-control and anomaly flagging.
- Station-level rainfall analysis.
- Spatial rainfall station coverage analysis against Mumbai's municipal wards.

### 3. Citizen Flood Reporting

The citizen reporting module supports:

- GPS-based incident reporting.
- Automatic ward identification using PostGIS.
- Water-depth classification:
  - Ankle
  - Knee
  - Waist
  - Submerged
- Optional image uploads.
- Computer-vision-based image analysis.
- Spatial-temporal duplicate detection.
- Report retrieval and verification summaries.

### 4. Computer Vision Intelligence

- Flood image analysis.
- YOLO-based object detection integration.
- Water-depth estimation.
- Confidence-based verification.
- Image inference testing.

### 5. Ward-Level Risk Intelligence

- Ward-based spatial analysis.
- Risk score management.
- Integration of environmental and geospatial inputs.
- Machine-learning integration architecture.

### 6. Social Intelligence

- Social signal collection and processing architecture.
- NLP-based classification integration.
- Additional situational awareness from public signals.

### 7. Alerts & Emergency Response

- Flood alert management.
- Alert generation architecture.
- Integration architecture for notification providers.
- Emergency-response information management.

---

## 🏗️ System Architecture

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
    PostgreSQL    ML / CV       Spatial Analysis
     + PostGIS    Engines        and Processing
       |              |              |
       +--------------+--------------+
                      |
             FLOOD INTELLIGENCE
                      |
       +--------------+--------------+
       |              |              |
    Risk Scores   Citizen Reports   Alerts
       |              |              |
       +--------------+--------------+
                      |
             NEXT.JS DASHBOARD
                      |
          GEOSPATIAL VISUALIZATION
```

---

## 🛠️ Technology Stack

| Layer | Technologies |
|---|---|
| Frontend | Next.js 14, React 18, TypeScript |
| Styling | Tailwind CSS |
| Mapping | Mapbox GL, Deck.gl |
| Backend | Python, FastAPI |
| API Server | Uvicorn |
| ORM | SQLAlchemy 2.0 |
| Database | PostgreSQL |
| Geospatial Database | PostGIS |
| Geospatial Processing | GeoPandas, Shapely, PyProj |
| Machine Learning | Python ML stack, XGBoost integration |
| Computer Vision | OpenCV, YOLO |
| NLP | Transformer-based architecture |
| Cache | Redis |
| Background Processing | Celery |
| AI Integration | Gemini API |
| Version Control | Git, GitHub |

---

## 📊 Rainfall Data Pipeline

A dedicated rainfall processing pipeline has been developed using Maharashtra Surface Water Department datasets.

### Data Sources

| Dataset | Temporal Resolution |
|---|---|
| Maharashtra Daily Rainfall | Daily |
| Maharashtra Telemetry Rainfall | Hourly |

### Processing Workflow

```text
Raw Maharashtra Rainfall CSVs
             |
             v
      Data Cleaning
             |
             v
    Spatial Station Analysis
             |
             v
      Mumbai Region
        Extraction
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

### Current Dataset Statistics

| Metric | Daily | Hourly |
|---|---:|---:|
| Records after QC | 15,895 | 66,139 |
| Unique stations | 62 | 23 |
| Duplicate records removed | 0 | 160 |

The unified dataset currently contains **82,034 observations** across 70 unique stations.

Quality flags are retained for extreme rainfall observations and suspicious station events.

> Note: These are processed regional observations, not direct measurements inside every Mumbai municipal ward. Hourly telemetry anomalies and source-level rainfall semantics remain under investigation. The dataset is not yet a validated flood-prediction training dataset.

---

## 📁 Project Structure

```text
flood-intelligence/
│
├── backend/
│   ├── api/
│   │   └── routes/
│   │       ├── alerts.py
│   │       ├── reports.py
│   │       ├── routing.py
│   │       ├── signals.py
│   │       ├── social.py
│   │       ├── wards.py
│   │       └── weather.py
│   │
│   ├── models/
│   │   ├── report.py
│   │   ├── ward.py
│   │   ├── weather.py
│   │   ├── risk.py
│   │   └── alert.py
│   │
│   ├── schemas/
│   ├── pipeline/
│   ├── ml/
│   │   ├── engine_a/
│   │   ├── engine_b/
│   │   └── engine_c/
│   │
│   ├── data/
│   │   ├── raw/
│   │   ├── processed/
│   │   ├── metadata/
│   │   ├── clean_rainfall_datasets.py
│   │   ├── analyze_station_coverage.py
│   │   ├── validate_rainfall.py
│   │   ├── validate_unified_rainfall.py
│   │   ├── investigate_rainfall_anomalies.py
│   │   ├── clean_hourly_rainfall.py
│   │   ├── clean_daily_rainfall.py
│   │   └── build_unified_rainfall.py
│   │
│   ├── migrations/
│   ├── tests/
│   ├── config.py
│   ├── main.py
│   └── requirements.txt
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   ├── public/
│   ├── types/
│   └── package.json
│
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## ⚙️ Local Development Setup

### Prerequisites

- Python 3.10+
- Node.js 20+
- npm
- PostgreSQL with PostGIS
- Redis
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/harshhdubeyy/flood-intelligence.git

cd flood-intelligence
```

### 2. Backend Setup

Create and activate a virtual environment:

```bash
python3 -m venv backend/venv

source backend/venv/bin/activate
```

Install dependencies:

```bash
pip install -r backend/requirements.txt
```

Configure your environment variables in the backend environment file.

Start the FastAPI server:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Backend API:

`http://localhost:8000`

Interactive API documentation:

`http://localhost:8000/docs`

### 3. Frontend Setup

Open another terminal:

```bash
cd frontend

npm install
```

Create the frontend environment file:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
NEXT_PUBLIC_MAPBOX_TOKEN=your_mapbox_public_token
```

Start the Next.js development server:

```bash
npm run dev
```

Frontend:

`http://localhost:3000`

### 4. Database

Configure PostgreSQL and PostGIS, then set the appropriate database connection string in your backend environment configuration.

Ensure the required database migrations have been applied before starting the application.

---

## 🔐 Environment Variables

Do not commit credentials or API keys.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL database connection |
| `REDIS_URL` | Redis connection |
| `NEXT_PUBLIC_API_URL` | Backend API base URL |
| `NEXT_PUBLIC_MAPBOX_TOKEN` | Mapbox public access token |
| `GEMINI_API_KEY` | Gemini integration |
| `OPENWEATHER_API_KEY` | OpenWeatherMap integration |

Additional provider credentials may be required depending on the integrations enabled.

---

## 🗺️ Development Roadmap

| Module | Development Status |
|---|---|
| Next.js flood intelligence dashboard | Implemented |
| FastAPI backend architecture | Implemented |
| PostgreSQL / PostGIS integration | Implemented |
| Weather ingestion pipeline | Implemented, under refinement |
| Rainfall data cleaning | Implemented |
| Rainfall spatial coverage analysis | Implemented |
| Rainfall quality-control pipeline | Implemented |
| Unified rainfall dataset | Implemented |
| Citizen flood reporting | Existing implementation; enhancements planned |
| Computer vision integration | Implemented prototype |
| Ward-level risk intelligence | Under development |
| Social intelligence | Integration architecture |
| Tide and sea-level intelligence | Planned |
| Elevation and terrain intelligence | Planned |
| Drainage infrastructure intelligence | Planned |
| Historical flood intelligence | Planned |
| Advanced flood prediction | Planned |
| Emergency response optimization | Planned |

---

## ⚠️ Current Limitations

FIP is an actively developed prototype.

- Rainfall station coverage is geographically uneven.
- Rainfall observations are not available directly inside every municipal ward.
- Hourly telemetry contains readings requiring further source-level verification.
- Historical zero-rainfall observations are not established in the current datasets.
- Terrain, drainage and tide datasets are still being integrated.
- Operational flood predictions require further data validation, model development and testing.
- Citizen reports and computer-vision outputs require appropriate verification before operational use.

The platform should not be treated as an official emergency warning service.

---

## 👨‍💻 Development

Contributions and improvements are welcome.

For development:

1. Fork the repository.
2. Create a feature branch.
3. Implement and test your changes.
4. Submit a pull request.

---

**Flood Intelligence Platform (FIP)**

*Building localized intelligence for a more flood-resilient Mumbai.*

