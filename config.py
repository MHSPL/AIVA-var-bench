"""
Configuration for AIVA Benchmark.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
RESULTS_DIR = BASE_DIR / "results"

# AIVA API Configuration
AIVA_API_URL = os.getenv("AIVA_API_URL", "http://localhost:8000")
AIVA_API_TOKEN = os.getenv("AIVA_API_TOKEN", "")

# Classification settings
DEFAULT_ASSEMBLY = os.getenv("DEFAULT_ASSEMBLY", "GRCh38")
CLASSIFICATION_TYPE = "acmg"  # acmg for germline, amp for somatic
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "google/gemini-3-flash-preview")  # None uses AIVA default (gemini-2.5-flash), or set e.g. "openai/gpt-4o"

# Request settings
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", "5"))  # Keep low to avoid rate limits
REQUEST_TIMEOUT = 300  # 5 minutes
MAX_RETRIES = 5
RETRY_DELAY = 10  # seconds base delay
RATE_LIMIT_DELAY = 30  # seconds to wait on 429

# Sampling settings
DEFAULT_SAMPLE_SIZE = int(os.getenv("DEFAULT_SAMPLE_SIZE", "200"))
RANDOM_SEED = 42

# Classification categories
CLASSIFICATION_LABELS = [
    "Pathogenic",
    "Likely Pathogenic",
    "Uncertain Significance",
    "Likely Benign",
    "Benign"
]

# Mapping for directional (3-class) comparison
CLASSIFICATION_TO_DIRECTION = {
    "Pathogenic": "pathogenic",
    "Likely Pathogenic": "pathogenic",
    "Uncertain Significance": "vus",
    "Likely Benign": "benign",
    "Benign": "benign",
    # AIVA variations
    "VUS": "vus",
    "VUS (leaning pathogenic)": "vus",
    "VUS (leaning benign)": "vus",
}

DIRECTION_LABELS = ["pathogenic", "vus", "benign"]

# wInterVar API Configuration
WINTERVAR_API_URL = os.getenv("WINTERVAR_API_URL", "http://wintervar.wglab.org/api_new.php")
WINTERVAR_ASSEMBLY = os.getenv("WINTERVAR_ASSEMBLY", "hg38")  # hg19 or hg38
