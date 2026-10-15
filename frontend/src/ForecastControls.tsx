import type { Route } from './api'
import { dateTime } from './format'

export type MapMode = 'arrival' | 'forecast'

export const MAX_OFFSET_HOURS = 48

interface Props {
  routes: Route[]
  mode: MapMode
  offset: number
  forecastTime: Date
  onModeChange: (mode: MapMode) => void
  onOffsetChange: (offset: number) => void
}

export default function ForecastControls({ routes, mode, offset, forecastTime, onModeChange, onOffsetChange }: Props) {
  const checkpoints = routes.flatMap((route) => route.checkpoints)
  const missing = checkpoints.filter((c) => c.hourly.risk[offset] === null).length

  return (
    <section className="panel forecast-controls">
      <div className="mode-toggle" role="radiogroup" aria-label="Map shows">
        <button type="button" role="radio" aria-checked={mode === 'arrival'} onClick={() => onModeChange('arrival')}>
          Risk at truck arrival
        </button>
        <button type="button" role="radio" aria-checked={mode === 'forecast'} onClick={() => onModeChange('forecast')}>
          Forecast heatmap
        </button>
      </div>

      <label className="slider">
        <span>
          Forecast hour: <strong>+{offset} h</strong> · <strong>{dateTime(forecastTime.toISOString())}</strong>
        </span>
        <input
          type="range" min={0} max={MAX_OFFSET_HOURS} step={1} value={offset}
          onChange={(event) => onOffsetChange(Number(event.target.value))}
          aria-valuetext={`+${offset} hours, ${dateTime(forecastTime.toISOString())}`}
        />
        <span className="slider-scale"><span>Now</span><span>+24 h</span><span>+48 h</span></span>
      </label>

      <p className="note">
        {mode === 'arrival'
          ? 'Map colors show the forecast for when the truck reaches each checkpoint. These drive the ranking.'
          : 'Map colors show conditions along every route at the selected hour, regardless of when the truck passes.'}
      </p>
      {mode === 'forecast' && missing > 0 && (
        <p className="card-warning">
          No forecast for {missing} of {checkpoints.length} checkpoints at this hour (shown grey and dashed).
        </p>
      )}
    </section>
  )
}
