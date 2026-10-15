"""Weather risk classification, route aggregation, and route ranking.

Boundary convention: where the assessment's bands share an endpoint
(rain 0.25 and 0.50, snow 1.0 and 2.0, and the integer wind bands), the
value belongs to the higher band, i.e. each band includes its lower bound.
The only upper bounds that are inclusive are the ones the assessment states
explicitly: No Travel is "> 1.00" in/hr rain and "> 3.0" in/hr snow, so
exactly 1.00 and 3.0 are Severe.

Combining hazards: a checkpoint's risk is the worst of its wind (after load
adjustment), rain, and snow levels. Hazards are not added together.
"""
from enum import IntEnum


class Risk(IntEnum):
    LOW = 1
    MODERATE = 2
    HIGH = 3
    SEVERE = 4
    NO_TRAVEL = 5


def wind_risk(mph):
    if mph < 25:
        return Risk.LOW
    if mph < 35:
        return Risk.MODERATE
    if mph < 45:
        return Risk.HIGH
    if mph < 55:
        return Risk.SEVERE
    return Risk.NO_TRAVEL


def rain_risk(inches_per_hour):
    if inches_per_hour < 0.10:
        return Risk.LOW
    if inches_per_hour < 0.25:
        return Risk.MODERATE
    if inches_per_hour < 0.50:
        return Risk.HIGH
    if inches_per_hour <= 1.00:
        return Risk.SEVERE
    return Risk.NO_TRAVEL


def snow_risk(inches_per_hour):
    if inches_per_hour < 0.5:
        return Risk.LOW
    if inches_per_hour < 1.0:
        return Risk.MODERATE
    if inches_per_hour < 2.0:
        return Risk.HIGH
    if inches_per_hour <= 3.0:
        return Risk.SEVERE
    return Risk.NO_TRAVEL


def wind_risk_for_load(mph, load_lb):
    """Wind risk raised for heavy loads; >= 55 mph is already No Travel for any load."""
    risk = wind_risk(mph)
    if risk == Risk.SEVERE and load_lb > 30_000:
        return Risk.NO_TRAVEL
    if risk == Risk.HIGH and load_lb > 40_000:
        return Risk.SEVERE
    return risk


def checkpoint_risk(weather, load_lb):
    """Worst hazard at a checkpoint, or None when no weather data is available.

    `weather` is an hourly forecast from routing.weather (or None). Precipitation
    is used as the rain rate; it includes melted snow, but that water equivalent
    never classifies higher than the snowfall itself, so taking the worst hazard
    does not inflate the result.
    """
    if not weather:
        return None
    wind = weather.get('wind_speed_mph')
    rain = weather.get('precipitation_in')
    snow = weather.get('snowfall_in')
    risks = []
    if wind is not None:
        risks.append(wind_risk_for_load(wind, load_lb))
    if rain is not None:
        risks.append(rain_risk(rain))
    if snow is not None:
        risks.append(snow_risk(snow))
    return max(risks, default=None)


def summarize_route(segments):
    """Aggregate (miles, risk) segments into risk miles and mile-weighted average risk.

    Segments with unknown risk (None) are reported as unknown_miles and
    excluded from the average, never treated as Low.
    """
    miles = {risk: 0.0 for risk in Risk}
    unknown_miles = 0.0
    for segment_miles, risk in segments:
        if risk is None:
            unknown_miles += segment_miles
        else:
            miles[risk] += segment_miles
    known_miles = sum(miles.values())
    average = sum(risk * m for risk, m in miles.items()) / known_miles if known_miles else None
    return {
        'risk_miles': {risk.name: m for risk, m in miles.items()},
        'unknown_miles': unknown_miles,
        'average_risk': average,
        'no_travel': miles[Risk.NO_TRAVEL] > 0,
    }


def rank_routes(routes):
    """Sort routes best first. Each route needs 'id', 'duration_seconds', and summarize_route() fields.

    Routes with any No Travel segment always rank after travelable ones. Within
    each group the assessment's order applies: fewest Severe miles, fewest High
    miles, lowest average risk, shortest travel time. Route id breaks exact ties.
    Values are rounded so floating-point noise cannot reorder equal routes.
    """
    def key(route):
        average = route['average_risk']
        return (
            route['no_travel'],
            round(route['risk_miles']['SEVERE'], 6),
            round(route['risk_miles']['HIGH'], 6),
            float('inf') if average is None else round(average, 6),
            route['duration_seconds'],
            route['id'],
        )
    return sorted(routes, key=key)
