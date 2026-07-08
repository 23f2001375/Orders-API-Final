from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from uuid import uuid4
from collections import defaultdict, deque
import base64
import time

app = FastAPI()

EMAIL = "23f2001375@ds.study.iitm.ac.in"

ALLOWED_ORIGINS = [
    "https://exam.sanand.workers.dev",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 54
RATE_LIMIT = 15
WINDOW = 10

# -----------------------------
# Fixed catalog
# -----------------------------
catalog = [{"id": i} for i in range(1, TOTAL_ORDERS + 1)]

# -----------------------------
# In-memory stores
# -----------------------------
idempotency = {}
rate_buckets = defaultdict(deque)


class Order(BaseModel):
    item: str = "Sample Item"


# -----------------------------
# Rate Limiter Middleware
# -----------------------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):

    # Allow preflight requests
    if request.method == "OPTIONS":
        return await call_next(request)

    client = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()
    bucket = rate_buckets[client]

    while bucket and now - bucket[0] >= WINDOW:
        bucket.popleft()

    if len(bucket) >= RATE_LIMIT:

        retry_after = max(1, int(WINDOW - (now - bucket[0])))

        response = JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
        )

        response.headers["Retry-After"] = str(retry_after)

        origin = request.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"

        return response

    bucket.append(now)

    response = await call_next(request)
    return response


# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders", status_code=201)
def create_order(
    order: Order,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):

    if idempotency_key in idempotency:
        return idempotency[idempotency_key]

    result = {
        "id": str(uuid4()),
        "item": order.item,
    }

    idempotency[idempotency_key] = result
    return result


# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def get_orders(limit: int = 10, cursor: str | None = None):

    limit = max(1, min(limit, TOTAL_ORDERS))

    start = 0

    if cursor:
        try:
            start = int(base64.b64decode(cursor).decode())
        except Exception:
            start = 0

    end = min(start + limit, TOTAL_ORDERS)

    items = catalog[start:end]

    next_cursor = None
    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end).encode()).decode()

    return {
        "items": items,
        "next_cursor": next_cursor,
    }


@app.get("/")
def root():
    return {"status": "ok"}