import { InlineNotification, SkeletonPlaceholder, SkeletonText } from '@carbon/react';

interface PanelStateProps {
  kind: 'loading' | 'empty' | 'error';
  title?: string;
  message?: string;
  tall?: boolean;
}

export function PanelState({ kind, title, message, tall = false }: PanelStateProps) {
  if (kind === 'loading') {
    return (
      <div className={`panel-state panel-state--loading ${tall ? 'panel-state--tall' : ''}`} aria-label={title ?? 'Loading'} aria-busy="true">
        {tall ? <SkeletonPlaceholder className="panel-state__placeholder" /> : null}
        <SkeletonText heading width="45%" />
        <SkeletonText paragraph lineCount={3} width="85%" />
      </div>
    );
  }

  return (
    <InlineNotification
      kind={kind === 'error' ? 'error' : 'info'}
      lowContrast
      hideCloseButton
      title={title ?? (kind === 'error' ? 'Unable to load' : 'Nothing to show')}
      subtitle={message ?? ''}
    />
  );
}
