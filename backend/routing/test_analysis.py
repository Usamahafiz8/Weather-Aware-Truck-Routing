from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from django.test import SimpleTestCase

from routing.analysis import analyze_routes, covered_miles, hourly_series, place_checkpoints

DEPARTURE = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
CALM = {'wind_speed_mph': 5.0, 'wind_gust_mph': 8.0, 'precipitation_in': 0.0, 'snowfall_in': 0.0}
STORM = {'wind_speed_mph': 40.0, 'wind_gust_mph': 50.0, 'precipitation_in': 0.0, 'snowfall_in': 0.0}


def straight_route(id=1, distance=60.0, duration=3600):
    # 1 degree of latitude due north; geometry length (~69 mi) differs from the
    # reported distance on purpose, to check that distances are scaled to the routing API's values.
    return {'id': id, 'distance_miles': distance, 'duration_seconds': duration,
            'geometry': [[0.0, 0.0], [1.0, 0.0]]}


class PlaceCheckpointsTests(SimpleTestCase):
    def test_interval_marks_plus_destination(self):
        checkpoints = place_checkpoints(straight_route(), 25, DEPARTURE)

        self.assertEqual([c['distance_miles'] for c in checkpoints], [0, 25, 50, 60])
        for checkpoint, lat in zip(checkpoints, [0, 25 / 60, 50 / 60, 1]):
            self.assertAlmostEqual(checkpoint['lat'], lat)
            self.assertAlmostEqual(checkpoint['lon'], 0)

    def test_eta_proportional_to_distance(self):
        checkpoints = place_checkpoints(straight_route(), 25, DEPARTURE)

        self.assertEqual([c['eta'] for c in checkpoints], [
            DEPARTURE, DEPARTURE + timedelta(minutes=25), DEPARTURE + timedelta(minutes=50),
            DEPARTURE + timedelta(minutes=60),
        ])

    def test_eta_keeps_departure_time_zone_offset(self):
        chicago = timezone(timedelta(hours=-5))
        eta = place_checkpoints(straight_route(), 50, DEPARTURE.astimezone(chicago))[-1]['eta']

        self.assertEqual(eta, DEPARTURE + timedelta(hours=1))

    def test_exact_multiple_has_no_duplicate_endpoint(self):
        checkpoints = place_checkpoints(straight_route(distance=50), 25, DEPARTURE)

        self.assertEqual([c['distance_miles'] for c in checkpoints], [0, 25, 50])

    def test_float_noise_on_exact_multiple_has_no_duplicate_endpoint(self):
        checkpoints = place_checkpoints(straight_route(distance=50.0000001), 25, DEPARTURE)

        self.assertEqual([round(c['distance_miles'], 3) for c in checkpoints], [0, 25, 50])

    def test_destination_just_past_a_mark_is_still_sampled(self):
        checkpoints = place_checkpoints(straight_route(distance=50.004), 25, DEPARTURE)

        self.assertEqual([c['distance_miles'] for c in checkpoints], [0, 25, 50, 50.004])

    def test_route_shorter_than_interval_has_both_endpoints(self):
        checkpoints = place_checkpoints(straight_route(distance=8), 10, DEPARTURE)

        self.assertEqual([c['distance_miles'] for c in checkpoints], [0, 8])

    def test_follows_multi_vertex_geometry(self):
        route = {'id': 1, 'distance_miles': 100.0, 'duration_seconds': 7200,
                 'geometry': [[0.0, 0.0], [0.0, 1.0], [0.0, 1.0], [0.0, 2.0]]}  # includes a repeated vertex

        checkpoints = place_checkpoints(route, 25, DEPARTURE)

        self.assertEqual([[round(c['lat'], 9), round(c['lon'], 9)] for c in checkpoints],
                         [[0, 0], [0, 0.5], [0, 1], [0, 1.5], [0, 2]])


class CoveredMilesTests(SimpleTestCase):
    def test_each_checkpoint_covers_nearest_road(self):
        self.assertEqual(covered_miles([0, 25, 50, 60]), [12.5, 25, 17.5, 5])

    def test_single_checkpoint(self):
        self.assertEqual(covered_miles([0]), [0.0])


def hourly(weather_by_hour):
    """Forecast keyed by UTC timestamp, for hour offsets from DEPARTURE."""
    return {int((DEPARTURE + timedelta(hours=h)).timestamp()): w for h, w in weather_by_hour.items()}


@patch('routing.analysis.get_forecasts')
@patch('routing.analysis.get_routes')
class AnalyzeRoutesTests(SimpleTestCase):
    def test_weather_taken_at_each_checkpoint_arrival_hour(self, get_routes, get_forecasts):
        # 3-hour route: checkpoints at 0, 1.5 h (rounds to 2 h) and 3 h.
        get_routes.return_value = [straight_route(distance=100, duration=3 * 3600)]
        get_forecasts.return_value = [hourly({0: CALM, 1: STORM, 2: CALM, 3: CALM})] * 3

        result = analyze_routes((0, 0), (1, 0), DEPARTURE, 0, 50, DEPARTURE)

        self.assertEqual([c['risk'] for c in result['routes'][0]['checkpoints']], ['LOW', 'LOW', 'LOW'])

    def test_ranks_routes_and_recommends_safest(self, get_routes, get_forecasts):
        get_routes.return_value = [straight_route(1, duration=3000), straight_route(2, duration=3600)]
        get_forecasts.return_value = [hourly({0: STORM, 1: STORM})] * 4 + [hourly({0: CALM, 1: CALM})] * 4

        result = analyze_routes((0, 0), (1, 0), DEPARTURE, 45_000, 25, DEPARTURE)

        self.assertEqual([r['id'] for r in result['routes']], [2, 1])
        self.assertEqual([r['rank'] for r in result['routes']], [1, 2])
        self.assertEqual(result['recommended_route_id'], 2)
        self.assertEqual(result['routes'][1]['risk_miles']['SEVERE'], 60)  # 40 mph + 45,000 lb
        self.assertEqual(result['routes'][0]['arrival_time'], DEPARTURE + timedelta(hours=1))

    def test_no_recommendation_when_every_route_is_no_travel(self, get_routes, get_forecasts):
        get_routes.return_value = [straight_route()]
        get_forecasts.return_value = [hourly({0: {**CALM, 'wind_speed_mph': 60.0}, 1: CALM})] * 4

        result = analyze_routes((0, 0), (1, 0), DEPARTURE, 0, 25, DEPARTURE)

        self.assertTrue(result['routes'][0]['no_travel'])
        self.assertIsNone(result['recommended_route_id'])

    def test_arrival_beyond_forecast_is_unknown(self, get_routes, get_forecasts):
        get_routes.return_value = [straight_route()]
        get_forecasts.return_value = [hourly({0: CALM})] * 4  # no data after departure hour

        route = analyze_routes((0, 0), (1, 0), DEPARTURE, 0, 25, DEPARTURE)['routes'][0]

        # ETAs 0, 25, 50, 60 min round to hours 0, 0, 1, 1; hour 1 is missing.
        self.assertEqual([c['risk'] for c in route['checkpoints']], ['LOW', 'LOW', None, None])
        self.assertEqual([c['weather'] for c in route['checkpoints']][2:], [None, None])
        self.assertEqual(route['unknown_miles'], 22.5)
        self.assertEqual(route['average_risk'], 1)

    def test_one_weather_request_for_all_routes(self, get_routes, get_forecasts):
        get_routes.return_value = [straight_route(1), straight_route(2, distance=20)]
        get_forecasts.return_value = [hourly({0: CALM, 1: CALM})] * 6

        analyze_routes((0, 0), (1, 0), DEPARTURE, 0, 25, DEPARTURE)

        get_forecasts.assert_called_once()
        self.assertEqual(len(get_forecasts.call_args.args[0]), 6)  # 4 + 2 checkpoints


class CheckpointPathTests(SimpleTestCase):
    def test_paths_split_route_midway_between_checkpoints(self):
        checkpoints = place_checkpoints(straight_route(), 25, DEPARTURE)  # marks 0, 25, 50, 60 of 60

        bounds = [(round(c['path'][0][0], 9), round(c['path'][-1][0], 9)) for c in checkpoints]
        self.assertEqual(bounds, [(0, round(12.5 / 60, 9)), (round(12.5 / 60, 9), round(37.5 / 60, 9)),
                                  (round(37.5 / 60, 9), round(55 / 60, 9)), (round(55 / 60, 9), 1)])

    def test_paths_follow_geometry_vertices(self):
        route = {'id': 1, 'distance_miles': 100.0, 'duration_seconds': 7200,
                 'geometry': [[0.0, 0.0], [0.0, 1.0], [0.0, 2.0]]}

        path = place_checkpoints(route, 50, DEPARTURE)[1]['path']  # stretch 25..75 mi

        self.assertEqual(len(path), 3)
        self.assertAlmostEqual(path[0][1], 0.5)
        self.assertEqual(path[1], [0.0, 1.0])  # the vertex at mile 50
        self.assertAlmostEqual(path[2][1], 1.5)


class HourlySeriesTests(SimpleTestCase):
    def test_covers_hours_0_to_48_inclusive(self):
        forecast = hourly({h: CALM for h in range(-5, 60)})

        series = hourly_series(forecast, DEPARTURE, 0)

        self.assertEqual(len(series['risk']), 49)
        self.assertTrue(all(len(values) == 49 for values in series.values()))

    def test_boundary_hours_use_their_own_forecast(self):
        forecast = hourly({0: STORM, 1: CALM, 47: CALM, 48: {**STORM, 'wind_speed_mph': 60.0}, 49: STORM})

        series = hourly_series(forecast, DEPARTURE, 0)

        self.assertEqual(series['risk'][0], 'HIGH')
        self.assertEqual(series['risk'][47], 'LOW')
        self.assertEqual(series['risk'][48], 'NO_TRAVEL')
        self.assertEqual(series['wind_speed_mph'][48], 60.0)

    def test_missing_hours_are_none_not_zero(self):
        forecast = hourly({0: CALM, 2: {**CALM, 'snowfall_in': None}})

        series = hourly_series(forecast, DEPARTURE, 0)

        self.assertIsNone(series['risk'][1])
        self.assertIsNone(series['wind_speed_mph'][1])
        self.assertIsNone(series['snowfall_in'][2])
        self.assertEqual(series['risk'][2], 'LOW')  # still classified from the values present
        self.assertEqual(series['risk'][3:], [None] * 46)

    def test_load_rules_apply(self):
        series = hourly_series(hourly({0: STORM}), DEPARTURE, 45_000)  # 40 mph, > 40,000 lb

        self.assertEqual(series['risk'][0], 'SEVERE')

    def test_values_rounded_for_output_after_classification(self):
        forecast = hourly({0: {**CALM, 'wind_speed_mph': 24.96, 'precipitation_in': 0.12345}})

        series = hourly_series(forecast, DEPARTURE, 0)

        self.assertEqual(series['wind_speed_mph'][0], 25.0)
        self.assertEqual(series['precipitation_in'][0], 0.123)
        self.assertEqual(series['risk'][0], 'MODERATE')  # 0.12345 in/hr rain; wind 24.96 is still Low


@patch('routing.analysis.get_forecasts')
@patch('routing.analysis.get_routes')
class HeatmapVersusArrivalTests(SimpleTestCase):
    def test_heatmap_uses_forecast_start_not_arrival_time(self, get_routes, get_forecasts):
        get_routes.return_value = [straight_route(distance=40, duration=3600)]  # checkpoints 0, 25, 40
        get_forecasts.return_value = [hourly({-3: STORM, -2: CALM, 0: CALM, 1: CALM})] * 3

        route = analyze_routes((0, 0), (1, 0), DEPARTURE, 0, 25, DEPARTURE - timedelta(hours=3))['routes'][0]

        first = route['checkpoints'][0]
        self.assertEqual(first['risk'], 'LOW')  # arrival at DEPARTURE is calm
        self.assertEqual(first['hourly']['risk'][:3], ['HIGH', 'LOW', None])  # heatmap hours -3, -2, -1
