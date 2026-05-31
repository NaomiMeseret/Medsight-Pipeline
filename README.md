# 🩺 Medsight-Pipeline

Medsight-Pipeline is an AI-powered data pipeline that turns medical Telegram marketplace posts and images into structured business insights.

The project scrapes Telegram channels, stores raw posts and images, loads them into PostgreSQL, transforms the data with dbt, analyzes images with YOLO, orchestrates the workflow with Dagster, and exposes reports through a FastAPI API.

## 💡 Project Idea

Medical, pharmacy, and cosmetics businesses often post products on Telegram. This project collects those posts and creates reports such as:

- Top mentioned products or terms
- Channel posting activity
- Searchable Telegram messages
- Image usage by channel
- Visual content categories from YOLO detection

In short:

```text
Telegram posts and images -> Data warehouse -> AI image analysis -> Business reports
```

## 📡 Telegram Channels

The project is configured to scrape these Telegram marketplace channels:

- `CheMed123`
- `lobelia4cosmetics`
- `tikvahpharma`

You can change the channel list in `.env`:

```env
TELEGRAM_CHANNELS=CheMed123,lobelia4cosmetics,tikvahpharma
```

## 🛠️ Tech Stack

- Python 3.11
- Telethon for Telegram scraping
- PostgreSQL for the warehouse database
- dbt for data modeling and tests
- YOLOv8 for image detection
- FastAPI for report endpoints
- Dagster for pipeline orchestration
- Docker Compose for local PostgreSQL

## 🔄 Pipeline Flow

```text
Telegram channels
    -> Scrape messages and images
    -> Save raw JSON and image files
    -> Load raw data into PostgreSQL
    -> Build dbt staging and marts models
    -> Run YOLO image detection
    -> Load image detections into PostgreSQL
    -> Serve analytics through FastAPI
```

## 📁 Project Structure

```text
api/                    FastAPI application
data/                   Raw and processed local data
medical_warehouse/      dbt project
scripts/                Database loading utilities
src/                    Telegram scraper and YOLO detection
pipeline.py             Dagster pipeline
docker-compose.yml      Local PostgreSQL service
requirements.txt        Python dependencies
```

## ⚙️ Setup

Create and activate a virtual environment:

```zsh
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
TELEGRAM_API_ID=
TELEGRAM_API_HASH=
TELEGRAM_PHONE=
TELEGRAM_CHANNELS=CheMed123,lobelia4cosmetics,tikvahpharma

POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=medical_warehouse
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
```

Get Telegram API credentials from:

```text
https://my.telegram.org/apps
```

## 🚀 Run Locally

Start PostgreSQL:

```zsh
docker compose up -d postgres
```

Run the scraper once to authenticate Telegram and collect data:

```zsh
python src/scraper.py
```

If Telegram sends a login code, enter it in the terminal. A `telegram_scraper.session` file will be created after successful login.

Load data and build the warehouse:

```zsh
python scripts/load_to_postgres.py
python src/yolo_detect.py
python scripts/load_yolo_results.py

cd medical_warehouse
DBT_PROFILES_DIR=. POSTGRES_PASSWORD=postgres ../.venv/bin/dbt run
DBT_PROFILES_DIR=. POSTGRES_PASSWORD=postgres ../.venv/bin/dbt test
cd ..
```

Start the API:

```zsh
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open the API docs:

```text
http://127.0.0.1:8000/docs
```

## 🧭 Run with Dagster

Start Dagster:

```zsh
dagster dev -f pipeline.py -h 127.0.0.1 -p 3000
```

Open:

```text
http://127.0.0.1:3000
```

Dagster runs the full workflow:

```text
scrape_telegram_data
load_raw_to_postgres
run_dbt_transformations
run_yolo_enrichment
load_yolo_results
```

## 🌐 API Endpoints

```text
GET /
GET /api/reports/top-products
GET /api/channels/{channel_name}/activity
GET /api/search/messages
GET /api/reports/visual-content
```

Example requests:

```text
http://127.0.0.1:8000/api/reports/top-products?limit=10
http://127.0.0.1:8000/api/search/messages?query=cream&limit=10
http://127.0.0.1:8000/api/channels/lobelia4cosmetics/activity
http://127.0.0.1:8000/api/reports/visual-content
```

## 📸 Screenshots

FastAPI documentation:

![FastAPI API Documentation](screenshots/task4/api_docs.png)

Top products report:

![Top Products Endpoint](screenshots/task4/top_products.png)

Visual content report:

![Visual Content Analysis](screenshots/task4/visual_content.png)

Dagster pipeline graph:

![Dagster Pipeline Graph](screenshots/task5/pipeline_graph.png)

## 🧱 Data Models

The dbt project builds:

- `staging.stg_telegram_messages`
- `marts.dim_channels`
- `marts.dim_dates`
- `marts.fct_messages`
- `marts.fct_image_detections`

## ✅ Recent Updates

- Added Docker Compose support for local PostgreSQL.
- Added Dagster webserver dependency for `dagster dev`.
- Fixed dependency compatibility for YOLO/OpenCV by constraining NumPy.
- Added dbt schema naming macro so models build into `staging` and `marts`.
- Added the YOLO image detections mart model.
- Added the raw YOLO detections source definition.
- Updated the scraper so Telegram authentication failures return an error instead of silently passing.
- Updated the pipeline to use the active virtual environment Python and dbt executables.

## 📝 Notes

- Do not commit `.env`, `.venv`, `telegram_scraper.session`, dbt `target/`, logs, or generated cache files.
- The first Telegram scrape may require a login code.
- YOLO can take several minutes when many images are present.
- The API depends on PostgreSQL and dbt models being built first.
