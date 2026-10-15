"""Builds the route analysis: routes -> checkpoints -> arrival-time weather -> risk -> ranking.

ETA assumption: the truck covers each route at a constant average speed
(TomTom total duration / TomTom total distance). Durations are requested
without live traffic; rest breaks are not modelled.

Risk miles: each checkpoint represents the stretch of road closer to it than
to any neighbouring checkpoint, so the covered miles add up to the route
distance and a checkpoint without weather counts as unknown miles. That
stretch is returned as the checkpoint's `path` for drawing.

Forecast heatmap: separately from the arrival-time analysis, every checkpoint
also gets its forecast for each hour from `forecast_start` to +48 h, so the
map can show conditions along all routes at one moment. It reuses the
forecasts already fetched for the arrival-time analysis.
"""
import bisect
import math
from datetime import timedelta

from routing.tomtom import get_routes
from routing.risk import checkpoint_risk, rank_routes, summarize_route
from routing.weather import get_forecasts, weather_at

EARTH_RADIUS_MILES = 3958.8
HEATMAP_HOURS = 48
# Output precision for the hourly series; risk is classified on unrounded values.
HOURLY_DIGITS = {'wind_speed_mph': 1, 'wind_gust_mph': 1, 'precipitation_in': 3, 'snowfall_in': 2}


def analyze_routes(origin, destination, departure, load_lb, interval_miles, forecast_start):
    routes = get_routes(origin, destination)
    for route in routes:
        route['checkpoints'] = place_checkpoints(route, interval_miles, departure)

    points = [(c['lat'], c['lon']) for route in routes for c in route['checkpoints']]
    forecasts = iter(get_forecasts(points))

    for route in routes:
        checkpoints = route['checkpoints']
        risks = []
        for checkpoint in checkpoints:
            forecast = next(forecasts)
            checkpoint['weather'] = weather_at(forecast, checkpoint['eta'])
            risk = checkpoint_risk(checkpoint['weather'], load_lb)
            checkpoint['risk'] = risk.name if risk else None
            checkpoint['hourly'] = hourly_series(forecast, forecast_start, load_lb)
            risks.append(risk)
        route.update(summarize_route(zip(covered_miles([c['distance_miles'] for c in checkpoints]), risks)))
        route['arrival_time'] = departure + timedelta(seconds=route['duration_seconds'])

    ranked = rank_routes(routes)
    for rank, route in enumerate(ranked, start=1):
        route['rank'] = rank
    best = ranked[0]
    return {
        'departure_time': departure,
        'forecast_start': forecast_start,
        'recommended_route_id': None if best['no_travel'] else best['id'],
        'routes': ranked,
    }


def hourly_series(forecast, start, load_lb):
    """Risk and weather for each hour from `start` to +48 h; None where the forecast has no data."""
    series = {'risk': [], **{field: [] for field in HOURLY_DIGITS}}
    for hour in range(HEATMAP_HOURS + 1):
        weather = weather_at(forecast, start + timedelta(hours=hour))
        risk = checkpoint_risk(weather, load_lb)
        series['risk'].append(risk.name if risk else None)
        for field, digits in HOURLY_DIGITS.items():
            value = weather.get(field) if weather else None
            series[field].append(None if value is None else round(value, digits))
    return series


def place_checkpoints(route, interval_miles, departure):
    """Checkpoints every `interval_miles` along the route geometry, plus the destination.

    Positions are found along the geometry; distances and ETAs are scaled to
    the route's reported distance and duration so the last checkpoint matches them.
    """
    geometry = route['geometry']
    total_miles = route['distance_miles']
    cumulative = _cumulative_miles(geometry)
    scale = cumulative[-1] / total_miles if total_miles else 0

    # The tolerance stops float noise (e.g. 50.0000001 mi) adding a duplicate checkpoint at the destination.
    marks = [i * interval_miles for i in range(math.ceil(total_miles / interval_miles - 1e-6))] + [total_miles]
    checkpoints = []
    for miles, (start, end) in zip(marks, _stretches(marks)):
        fraction = miles / total_miles if total_miles else 0
        lat, lon = _point_at(geometry, cumulative, miles * scale)
        checkpoints.append({
            'lat': lat,
            'lon': lon,
            'distance_miles': miles,
            'eta': departure + timedelta(seconds=route['duration_seconds'] * fraction),
            'path': _slice(geometry, cumulative, start * scale, end * scale),
        })
    return checkpoints


def covered_miles(distances):
    """Miles of road nearest to each checkpoint, given checkpoint distances along the route."""
    return [end - start for start, end in _stretches(distances)]


def _stretches(distances):
    """(start, end) of the road nearest to each checkpoint: midway to its neighbours."""
    if len(distances) == 1:
        return [(distances[0], distances[0])]
    edges = [distances[0]] + [(a + b) / 2 for a, b in zip(distances, distances[1:])] + [distances[-1]]
    return list(zip(edges, edges[1:]))


def _haversine_miles(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(h))


def _cumulative_miles(geometry):
    totals = [0.0]
    for a, b in zip(geometry, geometry[1:]):
        totals.append(totals[-1] + _haversine_miles(a, b))
    return totals


def _point_at(geometry, cumulative, target_miles):
    i = bisect.bisect_left(cumulative, target_miles)
    if i == 0:
        return geometry[0]
    if i == len(cumulative):
        return geometry[-1]
    (lat1, lon1), (lat2, lon2) = geometry[i - 1], geometry[i]
    t = (target_miles - cumulative[i - 1]) / (cumulative[i] - cumulative[i - 1])
    return [lat1 + (lat2 - lat1) * t, lon1 + (lon2 - lon1) * t]


def _slice(geometry, cumulative, start_miles, end_miles):
    """The part of the geometry between two distances along it."""
    inner = geometry[bisect.bisect_right(cumulative, start_miles):bisect.bisect_left(cumulative, end_miles)]
    return [_point_at(geometry, cumulative, start_miles), *inner, _point_at(geometry, cumulative, end_miles)]
