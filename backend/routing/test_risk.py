from django.test import SimpleTestCase

from routing.risk import (
    Risk, checkpoint_risk, rain_risk, rank_routes, snow_risk, summarize_route, wind_risk,
    wind_risk_for_load,
)

L, M, H, S, NT = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


class ThresholdTests(SimpleTestCase):
    def check(self, classify, cases):
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(classify(value), expected)

    def test_wind(self):
        self.check(wind_risk, [
            (0, L), (24.9, L), (25, M), (34, M), (34.9, M), (35, H), (44.9, H),
            (45, S), (54, S), (54.9, S), (55, NT), (80, NT),
        ])

    def test_rain(self):
        self.check(rain_risk, [
            (0, L), (0.09, L), (0.10, M), (0.24, M),
            (0.25, H),  # shared boundary -> higher band
            (0.49, H),
            (0.50, S),  # shared boundary -> higher band
            (0.99, S), (1.00, S),  # "> 1.00" is No Travel, so 1.00 is Severe
            (1.01, NT),
        ])

    def test_snow(self):
        self.check(snow_risk, [
            (0, L), (0.49, L), (0.5, M), (0.99, M),
            (1.0, H),  # shared boundary -> higher band
            (1.99, H),
            (2.0, S),  # shared boundary -> higher band
            (3.0, S),  # "> 3.0" is No Travel, so 3.0 is Severe
            (3.01, NT),
        ])


class LoadRuleTests(SimpleTestCase):
    def test_load_rules(self):
        cases = [
            # >= 55 mph: No Travel for any load
            (55, 0, NT), (60, 10_000, NT),
            # 45-54 mph: No Travel only above 30,000 lb
            (45, 30_000, S), (45, 30_001, NT), (54.9, 30_001, NT), (50, 20_000, S),
            # 35-44 mph: Severe only above 40,000 lb
            (35, 40_000, H), (35, 40_001, S), (44.9, 80_000, S),
            # below 35 mph: load has no effect
            (34.9, 80_000, M), (10, 80_000, L),
        ]
        for mph, load, expected in cases:
            with self.subTest(mph=mph, load=load):
                self.assertEqual(wind_risk_for_load(mph, load), expected)


class CheckpointRiskTests(SimpleTestCase):
    def weather(self, wind=0.0, rain=0.0, snow=0.0):
        return {'wind_speed_mph': wind, 'wind_gust_mph': None, 'precipitation_in': rain, 'snowfall_in': snow}

    def test_worst_hazard_wins(self):
        self.assertEqual(checkpoint_risk(self.weather(wind=30, rain=0.3, snow=0.6), 0), H)

    def test_hazards_do_not_add_up(self):
        self.assertEqual(checkpoint_risk(self.weather(wind=40, rain=0.3, snow=1.5), 0), H)

    def test_load_adjustment_applies_before_combining(self):
        self.assertEqual(checkpoint_risk(self.weather(wind=50, rain=0.3), 35_000), NT)

    def test_partial_data_uses_available_hazards(self):
        self.assertEqual(checkpoint_risk(self.weather(wind=None, rain=0.6, snow=None), 0), S)

    def test_missing_weather_is_unknown_not_low(self):
        self.assertIsNone(checkpoint_risk(None, 0))
        self.assertIsNone(checkpoint_risk(self.weather(wind=None, rain=None, snow=None), 0))


class SummarizeRouteTests(SimpleTestCase):
    def test_risk_miles_and_mile_weighted_average(self):
        summary = summarize_route([(10, L), (10, H), (5, S)])

        self.assertEqual(summary['risk_miles']['HIGH'], 10)
        self.assertEqual(summary['risk_miles']['SEVERE'], 5)
        self.assertAlmostEqual(summary['average_risk'], (10 * 1 + 10 * 3 + 5 * 4) / 25)
        self.assertFalse(summary['no_travel'])

    def test_unknown_miles_excluded_from_average(self):
        summary = summarize_route([(10, M), (40, None)])

        self.assertEqual(summary['unknown_miles'], 40)
        self.assertEqual(summary['average_risk'], 2)

    def test_all_unknown_has_no_average(self):
        self.assertIsNone(summarize_route([(10, None)])['average_risk'])

    def test_any_no_travel_segment_flags_route(self):
        self.assertTrue(summarize_route([(100, L), (0.5, NT)])['no_travel'])


def route(id, segments, duration=3600):
    return {'id': id, 'duration_seconds': duration, **summarize_route(segments)}


def ranked_ids(*routes):
    return [r['id'] for r in rank_routes(list(routes))]


class RankRoutesTests(SimpleTestCase):
    def test_fewest_severe_miles_first(self):
        self.assertEqual(ranked_ids(
            route(1, [(10, S), (0, H)]),
            route(2, [(5, S), (50, H)]),
        ), [2, 1])

    def test_fewest_high_miles_breaks_severe_tie(self):
        self.assertEqual(ranked_ids(
            route(1, [(5, S), (20, H)]),
            route(2, [(5, S), (10, H), (100, M)]),
        ), [2, 1])

    def test_lowest_average_breaks_high_tie(self):
        self.assertEqual(ranked_ids(
            route(1, [(10, H), (10, M)]),
            route(2, [(10, H), (10, L)]),
        ), [2, 1])

    def test_shortest_time_breaks_average_tie(self):
        self.assertEqual(ranked_ids(
            route(1, [(10, L)], duration=7200),
            route(2, [(10, L)], duration=3600),
        ), [2, 1])

    def test_route_id_breaks_exact_tie(self):
        self.assertEqual(ranked_ids(route(2, [(10, L)]), route(1, [(10, L)])), [1, 2])

    def test_float_noise_does_not_reorder(self):
        noisy = route(1, [(0.1, S), (0.2, S)], duration=3600)  # 0.30000000000000004 Severe miles
        exact = route(2, [(0.3, S)], duration=7200)
        self.assertEqual(ranked_ids(noisy, exact), [1, 2])  # equal Severe miles, so faster wins

    def test_no_travel_route_never_ranks_above_travelable(self):
        self.assertEqual(ranked_ids(
            route(1, [(1, NT), (99, L)], duration=60),  # otherwise best on every criterion
            route(2, [(50, S), (50, H)], duration=99_999),
        ), [2, 1])

    def test_all_no_travel_routes_still_ranked_and_flagged(self):
        ranked = rank_routes([route(1, [(1, NT), (10, S)]), route(2, [(1, NT)])])

        self.assertEqual([r['id'] for r in ranked], [2, 1])
        self.assertTrue(all(r['no_travel'] for r in ranked))

    def test_unknown_average_ranks_after_known_average(self):
        self.assertEqual(ranked_ids(route(1, [(10, None)]), route(2, [(10, M)])), [2, 1])
