from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from routing.tomtom import RoutingError, geocode, get_routes

ORIGIN = (41.8781, -87.6298)
DESTINATION = (41.5868, -93.6250)


def response(status, payload):
    return Mock(status_code=status, json=Mock(return_value=payload))


def route(meters, seconds, *legs):
    return {
        'summary': {'lengthInMeters': meters, 'travelTimeInSeconds': seconds},
        'legs': [{'points': [{'latitude': lat, 'longitude': lon} for lat, lon in leg]} for leg in legs],
    }


CHICAGO_DES_MOINES = [(41.8781, -87.6298), (41.5868, -93.625)]


@override_settings(TOMTOM_API_KEY='test-key')
@patch('routing.tomtom.requests.get')
class GetRoutesTests(SimpleTestCase):
    def test_normalizes_routes(self, get):
        get.return_value = response(200, {'routes': [
            route(1609.344, 60, CHICAGO_DES_MOINES),
            route(3218.688, 120, [(41.8781, -87.6298), (42.0, -90.0)], [(42.0, -90.0), (41.5868, -93.625)]),
        ]})

        routes = get_routes(ORIGIN, DESTINATION)

        self.assertEqual([r['id'] for r in routes], [1, 2])
        self.assertAlmostEqual(routes[0]['distance_miles'], 1.0)
        self.assertEqual(routes[1]['duration_seconds'], 120)
        self.assertEqual(routes[0]['geometry'], [[41.8781, -87.6298], [41.5868, -93.625]])
        self.assertEqual(len(routes[1]['geometry']), 4)  # points from every leg, in order

    def test_requests_truck_route_with_two_alternatives(self, get):
        get.return_value = response(200, {'routes': [route(1, 1, CHICAGO_DES_MOINES)]})

        get_routes(ORIGIN, DESTINATION)

        url, params = get.call_args.args[0], get.call_args.kwargs['params']
        self.assertIn('/calculateRoute/41.8781,-87.6298:41.5868,-93.625/json', url)
        self.assertEqual(params['travelMode'], 'truck')
        self.assertEqual(params['maxAlternatives'], 2)
        self.assertEqual(params['key'], 'test-key')

    def test_fewer_than_three_routes(self, get):
        get.return_value = response(200, {'routes': [route(1000, 60, CHICAGO_DES_MOINES)]})

        self.assertEqual(len(get_routes(ORIGIN, DESTINATION)), 1)

    def test_caps_at_three_routes(self, get):
        get.return_value = response(200, {'routes': [route(1, 1, CHICAGO_DES_MOINES)] * 4})

        self.assertEqual(len(get_routes(ORIGIN, DESTINATION)), 3)

    def test_no_routes_is_error(self, get):
        get.return_value = response(200, {'routes': []})

        with self.assertRaisesMessage(RoutingError, 'no routes'):
            get_routes(ORIGIN, DESTINATION)

    def test_no_route_found_reports_tomtom_message(self, get):
        get.return_value = response(400, {'formatVersion': '0.0.12', 'detailedError': {
            'message': 'Engine error while executing route request: NO_ROUTE_FOUND: No valid route found',
            'code': 'NO_ROUTE_FOUND'}})

        with self.assertRaisesMessage(RoutingError, 'TomTom error (400): Engine error while executing route request: NO_ROUTE_FOUND'):
            get_routes(ORIGIN, DESTINATION)

    def test_rejected_key_or_daily_limit(self, get):
        for status in (401, 403):
            get.return_value = response(status, {'detailedError': {'code': 'Unauthorized', 'message': '...'}})
            with self.subTest(status=status), self.assertRaisesMessage(RoutingError, 'rejected the API key'):
                get_routes(ORIGIN, DESTINATION)

    def test_rate_limited(self, get):
        get.return_value = Mock(status_code=429, json=Mock(side_effect=ValueError))

        with self.assertRaisesMessage(RoutingError, 'rate limit'):
            get_routes(ORIGIN, DESTINATION)

    def test_body_not_json(self, get):
        get.return_value = Mock(status_code=200, json=Mock(side_effect=ValueError('Expecting value')))

        with self.assertRaisesMessage(RoutingError, 'invalid response'):
            get_routes(ORIGIN, DESTINATION)

    def test_network_failure_does_not_leak_key(self, get):
        get.side_effect = requests.ConnectionError('Max retries exceeded with url: /routing?key=test-key')

        with self.assertRaises(RoutingError) as ctx:
            get_routes(ORIGIN, DESTINATION)
        self.assertIn('Could not reach TomTom', str(ctx.exception))
        self.assertNotIn('test-key', str(ctx.exception))

    @override_settings(TOMTOM_API_KEY='')
    def test_missing_api_key(self, get):
        with self.assertRaisesMessage(RoutingError, 'TOMTOM_API_KEY is not configured'):
            get_routes(ORIGIN, DESTINATION)
        get.assert_not_called()


@override_settings(TOMTOM_API_KEY='test-key')
@patch('routing.tomtom.requests.get')
class GeocodeTests(SimpleTestCase):
    def test_returns_best_match(self, get):
        get.return_value = response(200, {'results': [{
            'type': 'Geography', 'address': {'freeformAddress': 'Chicago, IL'},
            'position': {'lat': 41.8781, 'lon': -87.6298},
        }]})

        self.assertEqual(geocode('Chicago'), {'label': 'Chicago, IL', 'lat': 41.8781, 'lon': -87.6298})
        self.assertEqual(get.call_args.kwargs['params'], {'limit': 1, 'key': 'test-key'})

    def test_query_is_url_encoded_in_path(self, get):
        get.return_value = response(200, {'results': []})

        geocode('Des Moines, IA/US?')

        self.assertTrue(get.call_args.args[0].endswith('/geocode/Des%20Moines%2C%20IA%2FUS%3F.json'))

    def test_no_match_is_none(self, get):
        get.return_value = response(200, {'results': []})

        self.assertIsNone(geocode('asdfghjkl'))

    def test_api_error(self, get):
        get.return_value = response(401, {'detailedError': {'code': 'Unauthorized', 'message': '...'}})

        with self.assertRaisesMessage(RoutingError, 'rejected the API key'):
            geocode('Chicago')
