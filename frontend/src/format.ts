import type { Risk } from './api'

export const RISK_LEVELS: Risk[] = ['LOW', 'MODERATE', 'HIGH', 'SEVERE', 'NO_TRAVEL']

export const RISK_LABELS: Record<Risk, string> = {
  LOW: 'Low',
  MODERATE: 'Moderate',
  HIGH: 'High',
  SEVERE: 'Severe',
  NO_TRAVEL: 'No Travel',
}

export const RISK_COLORS: Record<Risk, string> = {
  LOW: '#2f9e44',
  MODERATE: '#e0b000',
  HIGH: '#f08c00',
  SEVERE: '#e03131',
  NO_TRAVEL: '#7b2d8e',
}

export const UNKNOWN_COLOR = '#868e96'

export function riskLabel(risk: Risk | null) {
  return risk ? RISK_LABELS[risk] : 'Unknown'
}

export function riskColor(risk: Risk | null) {
  return risk ? RISK_COLORS[risk] : UNKNOWN_COLOR
}

export function miles(value: number) {
  return `${value.toFixed(value < 10 ? 1 : 0)} mi`
}

export function duration(seconds: number) {
  const totalMinutes = Math.round(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  return hours ? `${hours} h ${totalMinutes % 60} min` : `${totalMinutes} min`
}

export function dateTime(iso: string) {
  return new Date(iso).toLocaleString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
  })
}

export function measurement(value: number | null | undefined, unit: string, digits: number) {
  return value == null ? 'No data' : `${value.toFixed(digits)} ${unit}`
}
