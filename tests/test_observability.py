"""YOUR tests for the observability layer.

Per the lab guide, write at least 3 substantive tests, each with at least
1 assertion. The autograder enforces only the structure (3+ test functions,
each with an `assert` and a non-stub body); the specific behaviors you
choose to verify are up to you.

You name the tests, you decide what to assert, you choose the test
strategy (TestClient + header inspection? caplog + log parsing?
/metrics scrape + counter delta?). The placeholders below show one
possible split (one test per middleware), but you are free to pick any
three behaviors that exercise meaningful properties of your
instrumentation -- e.g. test that the request-id flows across two
sequential requests with distinct ids, test that the metrics counter
reflects a 500 response status correctly, test that the structured log
line carries the X-Request-ID matching the response header.

The autograder does not import your test function names; rename them
freely.
"""

import pytest
import json
import logging
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from api.main import app

client = TestClient(app)


def test_one():
    # TODO: write a meaningful test of your observability layer here.
    
    # Test RequestIdMiddleware: Ensure X-Request-ID header is present and not empty
    response = client.get("/healthz")
    assert response.status_code == 200
    
    req_id = response.headers.get("x-request-id")
    assert req_id is not None, "X-Request-ID header is missing"
    assert req_id != "", "X-Request-ID header is empty"


def test_two():
    # TODO: write a meaningful test of your observability layer here.
    
    # Test MetricsMiddleware: Ensure the requests_total counter is incremented
    val1 = REGISTRY.get_sample_value("requests_total_total", {"path": "/healthz", "status": "200"})
    if val1 is None:
        val1 = REGISTRY.get_sample_value("requests_total", {"path": "/healthz", "status": "200"}) or 0.0
        
    response = client.get("/healthz")
    assert response.status_code == 200
    
    val2 = REGISTRY.get_sample_value("requests_total_total", {"path": "/healthz", "status": "200"})
    if val2 is None:
        val2 = REGISTRY.get_sample_value("requests_total", {"path": "/healthz", "status": "200"}) or 0.0
        
    assert val2 == val1 + 1.0


def test_three(caplog):
    # TODO: write a meaningful test of your observability layer here.
    
    # Test StructuredLoggingMiddleware: Ensure the JSON log contains the matching request_id
    caplog.set_level(logging.INFO, logger="m11.api")
    
    response = client.get("/healthz")
    req_id = response.headers.get("x-request-id")
    
    log_matched = False
    for record in caplog.records:
        if record.name == "m11.api":
            try:
                log_data = json.loads(record.message)
                if log_data.get("request_id") == req_id:
                    log_matched = True
                    break
            except ValueError:
                continue
                
    assert log_matched, "No structured log found containing the matching request_id"