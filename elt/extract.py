import requests
from tenacity import retry, stop_after_attempt, wait_exponential_jitter
from typing import Any
import json
import tempfile
from datetime import date
from .logger import get_logger


logger = get_logger(__name__)


@retry(
    stop=stop_after_attempt(7),
    wait=wait_exponential_jitter(initial=1, max=60, jitter=1),
)
def fetch_api_data(
    session: requests.Session,
    url: str,
    params: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 30,
) -> dict[str, Any]:
    try:
        logger.info(f"Fetching job postings data from {url} ...")
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


def dump_to_temp(file_obj, items: list[dict[str, Any]]) -> None:
    logger.info("Dumping JSON postings data into temporary file...")
    for item in items:
        file_obj.write(json.dumps(item) + "\n")


def extract_api_data(
    url: str,
    params: dict[str, Any],
    headers: dict[str, str],
    timeout: int = 30,
) -> str:
    total_fetched = 0
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
        temp_file_path = temp_file.name
        with requests.Session() as session:
            while True:
                data = fetch_api_data(
                    session=session,
                    url=url,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )
                total_found = data.get("found", 0)
                items = data.get("items", [])

                if items:
                    dump_to_temp(temp_file, items)
                    total_fetched += len(items)
                else:
                    logger.warning("Received empty list of postings. Fetching stopped.")
                    break

                if total_fetched >= total_found:
                    logger.info("Successfully fetched and saved all postings data.")
                    break
                params = params.copy()
                params["page"] += 1
    return temp_file_path


def load_into_s3(s3_client, s3_bucket_name: str, s3_prefix: str, file_path: str) -> None:
    s3_file_name = date.today().isoformat()
    s3_key = f"{s3_prefix}/{s3_file_name}.json"
    logger.info(f"Uploading {file_path} to s3://{s3_bucket_name}/{s3_key} ...")
    s3_client.upload_file(file_path, s3_bucket_name, s3_key)
    logger.info("File successfully uploaded!")
