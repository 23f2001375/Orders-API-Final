from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from uuid import uuid4
import time
import base64

app = FastAPI()

# Allow CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

TOTAL_ORDERS = 54
RATE_LIMIT = 15
WINDOW = 10  # seconds

# In-memory storage
idempotency_store = {}
client_requests = {}

# Fixed catalog
catalog = [
    {
        "id": i,
        "item": f"Item {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]


class OrderRequest(BaseModel):
    item: str = "Sample Item"


@app.post("/orders", status_code=201)
def create_order(
    order: OrderRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    new_order = {
        "id": str(uuid4()),
        "item": order.item,
    }

    idempotency_store[idempotency_key] = new_order
    return new_order


@app.get("/orders")
def list_orders(
    limit: int = 10,
    cursor: str | None = None,
):
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


@app.middleware("http")
async def rate_limit(request, call_next):
    client = request.headers.get("X-Client-Id", "anonymous")

    now = time.time()

    history = client_requests.get(client, [])

    history = [t for t in history if now - t < WINDOW]

    if len(history) >= RATE_LIMIT:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
        headers={"Retry-After": "10"},
    )

    history.append(now)

    client_requests[client] = history

    return await call_next(request)