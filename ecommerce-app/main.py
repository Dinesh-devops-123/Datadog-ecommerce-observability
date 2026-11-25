import logging
import os
import random
import time
import psycopg2
import redis
from ddtrace import tracer
from fastapi import FastAPI, HTTPException

# Structured JSON Logger with automatic Datadog Trace/Span ID injection
class DatadogJSONFormatter(logging.Formatter):
    def format(self, record):
        span = tracer.current_span()
        trace_id = span.trace_id if span else 0
        span_id = span.span_id if span else 0
        log_record = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "service": os.getenv("DD_SERVICE", "ecommerce-checkout-api"),
            "env": os.getenv("DD_ENV", "prod"),
            "version": os.getenv("DD_VERSION", "1.0.0"),
            "dd.trace_id": str(trace_id),
            "dd.span_id": str(span_id),
            "message": record.getMessage(),
        }
        return str(log_record).replace("'", '"')

handler = logging.StreamHandler()
handler.setFormatter(DatadogJSONFormatter())
logger = logging.getLogger("ecommerce-logger")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

app = FastAPI(title="E-Commerce Storefront API")

redis_client = redis.Redis(host="redis", port=6379, decode_responses=True)

def get_db():
    return psycopg2.connect(
        host="postgres",
        database="ecommerce_db",
        user="postgres",
        password="postgres"
    )

@app.on_event("startup")
def init_db():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS catalog (
                sku VARCHAR(50) PRIMARY KEY,
                product_name VARCHAR(100),
                price NUMERIC(10, 2),
                stock INT
            );
        """)
        cur.execute("SELECT COUNT(*) FROM catalog;")
        if cur.fetchone()[0] == 0:
            cur.execute("""
                INSERT INTO catalog (sku, product_name, price, stock) VALUES
                ('SKU-101', 'Wireless Noise-Canceling Headphones', 149.99, 50),
                ('SKU-102', 'Mechanical Gaming Keyboard', 89.50, 35),
                ('SKU-103', '4K USB-C Docking Station', 199.00, 20);
            """)
        conn.commit()
        cur.close()
        conn.close()
        logger.info("E-Commerce catalog database initialized.")
    except Exception as e:
        logger.error(f"Database startup failed: {e}")

@app.get("/health")
def health():
    return {"status": "healthy"}

@app.get("/catalog/{sku}")
def get_product(sku: str):
    """Fetches product from Redis cache or PostgreSQL database."""
    cache_key = f"catalog:{sku}"
    cached = redis_client.get(cache_key)
    if cached:
        logger.info(f"Cache HIT for {sku}")
        return {"source": "redis", "product": cached}

    logger.info(f"Cache MISS for {sku} - querying PostgreSQL")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT sku, product_name, price, stock FROM catalog WHERE sku = %s;", (sku,))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        logger.warning(f"Product {sku} not found in catalog")
        raise HTTPException(status_code=404, detail="SKU not found")

    product_info = f"{row[1]} - ${row[2]} ({row[3]} in stock)"
    redis_client.setex(cache_key, 60, product_info)
    return {"source": "postgresql", "product": product_info}

@app.post("/cart/{user_id}/add/{sku}")
def add_to_cart(user_id: str, sku: str):
    """Adds an item to the customer's Redis shopping cart."""
    with tracer.trace("cart.redis.update", service="ecommerce-checkout-api") as span:
        span.set_tag("customer.id", user_id)
        span.set_tag("product.sku", sku)
        redis_client.rpush(f"cart:{user_id}", sku)
        logger.info(f"Added {sku} to cart for customer={user_id}")
    return {"status": "added", "user_id": user_id, "sku": sku}

@app.get("/checkout/{user_id}")
def checkout_order(user_id: str):
    """Processes customer checkout across Redis cart and PostgreSQL inventory."""
    with tracer.trace("checkout.order.process", service="ecommerce-checkout-api") as span:
        span.set_tag("customer.id", user_id)
        span.set_tag("payment.gateway", "razorpay-live")
        items = redis_client.lrange(f"cart:{user_id}", 0, -1)
        if not items:
            items = ["SKU-101"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE catalog SET stock = stock - 1 WHERE sku = %s;", (items[0],))
        conn.commit()
        cur.close()
        conn.close()

        redis_client.delete(f"cart:{user_id}")
        logger.info(f"Order completed successfully for customer={user_id}, items={items}")
    return {"status": "order_confirmed", "customer": user_id, "items": items}

@app.get("/flash-sale-slow")
def flash_sale_slow():
    """Simulates high-traffic flash sale database/payment lock latency."""
    delay = round(random.uniform(1.8, 3.2), 2)
    with tracer.trace("payment.gateway.authorize", service="payment-gateway-external") as span:
        span.set_tag("payment.gateway", "stripe-checkout")
        span.set_tag("flash_sale", "true")
        logger.warning(f"Flash sale traffic spike: payment authorization took {delay}s")
        time.sleep(delay)
    return {"status": "slow_checkout_complete", "latency_seconds": delay}

@app.get("/payment-fail")
def payment_fail():
    """Simulates a critical 500 checkout failure for Datadog Error Tracking & SLO burn."""
    with tracer.trace("payment.gateway.charge", service="payment-gateway-external") as span:
        span.set_tag("error", True)
        span.set_tag("error.type", "PaymentGatewayTimeout")
        logger.error("CRITICAL: Checkout payment failed with HTTP 500 Gateway Timeout!")
        raise HTTPException(status_code=500, detail="Payment Gateway Timeout during Checkout")
