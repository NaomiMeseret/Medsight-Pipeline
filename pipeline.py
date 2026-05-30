"""
Dagster pipeline for Medical Telegram Warehouse ELT pipeline.

This pipeline orchestrates the entire data workflow:
1. Scrape Telegram data 
2. Load raw data to PostgreSQL 
3. Run dbt transformations 
4. Run YOLO enrichment 
5. Load YOLO results to PostgreSQL 
"""

import os
import subprocess
import logging
import sys
from pathlib import Path
from typing import Optional

from dagster import (
    job,
    op,
    get_dagster_logger,
    RetryPolicy,
    Config,
    In,
    Out,
    Output,
    AssetMaterialization,
    MetadataValue
)

logger = get_dagster_logger()

# Base directory for the project
BASE_DIR = Path(__file__).parent
PYTHON_EXECUTABLE = sys.executable
DBT_EXECUTABLE = str(Path(PYTHON_EXECUTABLE).with_name("dbt"))


class ScrapeConfig(Config):
    """Configuration for scraping operation."""
    channels: Optional[str] = None  # Comma-separated channel list, None uses .env default


@op(
    retry_policy=RetryPolicy(max_retries=2),
    description="Scrape messages and images from Telegram channels"
)
def scrape_telegram_data(context, config: ScrapeConfig) -> str:
    """
    Op 1: Scrape Telegram Data
    
    Runs the Telegram scraper to download messages and images.
    """
    logger.info("Starting Telegram scraping...")
    
    try:
        scraper_path = BASE_DIR / "src" / "scraper.py"
        
        # Run scraper
        result = subprocess.run(
            [PYTHON_EXECUTABLE, str(scraper_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=True
        )
        
        logger.info(f"Scraping completed successfully")
        logger.info(f"Output: {result.stdout[-500:]}")  # Last 500 chars
        
        context.log_event(
            AssetMaterialization(
                asset_key="telegram_data",
                description="Raw Telegram messages and images downloaded",
                metadata={
                    "scraper_output": MetadataValue.text(result.stdout[-500:]),
                    "status": MetadataValue.text("success")
                }
            )
        )
        
        return "scraping_success"
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Scraping failed: {e}")
        logger.error(f"Error output: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during scraping: {e}")
        raise


@op(
    retry_policy=RetryPolicy(max_retries=2),
    description="Load raw JSON data into PostgreSQL"
)
def load_raw_to_postgres(context, scrape_result: str) -> str:
    """
    Op 2: Load Raw Data to PostgreSQL
    
    Loads JSON files from data lake into raw.telegram_messages table.
    """
    logger.info("Loading raw data to PostgreSQL...")
    
    try:
        loader_path = BASE_DIR / "scripts" / "load_to_postgres.py"
        
        result = subprocess.run(
            [PYTHON_EXECUTABLE, str(loader_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=True
        )
        
        logger.info(f"Data loading completed successfully")
        logger.info(f"Output: {result.stdout[-500:]}")
        
        context.log_event(
            AssetMaterialization(
                asset_key="raw_postgres_data",
                description="Raw data loaded into PostgreSQL",
                metadata={
                    "loader_output": MetadataValue.text(result.stdout[-500:]),
                    "status": MetadataValue.text("success")
                }
            )
        )
        
        return "loading_success"
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Data loading failed: {e}")
        logger.error(f"Error output: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during data loading: {e}")
        raise


@op(
    retry_policy=RetryPolicy(max_retries=2),
    description="Run dbt transformations (staging and marts)"
)
def run_dbt_transformations(context, load_result: str) -> str:
    """
    Op 3: Run dbt Transformations
    
    Executes dbt models to create staging and mart tables.
    """
    logger.info("Running dbt transformations...")
    
    try:
        dbt_project_dir = BASE_DIR / "medical_warehouse"
        
        # Run dbt
        result = subprocess.run(
            [DBT_EXECUTABLE, "run"],
            cwd=str(dbt_project_dir),
            capture_output=True,
            text=True,
            check=True
        )
        
        logger.info(f"dbt transformations completed successfully")
        logger.info(f"Output: {result.stdout[-500:]}")
        
        # Also run tests
        test_result = subprocess.run(
            [DBT_EXECUTABLE, "test"],
            cwd=str(dbt_project_dir),
            capture_output=True,
            text=True
        )
        
        test_status = "passed" if test_result.returncode == 0 else "failed"
        logger.info(f"dbt tests: {test_status}")
        
        context.log_event(
            AssetMaterialization(
                asset_key="dbt_marts",
                description="dbt models built successfully",
                metadata={
                    "dbt_output": MetadataValue.text(result.stdout[-500:]),
                    "test_status": MetadataValue.text(test_status),
                    "status": MetadataValue.text("success")
                }
            )
        )
        
        return "dbt_success"
        
    except subprocess.CalledProcessError as e:
        logger.error(f"dbt transformation failed: {e}")
        logger.error(f"Error output: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during dbt transformations: {e}")
        raise


@op(
    retry_policy=RetryPolicy(max_retries=1),  # YOLO is expensive, only retry once
    description="Run YOLO object detection on images"
)
def run_yolo_enrichment(context, dbt_result: str) -> str:
    """
    Op 4: Run YOLO Enrichment
    
    Processes images with YOLOv8 to detect objects and classify images.
    """
    logger.info("Running YOLO object detection...")
    
    try:
        yolo_path = BASE_DIR / "src" / "yolo_detect.py"
        
        # Run YOLO detection
        result = subprocess.run(
            [PYTHON_EXECUTABLE, str(yolo_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=True
        )
        
        logger.info(f"YOLO detection completed successfully")
        logger.info(f"Output: {result.stdout[-500:]}")
        
        context.log_event(
            AssetMaterialization(
                asset_key="yolo_detections",
                description="YOLO object detection results generated",
                metadata={
                    "yolo_output": MetadataValue.text(result.stdout[-500:]),
                    "status": MetadataValue.text("success")
                }
            )
        )
        
        return "yolo_success"
        
    except subprocess.CalledProcessError as e:
        logger.error(f"YOLO detection failed: {e}")
        logger.error(f"Error output: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during YOLO detection: {e}")
        raise


@op(
    retry_policy=RetryPolicy(max_retries=2),
    description="Load YOLO results into PostgreSQL"
)
def load_yolo_results(context, yolo_result: str) -> str:
    """
    Op 5: Load YOLO Results to PostgreSQL
    
    Loads YOLO detection CSV into raw.yolo_detections table.
    """
    logger.info("Loading YOLO results to PostgreSQL...")
    
    try:
        loader_path = BASE_DIR / "scripts" / "load_yolo_results.py"
        
        result = subprocess.run(
            [PYTHON_EXECUTABLE, str(loader_path)],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            check=True
        )
        
        logger.info(f"YOLO results loading completed successfully")
        logger.info(f"Output: {result.stdout[-500:]}")
        
        # Rebuild dbt model that uses YOLO data
        dbt_project_dir = BASE_DIR / "medical_warehouse"
        dbt_result = subprocess.run(
            [DBT_EXECUTABLE, "run", "--select", "fct_image_detections"],
            cwd=str(dbt_project_dir),
            capture_output=True,
            text=True
        )
        
        context.log_event(
            AssetMaterialization(
                asset_key="yolo_postgres_data",
                description="YOLO detection results loaded and integrated",
                metadata={
                    "loader_output": MetadataValue.text(result.stdout[-500:]),
                    "status": MetadataValue.text("success")
                }
            )
        )
        
        return "yolo_loading_success"
        
    except subprocess.CalledProcessError as e:
        logger.error(f"YOLO results loading failed: {e}")
        logger.error(f"Error output: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during YOLO results loading: {e}")
        raise


@job(
    description="Complete ELT pipeline for Medical Telegram Warehouse",
    tags={"pipeline": "medical_telegram_warehouse", "type": "elt"}
)
def medical_telegram_pipeline():
    """
    Main pipeline job that orchestrates all operations.
    
    Pipeline flow:
    1. Scrape Telegram data
    2. Load raw data to PostgreSQL
    3. Run dbt transformations
    4. Run YOLO enrichment
    5. Load YOLO results to PostgreSQL
    """
    scrape_result = scrape_telegram_data()
    load_result = load_raw_to_postgres(scrape_result)
    dbt_result = run_dbt_transformations(load_result)
    yolo_result = run_yolo_enrichment(dbt_result)
    load_yolo_results(yolo_result)


if __name__ == "__main__":
    # For local testing, run with: dagster dev -f pipeline.py
    pass
