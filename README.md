# Weather-Aware Truck Routing

A React + Django app that helps a truck driver choose the safest route based on weather, load weight, and travel time.
It compares up to three truck routes using the forecast for when the truck reaches each checkpoint, and shows a
0–48 hour weather heatmap along the route corridor.

## Features

- Origin/destination search (place name → coordinates), departure time, load weight (0–80,000 lb), and checkpoint
  spacing of 10, 25, or 50 miles.
- Up to three truck route alternatives from the TomTom Routing API.
- Checkpoints along each route with an ETA, plus the destination.
- Weather at each checkpoint taken from the forecast hour of the truck's arrival (Open-Meteo).
- Wind, rain, and snow risk levels with the load-weight rules, combined per checkpoint and totalled per route.
- Routes ranked by the required priority order, with the recommended route highlighted.
- Map with color-coded routes and checkpoints, route cards with risk-mile summaries, a checkpoint detail panel,
  and a 0–48 hour forecast slider that recolors the map without extra requests.

## Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript 6, Vite 8, Leaflet / React Leaflet (OpenStreetMap tiles), oxlint |
| Backend | Python, Django 6.1, Django REST Framework 3.18, django-cors-headers, requests, python-dotenv, gunicorn |
| External APIs | TomTom Routing + Search (free key required), Open-Meteo Forecast (no key) |

The backend is stateless: no database, authentication, or sessions.

## Project structure

```
backend/
  config/            Django settings, URLs, WSGI/ASGI entry points
  routing/
    tomtom.py        Truck routes (travelMode=truck, up to 2 alternatives) and geocoding; API key stays on the server
    weather.py       Open-Meteo hourly wind, gusts, precipitation, snowfall; metric → mph / inches; missing values stay null
    risk.py          Thresholds, load rules, worst-hazard combination, route totals, ranking
    analysis.py      Checkpoint placement, ETAs, arrival-time weather, 0–48 h series, final response
    views.py         Input validation and the two endpoints
    test_*.py        Unit tests (external APIs mocked)
  requirements.txt
  .env.example
frontend/
  src/
    api.ts           Typed API client
    App.tsx          Page state and layout
    TripForm.tsx, RouteCards.tsx, RouteMap.tsx, CheckpointPanel.tsx, ForecastControls.tsx
    format.ts        Risk colors/labels and number/date formatting
  package.json, package-lock.json
  .env.example
```

### API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/geocode/?q=Chicago, IL` | Best match as `{label, lat, lon}`; 404 if nothing matches |
| POST | `/api/routes/analyze/` | Body: `origin {lat, lon}`, `destination {lat, lon}`, `departure_time` (ISO 8601), `load_weight_lb`, `checkpoint_interval_miles` (10/25/50) |

Invalid input returns HTTP 400 with field errors. TomTom or Open-Meteo failures return HTTP 502 with a readable
`detail` message.

```
React                                             Django REST Framework
  form → GET  /api/geocode/?q=…        ───────►  TomTom Search: place name → coordinates
       → POST /api/routes/analyze/     ───────►  1. TomTom Routing: up to 3 truck routes
  route cards, map, checkpoint panel,            2. checkpoints every 10/25/50 mi + destination, ETA for each
  forecast slider (no extra requests)            3. Open-Meteo: hourly forecast for every checkpoint (one batched call)
                                                 4. risk per checkpoint → route totals → ranking
```

### Risk and ranking rules

- Wind (sustained mph): Low <25, Moderate 25–34, High 35–44, Severe 45–54, No Travel ≥55.
- Rain (in/hr): Low <0.10, Moderate 0.10–0.25, High 0.25–0.50, Severe 0.50–1.00, No Travel >1.00.
- Snow (in/hr): Low <0.5, Moderate 0.5–1.0, High 1.0–2.0, Severe 2.0–3.0, No Travel >3.0.
- Shared band edges (e.g. rain 0.25) belong to the higher band. Exactly 1.00 in/hr rain and 3.0 in/hr snow are Severe.
- Load: 45–54 mph with >30,000 lb → No Travel; 35–44 mph with >40,000 lb → Severe.
- A checkpoint's risk is its worst hazard. Each checkpoint covers the road halfway to its neighbours ("risk miles").
- Ranking: fewest Severe miles → fewest High miles → lowest average risk (mile-weighted, Low=1 … No Travel=5) →
  shortest travel time. Routes with any No Travel miles rank last and are never recommended.

## Prerequisites

- Python 3.12 or newer (required by Django 6.1; tested with 3.14.6)
- Node.js 20.19+ or 22.12+ (required by Vite 8; tested with 24.18.1) and npm
- A free TomTom API key. Open-Meteo needs no key.

## Environment variables

| Where | Variable | Local example | Production |
| --- | --- | --- | --- |
| `backend/.env` | `DJANGO_SECRET_KEY` | any generated key (required) | a new generated key |
| | `DJANGO_DEBUG` | `True` | `False` (default if unset) |
| | `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | backend host, e.g. `my-api.onrender.com` |
| | `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | frontend URL, e.g. `https://my-app.vercel.app` (no trailing slash) |
| | `TOMTOM_API_KEY` | `your-tomtom-api-key` | your key |
| `frontend/.env` | `VITE_API_BASE_URL` | `http://localhost:8000` (default if unset) | backend URL, e.g. `https://my-api.onrender.com` |

`.env` files are git-ignored; commit only the `.env.example` files. `VITE_` variables are public (bundled into the
browser), so never put secrets in them.

## Configuring API credentials

1. TomTom: register at [developer.tomtom.com](https://developer.tomtom.com), open Dashboard → Keys, and copy the
   default key (it includes the Routing and Search APIs). Put it in `backend/.env` as `TOMTOM_API_KEY`.
2. Open-Meteo: nothing to configure; the backend calls `https://api.open-meteo.com/v1/forecast` directly.

Generate a Django secret key with:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Run the backend locally

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env — then set DJANGO_SECRET_KEY and TOMTOM_API_KEY
python manage.py runserver      # http://localhost:8000
```

There are no migrations to run (no database). Check it with `http://localhost:8000/api/geocode/?q=Chicago`.

## Run the frontend locally

In a second terminal:

```bash
cd frontend
npm install
copy .env.example .env          # macOS/Linux: cp .env.example .env (optional; defaults to http://localhost:8000)
npm run dev                     # http://localhost:5173
```

## Tests and build

```bash
cd backend
python manage.py test routing   # 92 unit tests, external APIs mocked

cd frontend
npm run build                   # type check (tsc -b) and production build into dist/
npm run lint                    # oxlint
npm run preview                 # serve the production build locally
```

The tests cover every threshold edge, the load rules, each ranking tie-breaker, No Travel handling, checkpoint
placement, ETAs, missing forecast data, time zones, input validation, and API error handling.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| `KeyError: 'DJANGO_SECRET_KEY'` on startup | `backend/.env` is missing or has no secret key. Copy `.env.example` and set it. |
| "TOMTOM_API_KEY is not configured." | Add the key to `backend/.env` and restart `runserver`. |
| "TomTom rejected the API key or the daily free limit was reached." | Check the key in the TomTom dashboard, or wait for the daily quota to reset. |
| "Open-Meteo rate limit reached." | Long trips at 10-mile spacing request many points. Wait a minute or use 25/50-mile spacing. |
| Browser shows a CORS or network error | Backend not running, `VITE_API_BASE_URL` points elsewhere, or the frontend origin is missing from `CORS_ALLOWED_ORIGINS`. |
| HTTP 400 "Bad Request" from Django in production | Backend host is missing from `DJANGO_ALLOWED_HOSTS`. |
| `No location found for "…"` | Use "City, State" (e.g. "Springfield, IL"). |
| "Departure time cannot be in the past" / "must be within 7 days" | Departure must be from 1 hour ago up to the 7-day forecast window. |
| Vite fails to start with an engine error | Upgrade Node.js to 20.19+ or 22.12+. |
| Frontend still calls the old backend after a change | `VITE_API_BASE_URL` is read at build time: restart `npm run dev` or rebuild. |

## Deployment

### Backend on Render (free Python web service)

1. New → Web Service → connect the repository.
2. Root directory: `backend`. Runtime: Python.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn config.wsgi:application --bind 0.0.0.0:$PORT`
5. Environment: the backend variables above (with `DJANGO_DEBUG=False`), plus `PYTHON_VERSION=3.14.6`.
6. Check it: `https://<backend>/api/geocode/?q=Chicago` should return JSON.

### Frontend on Vercel

1. Add New → Project → import the repository.
2. Root directory: `frontend`. Framework preset: Vite (build `npm run build`, output `dist`).
3. Environment: `VITE_API_BASE_URL=https://<backend>`. It is read at build time, so redeploy after changing it.
4. Put the Vercel URL in the backend's `CORS_ALLOWED_ORIGINS` and redeploy the backend.

The app is a single page, so no rewrites are needed. Render and Vercel both serve HTTPS.

## Known limitations

- ETAs assume a constant average speed (route duration ÷ distance). Rest breaks and live traffic are not modelled.
- Weather at a checkpoint uses the forecast hour nearest the ETA. Arrivals beyond the 7-day forecast show "No data"
  and count as unknown miles, never as Low.
- Precipitation is used as the rain rate. It includes melted snow, but snowfall is also classified on its own.
- Wind gusts are displayed but not classified; the rules use sustained wind.
- The heatmap slider counts hours from the start of the current hour, independent of departure time.
- Geocoding uses the best match. Type "City, State" to avoid ambiguity.
- Free-tier limits: TomTom allows 2,500 requests/day. Open-Meteo counts each checkpoint as a call, so long trips at
  10-mile spacing can hit its per-minute limit; the app then shows a clear error.
- Render's free tier sleeps when idle, so the first request after a break can take about a minute.
- There are no automated frontend tests; the frontend is checked by the TypeScript build and lint.
