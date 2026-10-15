import requests

FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
FORECAST_DAYS = 7
LOCATIONS_PER_REQUEST = 100
TIMEOUT_SECONDS = 30

# Open-Meteo variable -> (metric unit we request, output field, factor to imperial).
VARIABLES = {
    'wind_speed_10m': ('km/h', 'wind_speed_mph', 1 / 1.609344),
    'wind_gusts_10m': ('km/h', 'wind_gust_mph', 1 / 1.609344),
    'precipitation': ('mm', 'precipitation_in', 1 / 25.4),
    'snowfall': ('cm', 'snowfall_in', 1 / 2.54),
}


class WeatherError(Exception):
    pass


def get_forecasts(points):
    """Return one hourly forecast per (lat, lon) point, in the same order.

    A forecast maps a UTC unix timestamp (on the hour) to
    {'wind_speed_mph', 'wind_gust_mph', 'precipitation_in', 'snowfall_in'}.
    Values Open-Meteo leaves empty stay None.
    """
    forecasts = []
    for start in range(0, len(points), LOCATIONS_PER_REQUEST):
        forecasts += _fetch(points[start:start + LOCATIONS_PER_REQUEST])
    return forecasts


def weather_at(forecast, when):
    """Weather for the hour nearest to `when`, or None if outside the forecast."""
    if when.tzinfo is None:
        raise ValueError('when must be timezone-aware')
    return forecast.get(round(when.timestamp() / 3600) * 3600)


def _fetch(points):
    params = {
        'latitude': ','.join(str(lat) for lat, _ in points),
        'longitude': ','.join(str(lon) for _, lon in points),
        'hourly': ','.join(VARIABLES),
        'wind_speed_unit': 'kmh',
        'precipitation_unit': 'mm',
        'timezone': 'GMT',
        'timeformat': 'unixtime',
        'forecast_days': FORECAST_DAYS,
    }
    try:
        response = requests.get(FORECAST_URL, params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise WeatherError(f'Could not reach Open-Meteo: {exc}') from exc

    if response.status_code == 429:
        raise WeatherError('Open-Meteo rate limit reached. Try again later.')
    if response.status_code != 200:
        try:
            reason = response.json().get('reason')
        except ValueError:
            reason = None
        raise WeatherError(f'Open-Meteo error ({response.status_code}): {reason or "no details"}')

    try:
        results = response.json()
    except ValueError as exc:
        raise WeatherError('Open-Meteo returned an invalid response.') from exc
    if isinstance(results, dict):  # single location returns an object, not a list
        results = [results]
    if len(results) != len(points):
        raise WeatherError('Open-Meteo returned an unexpected number of locations.')
    return [_parse(result) for result in results]


def _parse(result):
    hourly = result.get('hourly') or {}
    units = result.get('hourly_units') or {}
    times = hourly.get('time') or []
    forecast = {timestamp: {} for timestamp in times}

    for name, (unit, field, factor) in VARIABLES.items():
        if units.get(name) != unit:
            raise WeatherError(f'Open-Meteo returned {name} in {units.get(name)!r}, expected {unit!r}.')
        values = hourly.get(name) or []
        for i, timestamp in enumerate(times):
            value = values[i] if i < len(values) else None
            forecast[timestamp][field] = None if value is None else value * factor
    return forecast
