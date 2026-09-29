import { Activity, CloudOff } from 'lucide-react';
import type { HealthResponse } from '../api/types';

interface DashboardHeaderProps {
  health?: HealthResponse;
  isError: boolean;
}

export function DashboardHeader({ health, isError }: DashboardHeaderProps) {
  const online = health?.status === 'ok' && !isError;
  return (
    <header className="sticky top-0 z-40 w-full bg-white/95 backdrop-blur-md border-b border-[#1f2a1d]/10 px-4 sm:px-8 py-3.5 flex items-center justify-between transition-all">
      <div className="flex items-center gap-4">
        <a href="#main-content" className="flex items-center gap-2.5 text-[#1f2a1d] font-semibold text-lg tracking-tight">
          <span className="w-2.5 h-2.5 rounded-full bg-[#336443]" />
          <span>BustWatch</span>
          <span className="text-xs font-normal text-[#4b5b47] px-2 py-0.5 rounded bg-[#eef4ed] border border-[#336443]/15">
            NCMRWF / IMD Decision Support
          </span>
        </a>
        <div className="hidden md:flex items-center gap-2 text-xs text-[#4b5b47]">
          <span className="inline-flex items-center px-2 py-0.5 rounded bg-[#1f2a1d]/5 font-mono">
            Historical Replay
          </span>
          {health?.model_version ? (
            <span className="font-mono text-[#4b5b47]">{health.model_version}</span>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-3 sm:gap-4">
        <div
          className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border ${
            online
              ? 'bg-[#eef4ed] text-[#336443] border-[#336443]/20'
              : 'bg-red-50 text-red-700 border-red-200'
          }`}
          role="status"
        >
          {online ? <Activity className="w-3.5 h-3.5 text-[#336443]" /> : <CloudOff className="w-3.5 h-3.5 text-red-600" />}
          <span className="hidden sm:inline">{online ? 'API Online' : 'API Offline'}</span>
        </div>
      </div>
    </header>
  );
}
