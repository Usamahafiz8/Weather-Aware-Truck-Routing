const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export type Risk = 'LOW' | 'MODERATE' | 'HIGH' | 'SEVERE' | 'NO_TRAVEL'

export interface Weather {
  wind_speed_mph: number | null
  wind_gust_mph: number | null
  precipitation_in: number | null
  snowfall_in: number | null
}

// Forecast for hours 0..48 after Analysis.forecast_start; null where no data exists.
export type HourlyForecast = { risk: (Risk | null)[] } & { [K in keyof Weather]: Weather[K][] }

export interface Checkpoint {
  lat: number
  lon: number
  distance_miles: number
  eta: string
  weather: Weather | null // at the truck's estimated arrival
  risk: Risk | null // at the truck's estimated arrival
  path: [number, number][] // stretch of road this checkpoint represents
  hourly: HourlyForecast
}

export interface Route {
  id: number
  rank: number
  distance_miles: number
  duration_seconds: number
  arrival_time: string
  geometry: [number, number][]
  checkpoints: Checkpoint[]
  risk_miles: Record<Risk, number>
  unknown_miles: number
  average_risk: number | null
  no_travel: boolean
}

export interface Analysis {
  departure_time: string
  forecast_start: string
  recommended_route_id: number | null
  routes: Route[]
  load_weight_lb: number
  checkpoint_interval_miles: number
}

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface AnalyzeInput {
  origin: { lat: number; lon: number }
  destination: { lat: number; lon: number }
  departure_time: string
  load_weight_lb: number
  checkpoint_interval_miles: number
}

export class ApiError extends Error {
  // Field-level validation messages from a 400 response, e.g. {load_weight_lb: ['...']}.
  fieldErrors: Record<string, string[]>

  constructor(message: string, fieldErrors: Record<string, string[]> = {}) {
    super(message)
    this.fieldErrors = fieldErrors
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(API_BASE_URL + path, init)
  } catch {
    throw new ApiError('Could not reach the server. Check your connection and try again.')
  }
  const body = await response.json().catch(() => null)
  if (response.ok) return body as T
  if (body?.detail) throw new ApiError(body.detail)
  if (response.status === 400 && body) throw new ApiError('Please correct the following:', body)
  throw new ApiError(`Request failed (HTTP ${response.status}).`)
}

export function geocode(query: string) {
  return request<Place>(`/api/geocode/?q=${encodeURIComponent(query)}`)
}

export function analyzeRoutes(input: AnalyzeInput) {
  return request<Analysis>('/api/routes/analyze/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}
