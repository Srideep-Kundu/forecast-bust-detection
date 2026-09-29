import { Header, HeaderGlobalBar, HeaderName, Tag } from '@carbon/react';
import { CloudOffline, CloudServiceManagement } from '@carbon/icons-react';
import type { HealthResponse } from '../api/types';

interface DashboardHeaderProps {
  health?: HealthResponse;
  isError: boolean;
}

export function DashboardHeader({ health, isError }: DashboardHeaderProps) {
  const online = health?.status === 'ok' && !isError;
  return (
    <Header aria-label="Forecast Bust Detection">
      <HeaderName href="#main-content" prefix="NCMRWF / SIH">
        Forecast Bust Detection
      </HeaderName>
      <div className="header-context" aria-label="Application mode">
        <Tag type="cool-gray" size="sm">Historical Replay</Tag>
        {health ? <span className="header-context__version">{health.model_version}</span> : null}
      </div>
      <HeaderGlobalBar>
        <div className={`api-status ${online ? 'api-status--online' : 'api-status--offline'}`} role="status">
          {online ? <CloudServiceManagement size={16} /> : <CloudOffline size={16} />}
          <span>{online ? 'API ready' : 'API unavailable'}</span>
        </div>
      </HeaderGlobalBar>
    </Header>
  );
}
