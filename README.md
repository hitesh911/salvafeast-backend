# Salva Backend

Multi-tenant SaaS backend for restaurant/cafe/dhaba management.

## Prerequisites

- Python 3.12
- PostgreSQL (local install, not Docker)

## Setup

### 1. Create the database

```sql
CREATE DATABASE salva;
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

**System dependency for UPI QR scanning:** `pyzbar` requires the native ZBar library. The Python venv alone does not install it.

- **Linux (Debian/Ubuntu):** `sudo apt install libzbar0`
- **macOS:** `brew install zbar`
- **Windows:** install a ZBar build that provides `libzbar-64.dll` (or use WSL/Linux for QR upload testing)

Without ZBar, direct UPI ID entry still works; only the QR image upload endpoint needs it.

### 4. Configure environment

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # macOS / Linux
```

Edit `.env` and set your database credentials (`DB_HOST`, `DB_USER`, `DB_PASSWORD`, etc.), `JWT_SECRET_KEY`, and platform admin credentials.

### 5. Run migrations

```bash
alembic upgrade head
```

### 6. Seed permissions, roles, and platform admin

```bash
python scripts/seed.py
```

### 7. Start the server

```bash
python run.py
```

Or directly with uvicorn:

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`. Interactive docs at `/docs`.

## Testing the endpoints

### Health check (no auth)

```bash
curl http://127.0.0.1:8000/api/v1/health
```

### Platform admin login (email + password)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@example.com", "password": "changeme"}'
```

### Create an outlet (platform admin only)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/platform/outlets \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "name": "Demo Cafe",
    "slug": "demo-cafe",
    "owner_name": "John Doe",
    "owner_phone": "9876543210"
  }'
```

### Update outlet settings (platform admin only)

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/platform/outlets/<outlet_id>/settings \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{"require_customer_login": true}'
```

### Outlet user OTP login

Request OTP (404 if the phone is not a registered staff user; max 3 requests / 10 minutes):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/otp/request \
  -H "Content-Type: application/json" \
  -d '{"phone": "9876543210"}'
```

Check server logs for the OTP (ConsoleSmsProvider), then verify:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/otp/verify \
  -H "Content-Type: application/json" \
  -d '{"phone": "9876543210", "otp_code": "123456"}'
```

## Project structure

```
salva-backend/
  app/
    core/           # config, security, SMS provider abstraction
    db/             # SQLAlchemy engine/session
    models/         # SQLAlchemy ORM models
    schemas/        # Pydantic request/response schemas
    api/v1/         # versioned route handlers
    main.py         # FastAPI entrypoint
  alembic/          # database migrations
  scripts/          # seed script
  requirements.txt
  .env.example
```

## SMS provider

OTP delivery uses `ConsoleSmsProvider` by default (logs OTP to console). Set `SMS_PROVIDER=whatsapp` with Fast2SMS credentials (`FAST2SMS_AUTH_KEY`, `FAST2SMS_PHONE_NUMBER_ID`, `FAST2SMS_MESSAGE_ID`) to send WhatsApp template codes via Fast2SMS `message_id`. Switching providers is done only in `init_sms_provider()` — calling code still uses `send_otp()`.
