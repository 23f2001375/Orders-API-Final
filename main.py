from fastapi import FastAPI, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from uuid import uuid4
import base64
import time

app = FastAPI()

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

idempotency = {}
rate_buckets = {}

catalog = [{"id": i} for i in range(1, TOTAL_ORDERS + 1)]


class Order(BaseModel):
    item: str = "Sample Item"


@app.middleware("http")
async def limiter(request: Request, call_next):
    # Allow CORS preflight
    if request.method == "OPTIONS":
        return await call_next(request)

    client = request.headers.get("X-Client-Id", "anonymous")
    now = time.time()

    bucket = rate_buckets.get(client, [])
    bucket = [t for t in bucket if now - t < WINDOW]

    if len(bucket) >= RATE_LIMIT:
        response = JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
        )

        origin = request.headers.get("Origin")
        if origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"

        response.headers["Retry-After"] = "10"
        return response

    bucket.append(now)
    rate_buckets[client] = bucket

    return await call_next(request)


@app.post("/orders")
def create_order(
    order: Order,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    if idempotency_key in idempotency:
        return JSONResponse(
            status_code=200,
            content=idempotency[idempotency_key],
        )

    result = {
        "id": str(uuid4()),
        "item": order.item,
    }

    idempotency[idempotency_key] = result

    return JSONResponse(
        status_code=201,
        content=result,
    )

@app.get("/orders")
def get_orders(limit: int = 10, cursor: str | None = None):

    start = 0

    if cursor:
        try:
            start = int(base64.b64decode(cursor).decode())
        except Exception:
            start = 0

    limit = max(1, min(limit, TOTAL_ORDERS))

    end = min(start + limit, TOTAL_ORDERS)

    items = catalog[start:end]

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = base64.b64encode(str(end).encode()).decode()

    return {
        "items": items,
        "next_cursor": next_cursor,
    }