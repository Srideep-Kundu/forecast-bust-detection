import { useEffect, useMemo, useRef } from 'react';
import * as echarts from 'echarts/core';
import { BarChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { ArrowUpRight, ArrowDownRight } from 'lucide-react';
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
      grid: { left: 160, right: 36, top: 12, bottom: 28 },
      tooltip: {
        trigger: 'item',
        backgroundColor: '#1f2a1d',
        borderColor: '#3d5638',
        textStyle: { color: '#ffffff', fontFamily: 'Neue Haas Grotesk Text Pro, sans-serif', fontSize: 12 },
        formatter: (parameter: { dataIndex: number }) => {
          const driver = drivers[parameter.dataIndex];
          return `<div style="padding: 2px;">` +
            `<strong style="color: #85AB8B;">${driver.display_name}</strong><br/>` +
            `<span style="font-size: 11px;">Observed Value: <strong>${driver.value}${driver.unit ? ` ${driver.unit}` : ''}</strong></span><br/>` +
            `<span style="font-size: 11px;">SHAP Impact: <strong>${formatContribution(driver.shap_value)}</strong></span><br/>` +
            `<small style="font-size: 10px; opacity: 0.85;">${driver.interpretation}</small>` +
            `</div>`;
        },
      },
      xAxis: {
        type: 'value',
        name: 'SHAP contribution',
        nameLocation: 'middle',
        nameGap: 20,
        axisLine: { lineStyle: { color: '#85AB8B' } },
        splitLine: { lineStyle: { color: '#eef4ed' } },
        axisLabel: { color: '#4b5b47', fontFamily: 'IBM Plex Mono, monospace', fontSize: 10 },
      },
      yAxis: {
        type: 'category',
        data: drivers.map((driver) => driver.display_name),
        axisLine: { lineStyle: { color: '#85AB8B' } },
        axisLabel: { width: 148, overflow: 'truncate', color: '#1f2a1d', fontSize: 11 },
      },
      series: [{
        type: 'bar',
        data: drivers.map((driver) => ({
          value: driver.shap_value,
          itemStyle: {
            color: driver.shap_value >= 0 ? '#8c3b24' : '#336443',
            borderRadius: [0, 4, 4, 0],
          },
        })),
        barMaxWidth: 16,
      }],
    });
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(chartRef.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [drivers]);

  return (
    <div className="flex flex-col gap-6">
      <div
        ref={chartRef}
        className="w-full h-64 bg-[#f8faf7] rounded-lg border border-[#1f2a1d]/10 p-2"
        role="img"
        aria-label="SHAP contributions that increase or decrease predicted bust risk"
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <DriverList title="Increases predicted bust risk" drivers={positive} tone="increase" />
        <DriverList title="Decreases predicted bust risk" drivers={negative} tone="decrease" />
      </div>
    </div>
  );
}

function DriverList({ title, drivers, tone }: { title: string; drivers: ShapDriver[]; tone: 'increase' | 'decrease' }) {
  const isIncrease = tone === 'increase';
  return (
    <section
      className={`driver-list driver-list--${tone} rounded-lg p-4 border ${
        isIncrease
          ? 'bg-amber-50/40 border-amber-200/70'
          : 'bg-[#eef4ed]/50 border-[#336443]/20'
      }`}
      aria-label={title}
    >
      <div className="flex items-center gap-2 mb-3">
        {isIncrease ? (
          <ArrowUpRight className="w-4 h-4 text-[#8c3b24]" />
        ) : (
          <ArrowDownRight className="w-4 h-4 text-[#336443]" />
        )}
        <h3 className={`text-xs font-semibold uppercase tracking-wider ${isIncrease ? 'text-[#8c3b24]' : 'text-[#336443]'}`}>
          {title}
        </h3>
      </div>
      {drivers.length ? (
        <ol className="flex flex-col gap-2">
          {drivers.map((driver) => (
            <li
              key={driver.feature_name}
              className="flex items-center justify-between text-xs p-2 rounded bg-white border border-[#1f2a1d]/10"
            >
              <div className="flex flex-col">
                <strong className="text-[#1f2a1d] font-medium">{driver.display_name}</strong>
                <small className="text-[#4b5b47] font-mono">
                  {driver.value}
                  {driver.unit ? ` ${driver.unit}` : ''}
                </small>
              </div>
              <code className={`font-mono font-semibold px-1.5 py-0.5 rounded text-[11px] ${
                isIncrease ? 'bg-amber-100 text-[#8c3b24]' : 'bg-[#eef4ed] text-[#336443]'
              }`}>
                {formatContribution(driver.shap_value)}
              </code>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-xs text-[#4b5b47] italic">No contributions in this direction.</p>
      )}
    </section>
  );
}
