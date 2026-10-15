from datetime import timedelta
from unittest.mock import patch

from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from routing.tomtom import RoutingError
from routing.weather import WeatherError

URL = '/api/routes/analyze/'


def valid_body(**overrides):
    body = {
        'origin': {'lat': 41.8781, 'lon': -87.6298},
        'destination': {'lat': 41.5868, 'lon': -93.6250},
        'departure_time': (timezone.now() + timedelta(hours=1)).isoformat(),
        'load_weight_lb': 35_000,
        'checkpoint_interval_miles': 25,
    }
    body.update(overrides)
    return body


class ValidationTests(SimpleTestCase):
    def post(self, body):
        return APIClient().post(URL, body, format='json')

    def assert_invalid(self, field, **overrides):
        response = self.post(valid_body(**overrides))
        self.assertEqual(response.status_code, 400)
        self.assertIn(field, response.json())

    def test_missing_fields(self):
        response = self.post({})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {
            'origin', 'destination', 'departure_time', 'load_weight_lb', 'checkpoint_interval_miles',
        })

    def test_coordinates_out_of_range(self):
        self.assert_invalid('origin', origin={'lat': 91, 'lon': 0})
        self.assert_invalid('destination', destination={'lat': 0, 'lon': -181})

    def test_coordinates_not_finite(self):
        self.assert_invalid('origin', origin={'lat': 'NaN', 'lon': 0})

    def test_interval_must_be_10_25_or_50(self):
        self.assert_invalid('checkpoint_interval_miles', checkpoint_interval_miles=20)

    def test_load_weight_range(self):
        self.assert_invalid('load_weight_lb', load_weight_lb=-1)
        self.assert_invalid('load_weight_lb', load_weight_lb=80_001)

    def test_departure_window(self):
        self.assert_invalid('departure_time', departure_time='not a date')
        self.assert_invalid('departure_time', departure_time=(timezone.now() - timedelta(hours=2)).isoformat())
        self.assert_invalid('departure_time', departure_time=(timezone.now() + timedelta(days=8)).isoformat())

    def test_same_origin_and_destination(self):
        self.assert_invalid('non_field_errors', destination={'lat': 41.8781, 'lon': -87.6298})

    def test_get_not_allowed(self):
        self.assertEqual(APIClient().get(URL).status_code, 405)


@patch('routing.views.analyze_routes')
class AnalyzeViewTests(SimpleTestCase):
    def post(self, body):
        return APIClient().post(URL, body, format='json')

    def test_passes_validated_input(self, analyze_routes):
        analyze_routes.return_value = {'departure_time': None, 'recommended_route_id': None, 'routes': []}
        body = valid_body(checkpoint_interval_miles='50')

        self.post(body)

        kwargs = analyze_routes.call_args.kwargs
        self.assertEqual(kwargs['origin'], (41.8781, -87.6298))
        self.assertEqual(kwargs['interval_miles'], 50)
        self.assertEqual(kwargs['load_lb'], 35_000)
        self.assertEqual(kwargs['departure'], timezone.datetime.fromisoformat(body['departure_time']))
        start = kwargs['forecast_start']
        self.assertEqual((start.minute, start.second, start.microsecond), (0, 0, 0))
        self.assertLessEqual(timezone.now() - start, timedelta(hours=1))

    def test_routing_failure_is_502(self, analyze_routes):
        analyze_routes.side_effect = RoutingError('TomTom rate limit reached. Try again later.')

        response = self.post(valid_body())

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {'detail': 'TomTom rate limit reached. Try again later.'})

    def test_weather_failure_is_502(self, analyze_routes):
        analyze_routes.side_effect = WeatherError('Could not reach Open-Meteo: timed out')

        self.assertEqual(self.post(valid_body()).status_code, 502)


class ResponseStructureTests(SimpleTestCase):
    @patch('routing.analysis.get_forecasts')
    @patch('routing.analysis.get_routes')
    def test_json_shape(self, get_routes, get_forecasts):
        get_routes.return_value = [{'id': 1, 'distance_miles': 30.0, 'duration_seconds': 1800,
                                    'geometry': [[41.0, -87.0], [41.4, -87.0]]}]
        get_forecasts.return_value = [{}, {}, {}]  # no forecast hours at all

        response = APIClient().post(URL, valid_body(), format='json')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(set(data), {
            'departure_time', 'forecast_start', 'recommended_route_id', 'routes',
            'load_weight_lb', 'checkpoint_interval_miles',
        })
        route = data['routes'][0]
        self.assertEqual(set(route), {
            'id', 'rank', 'distance_miles', 'duration_seconds', 'arrival_time', 'geometry', 'checkpoints',
            'risk_miles', 'unknown_miles', 'average_risk', 'no_travel',
        })
        self.assertEqual(set(route['risk_miles']), {'LOW', 'MODERATE', 'HIGH', 'SEVERE', 'NO_TRAVEL'})
        self.assertEqual(set(route['checkpoints'][0]), {
            'lat', 'lon', 'distance_miles', 'eta', 'weather', 'risk', 'path', 'hourly',
        })
        hourly = route['checkpoints'][0]['hourly']
        self.assertEqual(set(hourly), {'risk', 'wind_speed_mph', 'wind_gust_mph', 'precipitation_in', 'snowfall_in'})
        self.assertTrue(all(len(series) == 49 and set(series) == {None} for series in hourly.values()))
        self.assertIsInstance(route['checkpoints'][0]['eta'], str)
        # No data means unknown, never invented Low weather.
        self.assertEqual([c['risk'] for c in route['checkpoints']], [None, None, None])
        self.assertEqual(route['unknown_miles'], 30)
        self.assertIsNone(route['average_risk'])


@patch('routing.views.geocode')
class GeocodeViewTests(SimpleTestCase):
    def get(self, q):
        return APIClient().get('/api/geocode/', {'q': q})

    def test_returns_place(self, geocode):
        geocode.return_value = {'label': 'Chicago, IL, USA', 'lat': 41.8781, 'lon': -87.6298}

        response = self.get(' Chicago ')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['label'], 'Chicago, IL, USA')
        geocode.assert_called_once_with('Chicago')

    def test_blank_or_too_long_query(self, geocode):
        self.assertEqual(self.get('').status_code, 400)
        self.assertEqual(self.get('x' * 201).status_code, 400)
        geocode.assert_not_called()

    def test_not_found_is_404(self, geocode):
        geocode.return_value = None

        self.assertEqual(self.get('zzzz').status_code, 404)

    def test_service_error_is_502(self, geocode):
        geocode.side_effect = RoutingError('TomTom rate limit reached. Try again later.')

        self.assertEqual(self.get('Chicago').status_code, 502)
