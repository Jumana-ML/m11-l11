"""Observability layer for the M10 backend.

This module is where you (the learner) declare the three Prometheus metric
families and implement the three ASGI middleware classes that the autograder
exercises through the FastAPI app.

What lives here, and why:

  - Three metric families. A counter for request volume by (path, status), a
    histogram for request latency by path, and a gauge for in-flight requests.
    Together they answer "how much traffic, how slow, how concurrent."

  - Three middlewares. A request-id layer that attaches a per-request
    correlation id to the response and to the logging context. A
    structured-logging layer that emits one JSON line per response. A metrics
    layer that increments the counter, observes the latency histogram, and
    brackets the request with the in-flight gauge.

  Ordering matters: request-id is outermost (so it wraps the logging line),
  logging is middle, metrics is innermost (closest to the route).

Where to put what:

  - Declarations at MODULE SCOPE. If you declare a Counter / Histogram / Gauge
    inside a function or inside a middleware __call__, you will hit
    `Duplicated timeseries in CollectorRegistry` on the second request --
    every request re-runs the function. Module scope means the registry sees
    the declaration once at import time.

  - Label cardinality matters. The Lab's `requests_total` Counter uses
    exactly two labels: {path, status}. Do NOT add user-id, query-text,
    full-URL, or any other unbounded label.

Methodology pointers:

  - Reading sections 6-10 cover middleware, metric types, label cardinality.
  - See Common Pitfalls #1-#4 in the lab guide.
"""

# import Counter, Histogram, Gauge from prometheus_client.
from prometheus_client import Counter, Histogram, Gauge
import time
import json
import logging
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# ContextVar is like a private pocket to hold our Request ID for the current request
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
logger = logging.getLogger("m11.api")

# declare the three metric families at module scope.
#
#   requests_total           — Counter, labels (path, status)
#   request_latency_seconds  — Histogram, label (path); use the default
#                              Prometheus latency buckets.
#   inflight_requests        — Gauge, no labels.
#
# Do not over-label — see the cardinality discussion in the M11 reading.

requests_total = Counter(
    "requests_total",
    "Total HTTP requests",
    ["path", "status"]
)

request_latency_seconds = Histogram(
    "request_latency_seconds",
    "Request latency in seconds",
    ["path"]
)

inflight_requests = Gauge(
    "inflight_requests",
    "Currently active in-flight requests"
)

# implement RequestIdMiddleware (ASGI middleware class).
#
#   - __init__(self, app): store app.
#   - __call__(self, scope, receive, send): generate a request id, store it
#     somewhere the logging layer can read (a ContextVar is the standard
#     pattern), and arrange for the outbound response to carry an
#     `X-Request-ID` header.
#
#   The autograder asserts the response header is present and at least 8
#   characters long.

class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = uuid.uuid4().hex
        token = request_id_var.set(req_id)
        
        response = await call_next(request)
        
        response.headers["X-Request-ID"] = req_id
        request_id_var.reset(token)
        return response

# implement StructuredLoggingMiddleware (ASGI middleware class).
#
#   - On response, emit one JSON line containing the keys:
#       request_id, path, status, latency_ms
#     plus any other keys you find useful. The autograder asserts the four
#     keys above are present and parseable as JSON.

class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        response = await call_next(request)
        
        latency_ms = (time.time() - start_time) * 1000
        req_id = request_id_var.get()
        
        log_data = {
            "request_id": req_id,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": latency_ms
        }
        logger.info(json.dumps(log_data))
        
        return response

# implement MetricsMiddleware (ASGI middleware class).
#
#   - On request: increment inflight_requests.
#   - Around the route handler: time the request.
#   - On response: increment requests_total with the (path, status) label
#     pair, observe the latency histogram, decrement inflight_requests.
#
#   Do not include high-cardinality labels (no user id, no query string).

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        inflight_requests.inc()
        start_time = time.time()
        
        try:
            response = await call_next(request)
            
            elapsed = time.time() - start_time
            path = request.url.path
            status = str(response.status_code)
            
            requests_total.labels(path=path, status=status).inc()
            request_latency_seconds.labels(path=path).observe(elapsed)
            
            return response
        finally:
            inflight_requests.dec()