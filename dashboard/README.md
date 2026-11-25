# E-Commerce Full-Stack Observability Lab (Datadog APM, Infra & Logs)

A local Docker lab that monitors a Python e-commerce checkout app using **Datadog**. It brings together **APM distributed tracing**, **Redis & PostgreSQL infrastructure checks**, and **trace-correlated JSON logs** inside a single SRE dashboard.

---

## Architecture

```text
[ Browser / Curl Traffic ]
            │
            ▼
 [ E-Commerce Checkout API ] ──(ddtrace APM + JSON Logs)──┐
    │                   │                                   │
 (Cart)             (Orders)                                ▼
    ▼                   ▼                        [ Datadog Agent Container ]
 [ Redis ]        [ PostgreSQL ]                  (DogStatsD, APM :8126, Logs)
    │                   │                                   │
    └───────────────────┴────(Docker Socket / Integrations)─┤
                                                            ▼
                                                [ Datadog Cloud Platform ]
                                             (APM, Infra, Logs, Dashboard)
```

### Tools Used
* **App & Storage:** Python 3.11, FastAPI, Redis (cart & product cache), PostgreSQL 15 (product catalog & inventory)
* **Instrumentation:** Datadog Python APM (`ddtrace-run`) with Unified Service Tagging (`env`, `service`, `version`)
* **Monitoring:** Datadog Agent 7 (`postgres.d` and `redisdb.d` integrations + Docker container log collection)

---

## Project Structure

```text
datadog-ecommerce-observability/
├── ecommerce-app/
│   ├── main.py                  # E-Commerce API (/catalog, /cart, /checkout, /flash-sale-slow, /payment-fail)
│   ├── requirements.txt         # FastAPI, DB drivers, and ddtrace
│   └── Dockerfile               # Runs app wrapped with ddtrace-run
├── datadog-conf/
│   ├── postgres.d/conf.yaml     # Datadog PostgreSQL integration check
│   └── redisdb.d/conf.yaml      # Datadog Redis integration check
├── dashboards/
│   └── ecommerce-sre-dashboard.json  # Exported Datadog SRE Dashboard JSON
├── screenshots/                 # Datadog dashboard & service catalog screenshots
├── .env                         # Local Datadog API key and site (ignored by Git)
├── .gitignore
├── docker-compose.yaml          # Runs App, Postgres, Redis, and Datadog Agent
└── README.md
```

---

## How to Run It

### 1. Prerequisites
* Docker Desktop
* A free 14-day [Datadog Trial](https://datadoghq.com) account and API key

### 2. Configure Your Datadog API Key
Create a `.env` file in the root folder:
```env
DD_API_KEY=<YOUR_DATADOG_API_KEY>
DD_SITE=datadoghq.com
```
*(Change `DD_SITE` to `://datadoghq.com` or `://datadoghq.com` depending on your Datadog account region.)*

### 3. Start the Stack
```bash
docker compose up --build -d
docker compose ps
```

### 4. Send Test Traffic
```bash
# Product lookup (1st call hits Postgres, 2nd call hits Redis cache)
curl http://localhost:8000/catalog/SKU-101
curl http://localhost:8000/catalog/SKU-101

# Add to cart and complete checkout
curl -X POST http://localhost:8000/cart/customer-101/add/SKU-101
curl http://localhost:8000/checkout/customer-101

# Simulate flash-sale latency spike (~2-3s)
curl http://localhost:8000/flash-sale-slow

# Simulate payment gateway timeout (HTTP 500 error + correlated log)
curl http://localhost:8000/payment-fail
```

### 5. Import the Dashboard
1. In Datadog, go to **Dashboards → New Dashboard → Blank Dashboard**.
2. Click the **Settings gear icon** (top-right) → **Import dashboard JSON**.
3. Paste the contents of `dashboards/ecommerce-sre-dashboard.json` and save.

---

## Screenshots

* **Unified SRE Dashboard:** `screenshots/datadog-sre-dashboard.png`
* **APM Service Catalog:** `screenshots/datadog-service-catalog.png`
