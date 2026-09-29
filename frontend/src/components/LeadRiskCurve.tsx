import { useEffect, useRef } from 'react';
import * as echarts from 'echarts/core';
import { LineChart } from 'echarts/charts';
import { GridComponent, MarkLineComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { TrendingUp } from 'lucide-react';
import type { LeadCurveResponse } from '../api/types';
import { formatDateTime, formatProbability } from '../utils/format';

echarts.use([LineChart, GridComponent, MarkLineComponent, TooltipComponent, CanvasRenderer]);

interface LeadRiskCurveProps {
  curve: LeadCurveResponse;
  selectedLead: number;
  onSelectLead: (leadDay: number) => void;
}

export function LeadRiskCurve({ curve, selectedLead, onSelectLead }: LeadRiskCurveProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const onSelectRef = useRef(onSelectLead);
  useEffect(() => { onSelectRef.current = onSelectLead; }, [onSelectLead]);

  useEffect(() => {
    if (!chartRef.current) return;
    const chart = echarts.init(chartRef.current, undefined, { renderer: 'canvas' });
    const validTimes = new Map(curve.points.map((point) => [point.lead_day, point.valid_time]));

    chart.setOption({
      animation: !window.matchMedia('(prefers-reduced-motion: reduce)').matches,
      grid: { left: 48, right: 24, top: 28, bottom: 44 },
      tooltip: {
        trigger: 'axis',
        backgroundColor: '#1f2a1d',
        borderColor: '#3d5638',
        textStyle: { color: '#ffffff', fontFamily: 'Neue Haas Grotesk Text Pro, sans-serif', fontSize: 12 },
        formatter: (parameters: unknown) => {
          const first = (parameters as Array<{ data: [number, number] }>)[0];
          const day = first.data[0];
          const probability = first.data[1];
          const point = curve.points.find((item) => item.lead_day === day);
          return `<div style="padding: 2px;">` +
            `<strong style="color: #85AB8B;">Day ${day} Horizon</strong><br/>` +
            `<span style="font-size: 11px; opacity: 0.85;">Valid ${formatDateTime(validTimes.get(day) ?? '')}</span><br/>` +
            `<span style="font-size: 11px;">Bust Probability: <strong>${formatProbability(probability)}</strong></span><br/>` +
            `<span style="font-size: 11px;">Reliability: <strong>${formatProbability(point?.forecast_reliability ?? 0)}</strong></span>` +
            `</div>`;
        },
      },
      xAxis: {
        type: 'value',
        min: 1,
        max: 10,
        interval: 1,
        name: 'Lead Day',
        nameLocation: 'middle',
        nameGap: 26,
        axisLine: { lineStyle: { color: '#85AB8B' } },
        splitLine: { lineStyle: { color: '#eef4ed' } },
        axisLabel: { color: '#4b5b47', fontFamily: 'IBM Plex Mono, monospace', fontSize: 11 },
      },
      yAxis: {
        type: 'value',
        min: 0,
        max: 1,
        axisLine: { lineStyle: { color: '#85AB8B' } },
        splitLine: { lineStyle: { color: '#eef4ed' } },
        axisLabel: {
          color: '#4b5b47',
          fontFamily: 'IBM Plex Mono, monospace',
          fontSize: 11,
          formatter: (value: number) => `${Math.round(value * 100)}%`,
        },
      },
      series: [{
        type: 'line',
        data: curve.points.map((point) => [point.lead_day, point.bust_probability]),
        smooth: 0.2,
        symbol: 'circle',
        symbolSize: (value: [number, number]) => value[0] === selectedLead ? 12 : 7,
        lineStyle: { color: '#336443', width: 2.5 },
        itemStyle: { color: '#336443', borderColor: '#ffffff', borderWidth: 2 },
        markLine: {
          symbol: 'none',
          lineStyle: { color: '#78281f', width: 1.5, type: 'dashed' },
          data: [{ xAxis: selectedLead, label: { formatter: `Selected Day ${selectedLead}`, color: '#78281f', fontSize: 10 } }],
        },
      }],
    });

    chart.on('click', (parameters) => {
      if (Array.isArray(parameters.value) && typeof parameters.value[0] === 'number') {
        onSelectRef.current(parameters.value[0]);
      }
    });

    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(chartRef.current);
    return () => {
      observer.disconnect();
      chart.dispose();
    };
  }, [curve, selectedLead]);

  return (
    <section className="bg-white rounded-xl border border-[#1f2a1d]/10 overflow-hidden shadow-sm flex flex-col" aria-labelledby="lead-curve-title">
      <div className="p-4 border-b border-[#1f2a1d]/10 bg-[#fdfdfd]">
        <span className="text-[11px] font-mono uppercase tracking-wider text-[#85AB8B] flex items-center gap-1">
          <TrendingUp className="w-3 h-3 text-[#336443]" />
          Calibrated Trajectory
        </span>
        <h2 id="lead-curve-title" className="text-base font-semibold text-[#1f2a1d]">
          Day 1–10 Lead-Risk Curve
        </h2>
      </div>

      <div
        ref={chartRef}
        className="w-full h-[400px] lg:h-[480px] p-2"
        role="img"
        aria-label={`Bust probability by lead day for ${curve.region_name}; Day ${selectedLead} selected`}
      />

      <table className="sr-only">
        <caption>Accessible lead-risk values for {curve.region_name}</caption>
        <thead><tr><th>Lead</th><th>Valid time</th><th>Bust probability</th><th>Forecast Reliability</th></tr></thead>
        <tbody>
          {curve.points.map((point) => (
            <tr key={point.lead_day}>
              <td>Day {point.lead_day}</td>
              <td>{formatDateTime(point.valid_time)}</td>
              <td>{formatProbability(point.bust_probability)}</td>
              <td>{formatProbability(point.forecast_reliability)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
