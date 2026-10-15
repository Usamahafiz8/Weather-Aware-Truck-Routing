import type { Checkpoint, Risk, Weather } from './api'
import { dateTime, measurement, riskColor, riskLabel } from './format'

interface Props {
  checkpoint: Checkpoint | null
  index: number | null
  loadWeight: number
  offset: number
  forecastTime: Date
}

function RiskPill({ risk }: { risk: Risk | null }) {
  return <span className="risk-pill" style={{ background: riskColor(risk) }}>{riskLabel(risk)}</span>
}

function windText(weather: Weather | null) {
  const wind = measurement(weather?.wind_speed_mph, 'mph', 0)
  return weather?.wind_gust_mph != null ? `${wind} (gusts ${weather.wind_gust_mph.toFixed(0)})` : wind
}

export default function CheckpointPanel({ checkpoint, index, loadWeight, offset, forecastTime }: Props) {
  if (!checkpoint || index === null) {
    return <aside className="panel checkpoint-panel muted">Click a checkpoint on the map to see its forecast.</aside>
  }
  const arrival = checkpoint.weather
  const hourly = checkpoint.hourly
  // The backend leaves risk null only when every weather value for that hour is missing.
  const atHour: Weather | null = hourly.risk[offset] === null
    ? null
    : {
        wind_speed_mph: hourly.wind_speed_mph[offset],
        wind_gust_mph: hourly.wind_gust_mph[offset],
        precipitation_in: hourly.precipitation_in[offset],
        snowfall_in: hourly.snowfall_in[offset],
      }

  return (
    <aside className="panel checkpoint-panel">
      <div className="checkpoint-header">
        <strong>Checkpoint {index + 1} · mile {checkpoint.distance_miles.toFixed(0)}</strong>
        <span className="muted">Load {loadWeight.toLocaleString()} lb</span>
      </div>
      <table className="compare">
        <thead>
          <tr>
            <th />
            <th>At truck arrival<br /><small>{dateTime(checkpoint.eta)}</small></th>
            <th>At forecast hour +{offset} h<br /><small>{dateTime(forecastTime.toISOString())}</small></th>
          </tr>
        </thead>
        <tbody>
          <tr><th>Risk</th><td><RiskPill risk={checkpoint.risk} /></td><td><RiskPill risk={hourly.risk[offset]} /></td></tr>
          <tr><th>Wind</th><td>{windText(arrival)}</td><td>{windText(atHour)}</td></tr>
          <tr>
            <th>Rain</th>
            <td>{measurement(arrival?.precipitation_in, 'in/hr', 2)}</td>
            <td>{measurement(atHour?.precipitation_in, 'in/hr', 2)}</td>
          </tr>
          <tr>
            <th>Snow</th>
            <td>{measurement(arrival?.snowfall_in, 'in/hr', 1)}</td>
            <td>{measurement(atHour?.snowfall_in, 'in/hr', 1)}</td>
          </tr>
        </tbody>
      </table>
      {(!arrival || !atHour) && <p className="card-warning">"No data" means the forecast is unavailable for that time.</p>}
    </aside>
  )
}
