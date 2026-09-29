import { useEffect, useMemo, useRef } from 'react';
import { Select, SelectItem } from '@carbon/react';
import { Map, NavigationControl, Popup, setWorkerUrl, type GeoJSONSource, type Map as MapLibreMap, type MapLayerMouseEvent } from 'maplibre-gl';
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url';
import type { RegionGeometryCollection, RegionRisk } from '../api/types';
import { formatDateTime, formatProbability } from '../utils/format';
import { joinRiskGeoJson, type RiskFeatureProperties } from '../utils/geo';
import { RiskLegend } from './RiskLegend';

setWorkerUrl(maplibreWorkerUrl);

interface RiskMapProps {
  geometry: RegionGeometryCollection;
  risks: RegionRisk[];
  selectedRegionId?: string;
  onSelectRegion: (regionId: string) => void;
}

export function RiskMap({ geometry, risks, selectedRegionId, onSelectRegion }: RiskMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const onSelectRef = useRef(onSelectRegion);
  const joined = useMemo(() => joinRiskGeoJson(geometry, risks), [geometry, risks]);
  const initialJoined = useRef(joined);

  useEffect(() => { onSelectRef.current = onSelectRegion; }, [onSelectRegion]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = new Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: { subdivisions: { type: 'geojson', data: initialJoined.current } },
        layers: [
          { id: 'background', type: 'background', paint: { 'background-color': '#f4f4f4' } },
          {
            id: 'subdivision-fill',
            type: 'fill',
            source: 'subdivisions',
            paint: {
              'fill-color': [
                'case',
                ['==', ['get', 'bust_probability'], null], '#c6c6c6',
                ['interpolate', ['linear'], ['get', 'bust_probability'], 0, '#edf5ff', 0.25, '#a6c8ff', 0.5, '#4589ff', 0.75, '#0f62fe', 1, '#001d6c'],
              ],
              'fill-opacity': 0.88,
            },
          },
          {
            id: 'subdivision-outline',
            type: 'line',
            source: 'subdivisions',
            paint: { 'line-color': '#161616', 'line-width': 0.7, 'line-opacity': 0.7 },
          },
        ],
      },
      bounds: [67, 5, 99, 39],
      fitBoundsOptions: { padding: 24 },
      attributionControl: false,
    });
    map.addControl(new NavigationControl({ showCompass: false }), 'top-right');
    const popup = new Popup({ closeButton: false, closeOnClick: false, offset: 10 });
    const handleClick = (event: MapLayerMouseEvent) => {
      const feature = event.features?.[0];
      const id = feature?.properties?.canonical_region_id as string | undefined;
      if (id) onSelectRef.current(id);
    };
    map.on('click', 'subdivision-fill', handleClick);
    map.on('mousemove', 'subdivision-fill', (event: MapLayerMouseEvent) => {
      map.getCanvas().style.cursor = 'pointer';
      const properties = event.features?.[0]?.properties as RiskFeatureProperties | undefined;
      if (!properties || properties.bust_probability === null) return;
      popup
        .setLngLat(event.lngLat)
        .setHTML(
          `<strong>${properties.region_name}</strong><br/>Day ${properties.lead_day}<br/>Bust probability ${formatProbability(Number(properties.bust_probability))}<br/>Forecast Reliability ${formatProbability(Number(properties.forecast_confidence))}<br/><small>Valid ${formatDateTime(String(properties.valid_time))}</small>`,
        )
        .addTo(map);
    });
    map.on('mouseleave', 'subdivision-fill', () => {
      map.getCanvas().style.cursor = '';
      popup.remove();
    });
    mapRef.current = map;
    return () => {
      popup.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    (map.getSource('subdivisions') as GeoJSONSource | undefined)?.setData(joined);
  }, [joined]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map?.isStyleLoaded()) return;
    map.setPaintProperty('subdivision-outline', 'line-width', [
      'case', ['==', ['get', 'canonical_region_id'], selectedRegionId ?? ''], 3.5, 0.7,
    ]);
    map.setPaintProperty('subdivision-outline', 'line-color', [
      'case', ['==', ['get', 'canonical_region_id'], selectedRegionId ?? ''], '#da1e28', '#161616',
    ]);
  }, [selectedRegionId]);

  return (
    <section className="map-panel" aria-labelledby="risk-map-title">
      <div className="panel-heading">
        <div><span className="eyebrow">36 IMD subdivisions</span><h2 id="risk-map-title">Bust probability map</h2></div>
        <Select
          id="keyboard-region-select"
          size="sm"
          labelText="Keyboard region selection"
          value={selectedRegionId ?? ''}
          onChange={(event) => onSelectRegion(event.target.value)}
        >
          <SelectItem value="" text="Select subdivision" />
          {risks.map((risk) => <SelectItem key={risk.region_id} value={risk.region_id} text={`${risk.region_name} · ${formatProbability(risk.bust_probability)}`} />)}
        </Select>
      </div>
      <div ref={containerRef} className="risk-map" role="img" aria-label="Map of calibrated forecast-bust probabilities across 36 IMD meteorological subdivisions" />
      <RiskLegend />
    </section>
  );
}
