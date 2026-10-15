from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from routing.weather import WeatherError, get_forecasts, weather_at

HOUR = 1792022400  # 2026-10-15 00:00 UTC
UNITS = {'time': 'unixtime', 'wind_speed_10m': 'km/h', 'wind_gusts_10m': 'km/h',
         'precipitation': 'mm', 'snowfall': 'cm'}


def response(status, payload):
    return Mock(status_code=status, json=Mock(return_value=payload))


def location(**overrides):
    hourly = {
        'time': [HOUR, HOUR + 3600],
        'wind_speed_10m': [16.09344, None],
        'wind_gusts_10m': [32.18688, 0.0],
        'precipitation': [25.4, 0.0],
        'snowfall': [2.54, 0.0],
    }
    hourly.update(overrides)
    return {'hourly_units': UNITS, 'hourly': hourly}


@patch('routing.weather.requests.get')
class GetForecastsTests(SimpleTestCase):
    def test_converts_metric_to_imperial(self, get):
        get.return_value = response(200, location())

        hour = get_forecasts([(41.88, -87.63)])[0][HOUR]

        self.assertAlmostEqual(hour['wind_speed_mph'], 10.0)
        self.assertAlmostEqual(hour['wind_gust_mph'], 20.0)
        self.assertAlmostEqual(hour['precipitation_in'], 1.0)
        self.assertAlmostEqual(hour['snowfall_in'], 1.0)

    def test_requests_explicit_units_and_utc(self, get):
        get.return_value = response(200, location())

        get_forecasts([(41.88, -87.63)])

        params = get.call_args.kwargs['params']
        self.assertEqual(params['wind_speed_unit'], 'kmh')
        self.assertEqual(params['precipitation_unit'], 'mm')
        self.assertEqual(params['timezone'], 'GMT')
        self.assertEqual(params['timeformat'], 'unixtime')

    def test_null_values_stay_missing(self, get):
        get.return_value = response(200, location())

        self.assertIsNone(get_forecasts([(41.88, -87.63)])[0][HOUR + 3600]['wind_speed_mph'])

    def test_short_value_array_is_missing_not_invented(self, get):
        get.return_value = response(200, location(snowfall=[2.54]))

        self.assertIsNone(get_forecasts([(41.88, -87.63)])[0][HOUR + 3600]['snowfall_in'])

    def test_multiple_locations_in_one_request(self, get):
        get.return_value = response(200, [location(), location()])

        forecasts = get_forecasts([(41.88, -87.63), (39.74, -104.99)])

        self.assertEqual(len(forecasts), 2)
        self.assertEqual(get.call_args.kwargs['params']['latitude'], '41.88,39.74')

    def test_batches_large_requests(self, get):
        get.side_effect = lambda url, params, timeout: response(
            200, [location()] * len(params['latitude'].split(',')))

        forecasts = get_forecasts([(40.0, -90.0)] * 150)

        self.assertEqual(len(forecasts), 150)
        self.assertEqual(get.call_count, 2)

    def test_location_count_mismatch(self, get):
        get.return_value = response(200, [location()])

        with self.assertRaisesMessage(WeatherError, 'unexpected number of locations'):
            get_forecasts([(41.88, -87.63), (39.74, -104.99)])

    def test_unexpected_units_rejected(self, get):
        payload = location()
        payload['hourly_units'] = {**UNITS, 'snowfall': 'inch'}
        get.return_value = response(200, payload)

        with self.assertRaisesMessage(WeatherError, "expected 'cm'"):
            get_forecasts([(41.88, -87.63)])

    def test_api_error_reason(self, get):
        get.return_value = response(400, {'error': True, 'reason': 'Latitude must be in range of -90 to 90°.'})

        with self.assertRaisesMessage(WeatherError, 'Latitude must be in range'):
            get_forecasts([(200, 0)])

    def test_rate_limited(self, get):
        get.return_value = response(429, {'error': True, 'reason': 'Too many requests'})

        with self.assertRaisesMessage(WeatherError, 'rate limit'):
            get_forecasts([(41.88, -87.63)])

    def test_network_failure(self, get):
        get.side_effect = requests.Timeout('timed out')

        with self.assertRaisesMessage(WeatherError, 'Could not reach Open-Meteo'):
            get_forecasts([(41.88, -87.63)])


class WeatherAtTests(SimpleTestCase):
    forecast = {HOUR: {'wind_speed_mph': 10.0}, HOUR + 3600: {'wind_speed_mph': 20.0}}
    start = datetime.fromtimestamp(HOUR, tz=timezone.utc)

    def test_rounds_to_nearest_hour(self):
        self.assertEqual(weather_at(self.forecast, self.start + timedelta(minutes=29))['wind_speed_mph'], 10.0)
        self.assertEqual(weather_at(self.forecast, self.start + timedelta(minutes=31))['wind_speed_mph'], 20.0)

    def test_other_time_zones_are_compared_in_utc(self):
        chicago = timezone(timedelta(hours=-5))
        when = datetime(2026, 10, 14, 20, 0, tzinfo=chicago)  # 01:00 UTC on Oct 15

        self.assertEqual(weather_at(self.forecast, when)['wind_speed_mph'], 20.0)

    def test_outside_forecast_range_is_none(self):
        self.assertIsNone(weather_at(self.forecast, self.start + timedelta(days=10)))
        self.assertIsNone(weather_at(self.forecast, self.start - timedelta(hours=2)))

    def test_naive_datetime_rejected(self):
        with self.assertRaises(ValueError):
            weather_at(self.forecast, datetime(2026, 10, 15))


@patch('routing.weather.requests.get')
class InvalidSuccessBodyTests(SimpleTestCase):
    def test_body_not_json(self, get):
        get.return_value = Mock(status_code=200, json=Mock(side_effect=ValueError('Expecting value')))

        with self.assertRaisesMessage(WeatherError, 'invalid response'):
            get_forecasts([(41.88, -87.63)])
