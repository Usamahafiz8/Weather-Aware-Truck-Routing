import { useState, type FormEvent } from 'react'

export interface TripFormValues {
  origin: string
  destination: string
  departure: string // datetime-local value, in the browser's time zone
  loadWeight: string
  interval: string
}

function nextHourLocal() {
  const date = new Date()
  date.setHours(date.getHours() + 1, 0, 0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:00`
}

interface Props {
  busy: boolean
  onSubmit: (values: TripFormValues) => void
}

export default function TripForm({ busy, onSubmit }: Props) {
  const [values, setValues] = useState<TripFormValues>({
    origin: '',
    destination: '',
    departure: nextHourLocal(),
    loadWeight: '30000',
    interval: '25',
  })

  const update = (field: keyof TripFormValues) => (event: { target: { value: string } }) =>
    setValues({ ...values, [field]: event.target.value })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit({ ...values, origin: values.origin.trim(), destination: values.destination.trim() })
  }

  return (
    <form className="panel trip-form" onSubmit={submit}>
      <label>
        Origin
        <input required value={values.origin} onChange={update('origin')} placeholder="e.g. Chicago, IL" />
      </label>
      <label>
        Destination
        <input required value={values.destination} onChange={update('destination')} placeholder="e.g. Denver, CO" />
      </label>
      <label>
        Departure
        <input required type="datetime-local" value={values.departure} onChange={update('departure')} />
      </label>
      <div className="form-row">
        <label>
          Load weight (lb)
          <input
            required type="number" min={0} max={80000} step={1}
            value={values.loadWeight} onChange={update('loadWeight')}
          />
        </label>
        <label>
          Checkpoint every
          <select value={values.interval} onChange={update('interval')}>
            <option value="10">10 miles</option>
            <option value="25">25 miles</option>
            <option value="50">50 miles</option>
          </select>
        </label>
      </div>
      <button type="submit" disabled={busy}>{busy ? 'Analyzing…' : 'Analyze routes'}</button>
    </form>
  )
}
