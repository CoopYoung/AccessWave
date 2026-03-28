# AccessWave

**WCAG 2.1 Accessibility Scanner SaaS** — Automated detection of ADA/WCAG violations with actionable fix instructions, accessibility scoring, and multi-site monitoring.

98% of websites fail WCAG compliance and ADA-related lawsuits have increased 300%. AccessWave provides automated scanning as a preventative measure for website owners, developers, and agencies.

---

## Features

### Scanning Engine (17 WCAG 2.1 Checks)

| Rule ID | WCAG Criteria | What It Checks | Severity |
|---------|--------------|-----------------|----------|
| `img-alt` | 1.1.1 | Images missing alt text | Critical |
| `heading-order` | 1.3.1 | Heading hierarchy (h1→h2→h3) | Moderate |
| `table-header` | 1.3.1 | Data tables missing `<th>` headers | Serious |
| `landmark` | 1.3.1 | Missing landmark regions (main, nav, etc.) | Moderate |
| `autocomplete` | 1.3.5 | Input fields missing autocomplete attributes | Minor |
| `media-autoplay` | 1.4.2 | Audio/video elements with autoplay | Serious |
| `color-contrast` | 1.4.3 | Potential color contrast issues | Serious |
| `resize-text` | 1.4.4 | Viewport meta disabling user zoom | Critical |
| `skip-nav` | 2.4.1 | Missing skip navigation links | Serious |
| `page-title` | 2.4.2 | Missing or empty `<title>` | Critical |
| `focus-order` | 2.4.3 | Problematic positive tabindex values | Moderate |
| `link-purpose` | 2.4.4 | Non-descriptive link text ("click here", "read more") | Serious |
| `html-lang` | 3.1.1 | Missing `lang` attribute on `<html>` | Critical |
| `duplicate-id` | 4.1.1 | Duplicate element IDs | Serious |
| `form-label` | 4.1.2 | Form inputs without associated labels | Critical |
| `button-name` | 4.1.2 | Buttons without accessible names | Critical |
| `aria-roles` | 4.1.2 | Invalid ARIA roles | Serious |

### Accessibility Scoring

Every scan produces a score from 0–100 using a diminishing penalty formula. Issues are weighted by severity:

- **Critical** — 10-point penalty
- **Serious** — 5-point penalty
- **Moderate** — 2-point penalty
- **Minor** — 1-point penalty

### Multi-Page Crawling

AccessWave doesn't just scan the homepage. The async crawler traverses internal links up to a configurable depth (default: 3 levels), scanning every discovered page within plan limits.

### Actionable Fix Instructions

Every issue includes:
- Human-readable description of the problem
- The specific WCAG criteria violated
- A snippet of the offending HTML element
- Step-by-step instructions on how to fix it

### SaaS Multi-Tenancy

- User registration and JWT-based authentication
- Three subscription tiers with Stripe billing integration
- Plan-based limits on sites, pages per scan, and monthly scans
- Per-user site management with cascade deletion

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Framework** | FastAPI 0.115.6 (async Python) |
| **Server** | Uvicorn 0.34.0 (ASGI) |
| **Database** | SQLite via aiosqlite + SQLAlchemy 2.0 (async ORM) |
| **Auth** | JWT (python-jose, HS256) + bcrypt password hashing |
| **Payments** | Stripe 11.4.1 |
| **Crawling** | httpx 0.28.1 (async HTTP client) |
| **Parsing** | BeautifulSoup4 + lxml |
| **CSS Analysis** | cssutils 2.11.0 |
| **Frontend** | Jinja2 templates, vanilla JS, CSS3 with custom properties |
| **Containerization** | Docker + Docker Compose |

---

## Project Structure

```
AccessWave/
├── app/
│   ├── routers/
│   │   ├── auth_router.py         # Registration & login endpoints
│   │   ├── billing_router.py      # Stripe subscription management
│   │   └── scan_router.py         # Sites, scans, issues, dashboard stats
│   ├── services/
│   │   ├── crawler.py             # Async web crawler (depth-based traversal)
│   │   ├── scanner.py             # WCAG 2.1 rule engine (17 checks, ~520 LOC)
│   │   └── scan_runner.py         # Scan orchestration (crawl → scan → aggregate)
│   ├── static/
│   │   ├── css/style.css          # Design system with CSS variables
│   │   └── js/app.js              # Frontend API client & dashboard logic
│   ├── templates/
│   │   ├── landing.html           # Marketing homepage with pricing
│   │   ├── login.html             # Login page
│   │   ├── register.html          # Registration page
│   │   └── dashboard.html         # User dashboard (sites, scans, issues)
│   ├── auth.py                    # JWT token creation & password hashing
│   ├── config.py                  # Settings, plan limits, environment vars
│   ├── database.py                # Async SQLAlchemy engine & session
│   ├── main.py                    # FastAPI app entry point
│   └── models.py                  # SQLAlchemy ORM models (User, Site, Scan, Issue)
├── tests/                         # Test directory (not yet populated)
├── docker-compose.yml             # Local development orchestration
├── Dockerfile                     # Production container (Python 3.12-slim)
├── requirements.txt               # Python dependencies
├── .env.example                   # Environment variable template
├── run.py                         # Development server launcher
└── .gitignore
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- (Optional) Docker & Docker Compose

### Local Development

```bash
# 1. Clone the repository
git clone <repo-url> && cd AccessWave

# 2. Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — at minimum, set a strong SECRET_KEY

# 5. Run the development server
python run.py
```

The app starts at **http://localhost:8000** with auto-reload enabled.

### Docker Deployment

```bash
# Build and run
docker-compose up --build
```

The SQLite database is persisted in a Docker volume (`db-data`). Access the app at **http://localhost:8000**.

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | SQLAlchemy async database URL | `sqlite+aiosqlite:///./accesswave.db` |
| `SECRET_KEY` | JWT signing key (**change in production**) | `change-me-to-a-random-secret-key` |
| `STRIPE_SECRET_KEY` | Stripe API secret key | — |
| `STRIPE_PUBLISHABLE_KEY` | Stripe publishable key (frontend) | — |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret | — |
| `STRIPE_PRICE_PRO` | Stripe Price ID for Pro plan | — |
| `STRIPE_PRICE_AGENCY` | Stripe Price ID for Agency plan | — |
| `BASE_URL` | Application base URL | `http://localhost:8000` |

---

## API Reference

All protected endpoints require an `Authorization: Bearer <token>` header.

### Authentication

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `POST` | `/api/auth/register` | Create account (email, password) | No |
| `POST` | `/api/auth/login` | Get JWT token (OAuth2 password grant) | No |

### Sites & Scans

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/api/sites` | List user's sites | Yes |
| `POST` | `/api/sites` | Add a site (name, url) | Yes |
| `DELETE` | `/api/sites/{site_id}` | Delete a site and all its data | Yes |
| `POST` | `/api/sites/{site_id}/scan` | Start a new scan (background task) | Yes |
| `GET` | `/api/sites/{site_id}/scans` | List scans for a site (paginated) | Yes |
| `GET` | `/api/scans/{scan_id}` | Get scan details | Yes |
| `GET` | `/api/scans/{scan_id}/issues` | Get issues (filterable by severity, rule_id) | Yes |
| `GET` | `/api/dashboard/stats` | Dashboard summary stats | Yes |

### Billing

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| `GET` | `/api/billing/plan` | Get current plan and limits | Yes |
| `POST` | `/api/billing/checkout/{plan}` | Create Stripe checkout session | Yes |
| `POST` | `/api/billing/webhook` | Stripe webhook handler | No |

### Pages

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Landing page |
| `GET` | `/login` | Login page |
| `GET` | `/register` | Registration page |
| `GET` | `/dashboard` | User dashboard |

---

## Database Schema

Four tables with cascade-delete relationships:

```
User (1) ──→ (N) Site (1) ──→ (N) Scan (1) ──→ (N) Issue
```

**User** — `id`, `email`, `hashed_password`, `plan` (free/pro/agency), `stripe_customer_id`, `stripe_subscription_id`, `created_at`

**Site** — `id`, `user_id` (FK), `url`, `name`, `created_at`

**Scan** — `id`, `site_id` (FK), `status` (pending/running/completed/failed), `pages_scanned`, `total_issues`, `critical_count`, `serious_count`, `moderate_count`, `minor_count`, `score` (0–100), `started_at`, `completed_at`, `created_at`

**Issue** — `id`, `scan_id` (FK), `page_url`, `rule_id`, `severity`, `wcag_criteria`, `message`, `element_html`, `selector`, `how_to_fix`

---

## Subscription Plans

| | Free | Pro | Agency |
|---|------|-----|--------|
| **Price** | $0/mo | $29/mo | $79/mo |
| **Sites** | 1 | 10 | 50 |
| **Pages per scan** | 5 | 50 | 200 |
| **Scans per month** | 3 | 100 | Unlimited |
| **WCAG checks** | All 17 | All 17 | All 17 |
| **Fix instructions** | Yes | Yes | Yes |
| **Scan history** | — | Yes | Yes |
| **Priority support** | — | — | Yes |

---

## Configuration

Key settings in `app/config.py`:

| Setting | Value | Description |
|---------|-------|-------------|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 10,080 (7 days) | JWT token lifetime |
| `ALGORITHM` | HS256 | JWT signing algorithm |
| `SCAN_TIMEOUT` | 30s | Per-page crawl timeout |
| `MAX_CRAWL_DEPTH` | 3 | Maximum link traversal depth |
| `PLAN_LIMITS` | See plans above | Per-plan resource caps |

---

## Architecture Notes

- **Fully async**: Database queries, HTTP crawling, and request handling all use `async`/`await`
- **Background scanning**: Scans run as FastAPI background tasks — the API returns immediately while the scan processes
- **Stateless auth**: JWT tokens with no server-side session storage
- **Multi-tenant isolation**: All queries are scoped to the authenticated user
- **Score algorithm**: Uses a diminishing penalty curve so the first issues matter most (avoids scores clustering at 0 for very broken sites)

### Production Considerations

- **Database**: SQLite works for small deployments; migrate to PostgreSQL for production scale
- **Migrations**: Add Alembic for schema migrations
- **Task queue**: Replace FastAPI background tasks with Celery + Redis for distributed scanning
- **Rate limiting**: Not yet implemented — add before public launch
- **HTTPS**: Set `BASE_URL` to an `https://` address and terminate TLS at the reverse proxy
- **Monitoring**: Add structured logging and health check endpoints

---

## Security

- Passwords hashed with bcrypt (random salt per user)
- JWT tokens signed with HS256; configurable secret key
- SQL injection protection via SQLAlchemy ORM (parameterized queries)
- HTML escaping in frontend via `esc()` helper
- Stripe webhook signature verification
- Bearer token auth (not cookies) — resistant to CSRF attacks
- User input validated with Pydantic models

---

## License

Proprietary. All rights reserved.
