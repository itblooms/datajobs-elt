import requests
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
import json
import tempfile
from typing import Any
from logger import get_logger


logger = get_logger(__name__)


@retry(
    stop=stop_after_attempt(7),
    wait=wait_exponential_jitter(initial=1, max=60, jitter=1)
)
def fetch_api_data(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 30
) -> dict[str, Any]:
    try:
        logger.info(f"Fetching job postings data from {url}...")
        response = session.get(url=url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        logger.info("Page of job postings data successfully fetched.")
        return response.json()
    except requests.exceptions.HTTPError as exc:
        logger.error(f"Server responded with {exc}", exc_info=exc)
        raise
    except requests.exceptions.RequestException as exc:
        logger.error(f"Extraction failed with {exc}", exc_info=exc)
        raise
