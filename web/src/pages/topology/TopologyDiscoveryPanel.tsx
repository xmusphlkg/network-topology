import { Check } from 'lucide-react';
import type { ZabbixDiscoveredDevice } from '../../types';
import { StatusPill } from '../../components/StatusPill';

interface Props {
  zabbixChecking: boolean;
  zabbixUnavailable: boolean;
  zabbixConfigured: boolean;
  discoveryError: string | null;
  discoveredLoading: boolean;
  discoveredFetching: boolean;
  discoveredDevices: ZabbixDiscoveredDevice[];
  syncedCount: number;
  unsyncedCount: number;
  discoveredSelection: Set<string>;
  importAllPending: boolean;
  importSelectedPending: boolean;
  onRefresh: () => void;
  onImportAll: () => void;
  onImportSelected: () => void;
  onToggleDiscovery: (hostid: string) => void;
}

export function TopologyDiscoveryPanel({
  zabbixChecking,
  zabbixUnavailable,
  zabbixConfigured,
  discoveryError,
  discoveredLoading,
  discoveredFetching,
  discoveredDevices,
  syncedCount,
  unsyncedCount,
  discoveredSelection,
  importAllPending,
  importSelectedPending,
  onRefresh,
  onImportAll,
  onImportSelected,
  onToggleDiscovery,
}: Props) {
  if (zabbixChecking) {
    return <div className="muted-note">正在检查 Zabbix 配置...</div>;
  }
  if (zabbixUnavailable) {
    return <div className="muted-note">Zabbix 未配置，发现与同步已暂停。</div>;
  }
  if (discoveryError) {
    return (
      <div className="muted-note error-text">
        <strong>Zabbix 发现失败</strong>
        <span>{discoveryError}</span>
      </div>
    );
  }
  if (discoveredLoading) {
    return <div className="muted-note">正在加载发现设备...</div>;
  }
  if (discoveredDevices.length === 0) {
    return <div className="muted-note">暂无可导入的 Zabbix 设备。</div>;
  }

  return (
    <>
      <div className="rail-meta">
        <span>已同步 <strong>{syncedCount}</strong></span>
        <span>未同步 <strong>{unsyncedCount}</strong></span>
      </div>
      <div className="rail-workspace-actions">
        <button
          type="button"
          className="text-button"
          onClick={onRefresh}
          disabled={zabbixChecking || !zabbixConfigured || discoveredFetching}
        >
          {discoveredFetching ? '刷新中...' : '刷新'}
        </button>
        <button
          type="button"
          className="text-button"
          onClick={onImportAll}
          disabled={zabbixChecking || !zabbixConfigured || discoveredFetching || unsyncedCount === 0 || importAllPending}
        >
          <Check size={16} />
          全部导入
        </button>
        <button
          type="button"
          className="text-button"
          onClick={onImportSelected}
          disabled={zabbixChecking || !zabbixConfigured || !discoveredSelection.size || importSelectedPending}
        >
          导入选中
        </button>
      </div>
      <div className="discovery-list">
        {discoveredDevices.map((item) => (
          <label className="discovery-row" key={item.zabbixHostid}>
            <input
              type="checkbox"
              checked={discoveredSelection.has(item.zabbixHostid)}
              onChange={() => onToggleDiscovery(item.zabbixHostid)}
              disabled={item.synced}
            />
            <span className="discovery-main">
              <strong>{item.displayName}</strong>
              <small title={item.model || undefined}>
                {item.model || item.mgmtIp || '-'}
                {item.changes?.length ? ` · 变更 ${item.changes.map((change) => change.field).join(', ')}` : ''}
              </small>
            </span>
            <span className="discovery-meta">
              <span>{item.role}</span>
              <span>{item.portCount} 端口</span>
              {item.action === 'update' ? <StatusPill value="warning" /> : item.synced ? <StatusPill value="ok" /> : <span>新增</span>}
            </span>
          </label>
        ))}
      </div>
    </>
  );
}
