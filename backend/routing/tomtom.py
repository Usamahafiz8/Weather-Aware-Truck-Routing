import requests
from django.conf import settings

ROUTE_URL = 'https://api.tomtom.com/routing/1/calculateRoute/{origin}:{destination}/json'
GEOCODE_URL = 'https://api.tomtom.com/search/2/geocode/{query}.json'
METERS_PER_MILE = 1609.344
MAX_ROUTES = 3
TIMEOUT_SECONDS = 30


class RoutingError(Exception):
    pass


def get_routes(origin, destination):
    """Return up to three truck routes between two (lat, lon) points.

    Each route: {'id', 'distance_miles', 'duration_seconds', 'geometry'},
    where geometry is a list of [lat, lon] pairs.
    """
    url = ROUTE_URL.format(origin=f'{origin[0]},{origin[1]}', destination=f'{destination[0]},{destination[1]}')
    # traffic=false: durations don't depend on live traffic at request time.
    data = _get(url, {'travelMode': 'truck', 'maxAlternatives': MAX_ROUTES - 1, 'traffic': 'false'})
    routes = data.get('routes') or []
    if not routes:
        raise RoutingError('TomTom returned no routes.')
    return [_normalize(i, route) for i, route in enumerate(routes[:MAX_ROUTES], start=1)]


def geocode(text):
    """Best match for a place name as {'label', 'lat', 'lon'}, or None if nothing matches."""
    data = _get(GEOCODE_URL.format(query=requests.utils.quote(text, safe='')), {'limit': 1})
    results = data.get('results') or []
    if not results:
        return None
    best = results[0]
    return {'label': best['address']['freeformAddress'], 'lat': best['position']['lat'], 'lon': best['position']['lon']}


def _normalize(route_id, route):
    summary = route['summary']
    return {
        'id': route_id,
        'distance_miles': summary['lengthInMeters'] / METERS_PER_MILE,
        'duration_seconds': summary['travelTimeInSeconds'],
        'geometry': [[p['latitude'], p['longitude']] for leg in route['legs'] for p in leg['points']],
    }


def _get(url, params):
    if not settings.TOMTOM_API_KEY:
        raise RoutingError('TOMTOM_API_KEY is not configured.')
    try:
        response = requests.get(url, params={**params, 'key': settings.TOMTOM_API_KEY}, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        # The exception text contains the request URL, which includes the API key, so it is not passed on.
        raise RoutingError('Could not reach TomTom. Try again later.') from exc

    if response.status_code in (401, 403):
        raise RoutingError('TomTom rejected the API key or the daily free limit was reached.')
    if response.status_code == 429:
        raise RoutingError('TomTom rate limit reached. Try again later.')
    try:
        data = response.json()
    except ValueError as exc:
        raise RoutingError(f'TomTom returned an invalid response (HTTP {response.status_code}).') from exc
    if response.status_code == 200:
        return data
    detail = (data.get('detailedError') or {}).get('message') if isinstance(data, dict) else None
    raise RoutingError(f'TomTom error ({response.status_code}): {detail or "no details"}')
