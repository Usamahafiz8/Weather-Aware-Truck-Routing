import { useState } from 'react'
import 'leaflet/dist/leaflet.css'
import './App.css'
import { ApiError, analyzeRoutes, geocode, type Analysis, type Checkpoint, type Place } from './api'
import CheckpointPanel from './CheckpointPanel'
import ForecastControls, { type MapMode } from './ForecastControls'
import { RISK_COLORS, RISK_LABELS, RISK_LEVELS, UNKNOWN_COLOR } from './format'
import RouteCards from './RouteCards'
import RouteMap from './RouteMap'
import TripForm, { type TripFormValues } from './TripForm'

type Status = 'idle' | 'geocoding' | 'analyzing'

const FIELD_LABELS: Record<string, string> = {
  departure_time: 'Departure',
  load_weight_lb: 'Load weight',
  checkpoint_interval_miles: 'Checkpoint interval',
  origin: 'Origin',
  destination: 'Destination',
  non_field_errors: 'Trip',
}

interface ErrorState {
  message: string
  details: string[]
}

function toErrorState(error: unknown, context: string): ErrorState {
  if (!(error instanceof ApiError)) return { message: `${context}: unexpected error.`, details: [] }
  const details = Object.entries(error.fieldErrors).flatMap(([field, messages]) =>
    [messages].flat().map((message) => `${FIELD_LABELS[field] ?? field}: ${message}`))
  return { message: `${context}: ${error.message}`, details }
}

export default function App() {
  const [status, setStatus] = useState<Status>('idle')
  const [error, setError] = useState<ErrorState | null>(null)
  const [places, setPlaces] = useState<{ origin: Place; destination: Place } | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [selectedRouteId, setSelectedRouteId] = useState<number | null>(null)
  const [selectedCheckpoint, setSelectedCheckpoint] = useState<number | null>(null)
  const [mapMode, setMapMode] = useState<MapMode>('arrival')
  const [offset, setOffset] = useState(0)

  async function handleSubmit(values: TripFormValues) {
    setError(null)
    setStatus('geocoding')
    let origin: Place, destination: Place
    try {
      ;[origin, destination] = await Promise.all([geocode(values.origin), geocode(values.destination)])
    } catch (err) {
      setError(toErrorState(err, 'Location search failed'))
      setStatus('idle')
      return
    }

    setStatus('analyzing')
    try {
      const result = await analyzeRoutes({
        origin: { lat: origin.lat, lon: origin.lon },
        destination: { lat: destination.lat, lon: destination.lon },
        departure_time: new Date(values.departure).toISOString(),
        load_weight_lb: Number(values.loadWeight),
        checkpoint_interval_miles: Number(values.interval),
      })
      setPlaces({ origin, destination })
      setAnalysis(result)
      setSelectedRouteId(result.recommended_route_id ?? result.routes[0].id)
      setSelectedCheckpoint(null)
    } catch (err) {
      setError(toErrorState(err, 'Route analysis failed'))
    } finally {
      setStatus('idle')
    }
  }

  function selectRoute(id: number) {
    setSelectedRouteId(id)
    setSelectedCheckpoint(null)
  }

  const selectedRoute = analysis?.routes.find((route) => route.id === selectedRouteId) ?? null
  const checkpoint = selectedRoute && selectedCheckpoint !== null ? selectedRoute.checkpoints[selectedCheckpoint] : null
  const recommended = analysis?.routes.find((route) => route.id === analysis.recommended_route_id)
  const forecastTime = new Date(Date.parse(analysis?.forecast_start ?? '') + offset * 3_600_000)
  const riskOf = (c: Checkpoint) => (mapMode === 'arrival' ? c.risk : c.hourly.risk[offset])

  return (
    <div className="app">
      <header className="app-header">
        <h1>Weather-Aware Truck Routing</h1>
        <p>Compare truck routes by the weather expected when you reach each checkpoint.</p>
      </header>

      <main className="layout">
        <div className="sidebar">
          <TripForm busy={status !== 'idle'} onSubmit={handleSubmit} />

          {status !== 'idle' && (
            <p className="note" role="status">
              {status === 'geocoding' ? 'Finding locations…' : 'Fetching routes and forecasts…'}
            </p>
          )}

          {error && (
            <div className="alert alert-danger" role="alert">
              <p>{error.message}</p>
              {error.details.length > 0 && <ul>{error.details.map((d) => <li key={d}>{d}</li>)}</ul>}
            </div>
          )}

          {analysis && places && (
            <>
              <p className="trip-summary">
                <strong>{places.origin.label}</strong> → <strong>{places.destination.label}</strong>
              </p>
              {recommended && (
                <p className="alert alert-success">
                  <strong>Recommended: Route {recommended.id}</strong> — ranked by fewest severe miles, then
                  high-risk miles, average risk, and drive time.
                </p>
              )}
              <RouteCards
                routes={analysis.routes}
                recommendedId={analysis.recommended_route_id}
                selectedId={selectedRouteId}
                onSelect={selectRoute}
              />
            </>
          )}

          {!analysis && status === 'idle' && !error && (
            <p className="note">Enter a trip to compare up to three routes.</p>
          )}
        </div>

        <div className="map-column">
          {analysis && (
            <ForecastControls
              routes={analysis.routes}
              mode={mapMode}
              offset={offset}
              forecastTime={forecastTime}
              onModeChange={setMapMode}
              onOffsetChange={(hours) => {
                setOffset(hours)
                setMapMode('forecast')
              }}
            />
          )}
          <RouteMap
            routes={analysis?.routes ?? []}
            origin={places?.origin ?? null}
            destination={places?.destination ?? null}
            selectedRouteId={selectedRouteId}
            selectedCheckpoint={selectedCheckpoint}
            riskOf={riskOf}
            onSelectRoute={selectRoute}
            onSelectCheckpoint={setSelectedCheckpoint}
          />
          <ul className="legend" aria-label="Risk colors">
            {RISK_LEVELS.map((risk) => (
              <li key={risk}><span style={{ background: RISK_COLORS[risk] }} />{RISK_LABELS[risk]}</li>
            ))}
            <li><span style={{ background: UNKNOWN_COLOR }} />No forecast</li>
          </ul>
          {analysis && (
            <CheckpointPanel
              checkpoint={checkpoint}
              index={selectedCheckpoint}
              loadWeight={analysis.load_weight_lb}
              offset={offset}
              forecastTime={forecastTime}
            />
          )}
        </div>
      </main>
    </div>
  )
}
