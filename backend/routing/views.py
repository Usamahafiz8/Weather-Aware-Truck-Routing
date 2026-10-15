import math
from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.response import Response

from routing.analysis import analyze_routes
from routing.tomtom import RoutingError, geocode
from routing.weather import FORECAST_DAYS, WeatherError

MAX_LOAD_LB = 80_000  # US federal gross vehicle weight limit


class FiniteFloatField(serializers.FloatField):
    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if not math.isfinite(value):
            self.fail('invalid')
        return value


class PointSerializer(serializers.Serializer):
    lat = FiniteFloatField(min_value=-90, max_value=90)
    lon = FiniteFloatField(min_value=-180, max_value=180)


class AnalyzeRequestSerializer(serializers.Serializer):
    origin = PointSerializer()
    destination = PointSerializer()
    departure_time = serializers.DateTimeField()  # without an offset it is read as UTC
    load_weight_lb = serializers.IntegerField(min_value=0, max_value=MAX_LOAD_LB)
    checkpoint_interval_miles = serializers.ChoiceField(choices=[10, 25, 50])

    def validate_departure_time(self, value):
        now = timezone.now()
        if value < now - timedelta(hours=1):
            raise serializers.ValidationError('Departure time cannot be in the past.')
        if value > now + timedelta(days=FORECAST_DAYS):
            raise serializers.ValidationError(f'Departure time must be within {FORECAST_DAYS} days.')
        return value

    def validate(self, data):
        if data['origin'] == data['destination']:
            raise serializers.ValidationError('Origin and destination must be different.')
        return data


@api_view(['GET'])
def geocode_place(request):
    query = request.query_params.get('q', '').strip()
    if not query or len(query) > 200:
        return Response({'q': ['Enter a place name of up to 200 characters.']}, status=400)
    try:
        place = geocode(query)
    except RoutingError as exc:
        return Response({'detail': str(exc)}, status=502)
    if place is None:
        return Response({'detail': f'No location found for "{query}".'}, status=404)
    return Response(place)


@api_view(['POST'])
def analyze(request):
    serializer = AnalyzeRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        result = analyze_routes(
            origin=(data['origin']['lat'], data['origin']['lon']),
            destination=(data['destination']['lat'], data['destination']['lon']),
            departure=data['departure_time'],
            load_lb=data['load_weight_lb'],
            interval_miles=data['checkpoint_interval_miles'],
            # Heatmap hours count from the start of the current hour.
            forecast_start=timezone.now().replace(minute=0, second=0, microsecond=0),
        )
    except (RoutingError, WeatherError) as exc:
        return Response({'detail': str(exc)}, status=502)
    return Response({
        **result,
        'load_weight_lb': data['load_weight_lb'],
        'checkpoint_interval_miles': data['checkpoint_interval_miles'],
    })
