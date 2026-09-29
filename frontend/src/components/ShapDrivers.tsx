import { useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import type { ShapDriver } from '../api/types';
import { formatContribution } from '../utils/format';

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

interface ShapDriversProps {
  positive: ShapDriver[];
  negative: ShapDriver[];
}

export function ShapDrivers({ positive, negative }: ShapDriversProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const drivers = useMemo(() => [...negative].reverse().concat(positive), [negative, positive]);

  useEffect(() => {
    if (!chartRef.current) return;
    const chart = echarts.init(chartRef.current, undefined, { renderer: 'canvas' });
    chart.setOption({
      animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      grid: { left: 156, right: 32, top: 8, bottom: 28 },
      tooltip: {
        trigger: 'item',
        formatter: (parameter: { dataIndex: number }) => {
          const driver = drivers[parameter.dataIndex];
          return `<strong>${driver.display_name}</strong><br/>Value ${driver.value}${driver.unit ? ` ${driver.unit}` : ''}<br/>SHAP ${formatContribution(driver.shap_value)}<br/>${driver.interpretation}`;
        },
      },
      xAxis: { type: 'value', name: 'SHAP contribution', nameLocation: 'middle', nameGap: 22 },
      yAxis: { type: 'category', data: drivers.map((driver) => driver.display_name), axisLabel: { width: 142, overflow: 'truncate' } },
      series: [{
        type: 'bar',
        data: drivers.map((driver) => ({ value: driver.shap_value, itemStyle: { color: driver.shap_value >= 0 ? '#da1e28' : '#198038' } })),
        barMaxWidth: 18,
      }],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(chartRef.current);
    return () => { observer.disconnect(); chart.dispose(); };
  }, [drivers]);

  return (
    <div>
      <div ref={chartRef} className="shap-chart" role="img" aria-label="SHAP contributions that increase or decrease predicted bust risk" />
      <div className="driver-lists">
        <DriverList title="Increases predicted bust risk" drivers={positive} tone="increase" />
        <DriverList title="Decreases predicted bust risk" drivers={negative} tone="decrease" />
      </div>
    </div>
  );
}

function DriverList({ title, drivers, tone }: { title: string; drivers: ShapDriver[]; tone: 'increase' | 'decrease' }) {
  return (
    <section className={`driver-list driver-list--${tone}`} aria-label={title}>
      <h3>{title}</h3>
      {drivers.length ? <ol>{drivers.map((driver) => (
        <li key={driver.feature_name}>
          <span><strong>{driver.display_name}</strong><small>{driver.value}{driver.unit ? ` ${driver.unit}` : ''}</small></span>
          <code>{formatContribution(driver.shap_value)}</code>
        </li>
      ))}</ol> : <p>No contributions in this direction.</p>}
    </section>
  );
}
