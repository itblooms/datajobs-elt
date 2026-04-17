import pytest
import logging
from unittest.mock import MagicMock, patch, call
import requests
import json
import tenacity
from datetime import date
from typing import Any

# Since @tenacity.retry decorator is applied at import time for fetch_api_data
# if is patched tenacity before importing the module under test.

with (
    patch("tenacity.stop_after_attempt") as mock_stop,
    patch("tenacity.wait_exponential_jitter") as mock_wait,
):
    mock_stop.return_value = tenacity.stop_after_attempt(1)
    # The wait strategy becomes a no-op (0 seconds) for all retries
    mock_wait.return_value = lambda *args, **kwargs: 0

    from elt.extract import (
        fetch_api_data,
        dump_to_temp,
        extract_api_data,
        load_into_s3,
    )


@pytest.fixture(autouse=True)
def caplog_setup(caplog):
    """Ensure we capture DEBUG+ logs from the module under test."""
    caplog.set_level(logging.DEBUG, logger="elt")
    return caplog


def test_fetch_api_data_success(caplog):
    """Happy path: successful GET, JSON returned, logs INFO, no exception."""
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"found": 42, "items": [{"id": 1}]}
    mock_session.get.return_value = mock_response

    url = "https://api.example.com/jobs"
    params: dict[str, Any] = {"page": 0, "limit": 10}
    headers = {"Authorization": "Bearer token123"}
    timeout = 15

    result = fetch_api_data(
        session=mock_session,
        url=url,
        params=params,
        headers=headers,
        timeout=timeout,
    )

    assert result == {"found": 42, "items": [{"id": 1}]}
    mock_session.get.assert_called_once_with(
        url=url, params=params, headers=headers, timeout=timeout
    )
    mock_response.raise_for_status.assert_called_once()
    mock_response.json.assert_called_once()

    assert any(
        "Fetching job postings data from https://api.example.com/jobs ..." in record.message
        and record.levelno == logging.INFO
        for record in caplog.records
    )
    assert any(
        "Page of job postings data successfully fetched." in record.message
        and record.levelno == logging.INFO
        for record in caplog.records
    )


def test_fetch_api_data_http_error(caplog):
    """
    Error path: HTTPError (e.g., 4xx/5xx) is logged and re-raised.
    Retry is forced to 1 attempt via top-level patch.
    """
    mock_session = MagicMock()
    mock_response = MagicMock()
    mock_session.get.return_value = mock_response
    error = requests.exceptions.HTTPError("500 Server Error")
    mock_response.raise_for_status.side_effect = error

    with pytest.raises(tenacity.RetryError) as exc_info:
        fetch_api_data(
            session=mock_session,
            url="https://api.example.com/jobs",
            params={"page": 0},
            headers={},
            timeout=30,
        )

    mock_session.get.assert_called_once()  # only 1 attempt due to patched stop
    assert isinstance(exc_info.value.last_attempt.exception(), requests.exceptions.HTTPError)
    assert any(
        "Server responded with" in record.message and record.levelno == logging.ERROR
        for record in caplog.records
    )


def test_fetch_api_data_request_exception(caplog):
    """
    Error path: non-HTTP RequestException (e.g. timeout, connection error)
    is logged and re-raised. Separate except block is exercised.
    """
    mock_session = MagicMock()
    error = requests.exceptions.Timeout("Connection timed out")
    mock_session.get.side_effect = error

    with pytest.raises(tenacity.RetryError) as exc_info:
        fetch_api_data(
            session=mock_session,
            url="https://api.example.com/jobs",
            params={"page": 0},
            headers={},
            timeout=30,
        )

    mock_session.get.assert_called_once()
    assert isinstance(exc_info.value.last_attempt.exception(), requests.exceptions.Timeout)
    assert any(
        "Extraction failed with" in record.message and record.levelno == logging.ERROR
        for record in caplog.records
    )


def test_dump_to_temp(caplog):
    """Dumps list of dicts as JSON Lines; verifies write calls and log."""
    mock_file = MagicMock()
    items = [
        {"id": 1, "title": "Software Engineer", "company": "Acme"},
        {"id": 2, "title": "Data Scientist", "company": "Beta Corp"},
    ]

    dump_to_temp(mock_file, items)

    assert mock_file.write.call_count == 2
    expected_calls = [call(json.dumps(item) + "\n") for item in items]
    mock_file.write.assert_has_calls(expected_calls, any_order=False)

    assert any(
        "Dumping JSON postings data into temporary file..." in record.message
        and record.levelno == logging.INFO
        for record in caplog.records
    )


@patch("elt.extract.fetch_api_data")
@patch("elt.extract.dump_to_temp")
@patch("elt.extract.tempfile.NamedTemporaryFile")
def test_extract_api_data_multiple_pages(
    mock_named_tempfile,
    mock_dump,
    mock_fetch,
    caplog,
):
    """
    Multi-page pagination: fetches until total_fetched >= total_found.
    Verifies temp file, session usage, param mutation, dump calls, final log.
    """
    mock_file_obj = MagicMock()
    mock_file_obj.name = "/tmp/postings_20260417.json"
    mock_named_tempfile.return_value.__enter__.return_value = mock_file_obj
    mock_named_tempfile.return_value.__exit__.return_value = None

    mock_fetch.side_effect = [
        {"found": 5, "items": [{"id": 1}, {"id": 2}]},  # page 0
        {"found": 5, "items": [{"id": 3}, {"id": 4}, {"id": 5}]},  # page 1
    ]

    url = "https://api.example.com/jobs"
    params: dict[str, Any] = {"page": 0, "limit": 100, "query": "python"}
    headers = {"Authorization": "Bearer token123"}
    timeout = 25

    result_path = extract_api_data(url, params, headers, timeout)

    assert result_path == "/tmp/postings_20260417.json"
    assert mock_named_tempfile.call_count == 1
    assert mock_fetch.call_count == 2
    assert mock_dump.call_count == 2

    call_args_list = mock_fetch.call_args_list
    print(call_args_list)
    assert call_args_list[0].kwargs["params"]["page"] == 0
    assert call_args_list[1].kwargs["params"]["page"] == 1
    assert params["page"] == 0
    # Session is created inside the function (we don't care about exact instance)
    assert call_args_list[0].kwargs["session"] is not None
    assert call_args_list[1].kwargs["session"] is not None

    mock_dump.assert_any_call(mock_file_obj, [{"id": 1}, {"id": 2}])
    mock_dump.assert_any_call(mock_file_obj, [{"id": 3}, {"id": 4}, {"id": 5}])

    assert any(
        "Successfully fetched and saved all postings data." in record.message
        and record.levelno == logging.INFO
        for record in caplog.records
    )


@patch("elt.extract.fetch_api_data")
@patch("elt.extract.dump_to_temp")
@patch("elt.extract.tempfile.NamedTemporaryFile")
def test_extract_api_data_empty_items_early_stop(
    mock_named_tempfile,
    mock_dump,
    mock_fetch,
    caplog,
):
    """
    Edge case: empty 'items' list triggers warning and immediate stop
    (even if total_found suggests more data). No dump occurs.
    """
    mock_file_obj = MagicMock()
    mock_file_obj.name = "/tmp/empty.json"
    mock_named_tempfile.return_value.__enter__.return_value = mock_file_obj

    mock_fetch.side_effect = [{"found": 100, "items": []}]

    result_path = extract_api_data(
        url="https://api.example.com/jobs",
        params={"page": 0},
        headers={},
        timeout=30,
    )

    assert result_path == "/tmp/empty.json"
    assert mock_fetch.call_count == 1
    assert mock_dump.call_count == 0  # no items -> no dump

    assert any(
        "Received empty list of postings. Fetching stopped." in record.message
        and record.levelno == logging.WARNING
        for record in caplog.records
    )


@patch("elt.extract.fetch_api_data")
@patch("elt.extract.dump_to_temp")
@patch("elt.extract.tempfile.NamedTemporaryFile")
def test_extract_api_data_zero_found(
    mock_named_tempfile,
    mock_dump,
    mock_fetch,
    caplog,
):
    """Edge case: total_found=0 and empty items -> clean stop with warning."""
    mock_file_obj = MagicMock()
    mock_file_obj.name = "/tmp/zero.json"
    mock_named_tempfile.return_value.__enter__.return_value = mock_file_obj

    mock_fetch.side_effect = [{"found": 0, "items": []}]

    result_path = extract_api_data("https://api.example.com/jobs", {"page": 0}, {}, 30)

    assert mock_dump.call_count == 0
    assert any(
        "Received empty list of postings. Fetching stopped." in record.message
        for record in caplog.records
    )


@patch("elt.extract.fetch_api_data")
@patch("elt.extract.dump_to_temp")
@patch("elt.extract.tempfile.NamedTemporaryFile")
def test_extract_api_data_missing_page_key(
    mock_named_tempfile,
    mock_dump,
    mock_fetch,
    caplog,
):
    """
    Edge case / nuance: if 'page' key is absent from params,
    first fetch succeeds but KeyError is raised on the first +=1.
    This documents the implicit contract on input params.
    """
    mock_file_obj = MagicMock()
    mock_file_obj.name = "/tmp/missing.json"
    mock_named_tempfile.return_value.__enter__.return_value = mock_file_obj

    mock_fetch.side_effect = [{"found": 3, "items": [{"id": 1}]}]

    with pytest.raises(KeyError, match="page"):
        extract_api_data(
            url="https://api.example.com/jobs",
            params={"limit": 10},  # missing "page"
            headers={},
            timeout=30,
        )

    # First fetch still happened
    assert mock_fetch.call_count == 1


@patch("elt.extract.date")
def test_load_into_s3(mock_date, caplog):
    """S3 upload with dynamic date-based key; verifies upload call and logs."""
    # Mock today's date
    mock_date.today.return_value = date(2026, 4, 17)

    mock_s3_client = MagicMock()
    bucket_name = "my-data-bucket"
    s3_prefix = "raw/job_postings"
    file_path = "/tmp/postings_20260417.json"

    load_into_s3(mock_s3_client, bucket_name, s3_prefix, file_path)

    expected_key = f"{s3_prefix}/2026-04-17.json"
    mock_s3_client.upload_file.assert_called_once_with(file_path, bucket_name, expected_key)

    assert any(
        f"Uploading {file_path} to s3://{bucket_name}/{expected_key} ..." in record.message
        and record.levelno == logging.INFO
        for record in caplog.records
    )
    assert any(
        "File successfully uploaded!" in record.message and record.levelno == logging.INFO
        for record in caplog.records
    )
