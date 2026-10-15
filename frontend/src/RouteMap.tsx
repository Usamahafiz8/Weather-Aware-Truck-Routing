import { useEffect } from 'react'
import { CircleMarker, MapContainer, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import type { LatLngBoundsExpression } from 'leaflet'
import type { Checkpoint, Place, Risk, Route } from './api'
import { riskColor, riskLabel } from './format'

interface Props {
  routes: Route[]
  origin: Place | null
  destination: Place | null
  selectedRouteId: number | null
  selectedCheckpoint: number | null
  riskOf: (checkpoint: Checkpoint) => Risk | null // risk at the time the map is showing
  onSelectRoute: (id: number) => void
  onSelectCheckpoint: (index: number) => void
}

function FitBounds({ routes }: { routes: Route[] }) {
  const map = useMap()
  useEffect(() => {
    const points = routes.flatMap((route) => route.geometry)
    if (points.length) map.fitBounds(points as LatLngBoundsExpression, { padding: [24, 24] })
  }, [map, routes])
  return null
}

export default function RouteMap(props: Props) {
  const { routes, origin, destination, selectedRouteId, selectedCheckpoint, riskOf } = props
  const selected = routes.find((route) => route.id === selectedRouteId)
  // Draw unselected routes first so the selected one sits on top.
  const ordered = [...routes].sort((a, b) => Number(a.id === selectedRouteId) - Number(b.id === selectedRouteId))

  return (
    <MapContainer className="map" center={[39.5, -98.35]} zoom={4}>
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds routes={routes} />

      {/* Risk corridor: each checkpoint's stretch of road, colored by its risk. Grey dashed = no forecast. */}
      {ordered.flatMap((route) => {
        const isSelected = route.id === selectedRouteId
        return route.checkpoints.map((checkpoint, index) => {
          const risk = riskOf(checkpoint)
          return (
            <Polyline
              key={`${route.id}-${index}`}
              positions={checkpoint.path}
              pathOptions={{
                color: riskColor(risk),
                weight: isSelected ? 7 : 4,
                opacity: isSelected ? 0.95 : 0.55,
                dashArray: risk ? undefined : '6 6',
              }}
              eventHandlers={{ click: () => props.onSelectRoute(route.id) }}
            />
          )
        })
      })}

      {selected?.checkpoints.map((checkpoint, index) => {
        const risk = riskOf(checkpoint)
        return (
          <CircleMarker
            key={`${selected.id}-${index}`}
            center={[checkpoint.lat, checkpoint.lon]}
            radius={index === selectedCheckpoint ? 9 : 6}
            pathOptions={{
              color: index === selectedCheckpoint ? '#212529' : '#fff',
              weight: 2,
              fillColor: riskColor(risk),
              fillOpacity: 1,
            }}
            eventHandlers={{ click: () => props.onSelectCheckpoint(index) }}
          >
            <Tooltip>Mile {Math.round(checkpoint.distance_miles)}: {riskLabel(risk)}</Tooltip>
          </CircleMarker>
        )
      })}

      {[origin && { place: origin, label: 'Origin' }, destination && { place: destination, label: 'Destination' }]
        .filter((end) => end !== null)
        .map(({ place, label }) => (
          <CircleMarker
            key={label}
            center={[place.lat, place.lon]}
            radius={10}
            pathOptions={{ color: '#212529', weight: 3, fillColor: '#fff', fillOpacity: 1 }}
          >
            <Tooltip permanent direction="top" offset={[0, -10]}>{label}: {place.label}</Tooltip>
          </CircleMarker>
        ))}
    </MapContainer>
  )
}
