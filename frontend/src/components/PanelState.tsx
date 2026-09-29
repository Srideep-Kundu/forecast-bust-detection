import { AlertTriangle, Info, Loader2 } from 'lucide-react';

interface PanelStateProps {
  kind: 'loading' | 'empty' | 'error';
  title?: string;
  message?: string;
  tall?: boolean;
}

export function PanelState({ kind, title, message, tall = false }: PanelStateProps) {
  if (kind === 'loading') {
    return (
      <div
        className={`bg-white rounded-xl border border-[#1f2a1d]/10 p-8 flex flex-col items-center justify-center text-center gap-3 ${
          tall ? 'min-h-[380px]' : 'min-h-[160px]'
        }`}
        aria-label={title ?? 'Loading'}
        aria-busy="true"
      >
        <Loader2 className="w-6 h-6 text-[#336443] animate-spin" />
        <strong className="text-sm font-medium text-[#1f2a1d]">{title ?? 'Loading data...'}</strong>
        <p className="text-xs text-[#4b5b47] max-w-xs">{message ?? 'Retrieving verified meteorological records.'}</p>
      </div>
    );
  }

  if (kind === 'error') {
    return (
      <div
        className={`cds--inline-notification bg-amber-50/50 rounded-xl border border-[#8c3b24]/20 p-6 flex items-start gap-3 ${
          tall ? 'min-h-[240px]' : ''
        }`}
        role="alert"
      >
        <AlertTriangle className="w-5 h-5 text-[#8c3b24] shrink-0 mt-0.5" />
        <div className="flex flex-col gap-1">
          <strong className="text-sm font-semibold text-[#8c3b24]">{title ?? 'Unable to load'}</strong>
          <p className="text-xs text-[#4b5b47]">{message ?? 'Please check network connection or verify API service.'}</p>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`cds--inline-notification bg-[#f8faf7] rounded-xl border border-[#1f2a1d]/10 p-6 flex items-start gap-3 ${
        tall ? 'min-h-[240px]' : ''
      }`}
    >
      <Info className="w-5 h-5 text-[#85AB8B] shrink-0 mt-0.5" />
      <div className="flex flex-col gap-1">
        <strong className="text-sm font-semibold text-[#1f2a1d]">{title ?? 'Nothing to show'}</strong>
        <p className="text-xs text-[#4b5b47]">{message ?? 'Select an option to inspect details.'}</p>
      </div>
    </div>
  );
}
