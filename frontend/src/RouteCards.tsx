import type { Route } from './api'
import { RISK_COLORS, RISK_LABELS, RISK_LEVELS, UNKNOWN_COLOR, dateTime, duration, miles } from './format'

interface Props {
  routes: Route[]
  recommendedId: number | null
  selectedId: number | null
  onSelect: (id: number) => void
}

function fewerRoutesNote(routes: Route[]) {
  if (routes.length >= 3) return null
  return `${routes.length} of 3 possible routes returned. The routing service found no further distinct alternatives for this trip.`
}

function RiskBar({ route }: { route: Route }) {
  const segments = [
    ...RISK_LEVELS.map((risk) => ({ label: RISK_LABELS[risk], color: RISK_COLORS[risk], value: route.risk_miles[risk] })),
    { label: 'Unknown', color: UNKNOWN_COLOR, value: route.unknown_miles },
  ].filter((segment) => segment.value > 0)
  const total = segments.reduce((sum, segment) => sum + segment.value, 0)
  return (
    <div className="risk-bar" aria-label="Miles by risk level">
      {segments.map((segment) => (
        <span
          key={segment.label}
          style={{ width: `${(segment.value / total) * 100}%`, background: segment.color }}
          title={`${segment.label}: ${miles(segment.value)}`}
        />
      ))}
    </div>
  )
}

export default function RouteCards({ routes, recommendedId, selectedId, onSelect }: Props) {
  const note = fewerRoutesNote(routes)
  return (
    <section className="route-cards">
      {recommendedId === null && (
        <p className="alert alert-danger">
          Every route crosses a No Travel zone at the planned arrival times. No route is recommended.
        </p>
      )}
      {note && <p className="note">{note}</p>}

      {routes.map((route) => (
        <button
          key={route.id}
          type="button"
          className={`panel route-card${route.id === selectedId ? ' selected' : ''}`}
          onClick={() => onSelect(route.id)}
          aria-pressed={route.id === selectedId}
        >
          <div className="route-card-header">
            <strong>Route {route.id}</strong>
            <span className="rank">#{route.rank}</span>
            {route.id === recommendedId && <span className="badge badge-recommended">Recommended</span>}
            {route.no_travel && <span className="badge badge-no-travel">No Travel</span>}
          </div>

          <RiskBar route={route} />

          <dl className="stats">
            <div><dt>Distance</dt><dd>{miles(route.distance_miles)}</dd></div>
            <div><dt>Drive time</dt><dd>{duration(route.duration_seconds)}</dd></div>
            <div><dt>Severe miles</dt><dd>{miles(route.risk_miles.SEVERE)}</dd></div>
            <div><dt>High-risk miles</dt><dd>{miles(route.risk_miles.HIGH)}</dd></div>
            <div>
              <dt>Average risk</dt>
              <dd>{route.average_risk === null ? 'No data' : `${route.average_risk.toFixed(2)} / 5`}</dd>
            </div>
            <div><dt>Arrival</dt><dd>{dateTime(route.arrival_time)}</dd></div>
          </dl>

          {route.no_travel && (
            <p className="card-warning">{miles(route.risk_miles.NO_TRAVEL)} of this route is No Travel.</p>
          )}
          {route.unknown_miles > 0 && (
            <p className="card-warning">Forecast unavailable for {miles(route.unknown_miles)} of this route.</p>
          )}
        </button>
      ))}
    </section>
  )
}
