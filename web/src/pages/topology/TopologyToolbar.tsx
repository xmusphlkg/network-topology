import type { FormEvent, RefObject } from 'react';
import { Download, Link, Plus, RefreshCw, Save, Upload } from 'lucide-react';
import type { TopologySummary } from '../../types';
import { StatusPill } from '../../components/StatusPill';
import { normalizeSwitchPortLayoutKey, switchPortLayoutTemplates } from '../../lib/switchPortLayouts';

interface Props {
  topologyId: number | null;
  topologies: TopologySummary[];
  topologyName: string;
  onTopologyChange: (topologyIdText: string) => void;
  zabbixUnavailable: boolean;
  zabbixConfigured: boolean;
  runSyncPending: boolean;
  onRunSync: () => void;
  connectMode: boolean;
  onToggleConnectMode: () => void;
  switchPortLayoutKey: string;
  onSwitchPortLayoutChange: (layoutKey: string) => void;
  connectModeText: string | null;
  hasUnsavedLayout: boolean;
  onSaveLayout: () => void;
  saveLayoutPending: boolean;
  canSaveLayout: boolean;
  onExportJson: () => void;
  importTopologyPending: boolean;
  jsonImportRef: RefObject<HTMLInputElement | null>;
  onImportJsonFile: (file: File | null) => void;
  newTopologyName: string;
  onNewTopologyNameChange: (value: string) => void;
  newTopologyDefault: boolean;
  onNewTopologyDefaultChange: (value: boolean) => void;
  onSubmitTopology: (event: FormEvent) => void;
  createTopologyPending: boolean;
  stats: {
    deviceCount: number;
    switchCount: number;
    upPortCount: number;
    portCount: number;
    cableCount: number;
    availableDeviceCount: number;
    discoverySummaryText: string;
    syncStatusText: string;
    syncStatusValue: string;
  };
}

export function TopologyToolbar({
  topologyId,
  topologies,
  topologyName,
  onTopologyChange,
  zabbixUnavailable,
  zabbixConfigured,
  runSyncPending,
  onRunSync,
  connectMode,
  onToggleConnectMode,
  switchPortLayoutKey,
  onSwitchPortLayoutChange,
  connectModeText,
  hasUnsavedLayout,
  onSaveLayout,
  saveLayoutPending,
  canSaveLayout,
  onExportJson,
  importTopologyPending,
  jsonImportRef,
  onImportJsonFile,
  newTopologyName,
  onNewTopologyNameChange,
  newTopologyDefault,
  onNewTopologyDefaultChange,
  onSubmitTopology,
  createTopologyPending,
  stats,
}: Props) {
  return (
    <div className="workstation-toolbar">
      <div className="toolbar-group">
        <select
          value={topologyId ?? ''}
          onChange={(event) => onTopologyChange(event.target.value)}
          aria-label="当前拓扑"
        >
          {topologies.map((topology) => (
            <option key={topology.id} value={topology.id}>
              {topology.name}
            </option>
          ))}
        </select>
        <button
          className="icon-button"
          onClick={onRunSync}
          title={zabbixUnavailable ? 'Zabbix 未配置' : '同步并导入 Zabbix 主机'}
          disabled={!zabbixConfigured || runSyncPending}
          type="button"
        >
          <RefreshCw size={17} />
        </button>
        <button
          className={`icon-button ${connectMode ? 'is-active' : ''}`}
          onClick={onToggleConnectMode}
          title="切换连线模式"
          type="button"
        >
          <Link size={17} />
        </button>
        <label className="scope-select-wrap" title="交换机端口布局模板">
          <select
            value={switchPortLayoutKey}
            onChange={(event) => onSwitchPortLayoutChange(normalizeSwitchPortLayoutKey(event.target.value))}
            aria-label="交换机端口布局模板"
          >
            {switchPortLayoutTemplates.map((item) => (
              <option key={item.key} value={item.key} title={item.description}>
                {item.label}
              </option>
            ))}
          </select>
        </label>
        {connectModeText ? <span className="workstation-layout-state">{connectModeText}</span> : null}
        <span className={`workstation-layout-state ${hasUnsavedLayout ? 'warning' : ''}`}>
          {hasUnsavedLayout ? '布局未保存' : '布局已保存'}
        </span>
        <button
          className="icon-button"
          onClick={onSaveLayout}
          disabled={!canSaveLayout || saveLayoutPending}
          title={saveLayoutPending ? '保存中...' : '保存布局'}
          aria-label={saveLayoutPending ? '保存中...' : '保存布局'}
          type="button"
        >
          <Save size={16} />
          <span className="sr-only">{saveLayoutPending ? '保存中...' : '保存布局'}</span>
        </button>
        <button className="icon-button" onClick={onExportJson} title="导出 JSON" disabled={!topologyId} type="button">
          <Download size={17} />
        </button>
        <button
          className="icon-button"
          onClick={() => jsonImportRef.current?.click()}
          title="导入 JSON"
          disabled={!topologyId || importTopologyPending}
          type="button"
        >
          <Upload size={17} />
        </button>
        <input
          ref={jsonImportRef}
          type="file"
          accept="application/json,.json"
          hidden
          onChange={(event) => {
            onImportJsonFile(event.target.files?.[0] || null);
            event.target.value = '';
          }}
        />
      </div>
      <form className="topology-create toolbar-group" onSubmit={onSubmitTopology}>
        <input value={newTopologyName} onChange={(event) => onNewTopologyNameChange(event.target.value)} placeholder="新建拓扑名称" />
        <label>
          <input
            type="checkbox"
            checked={newTopologyDefault}
            onChange={(event) => onNewTopologyDefaultChange(event.target.checked)}
          />
          设为默认
        </label>
        <button className="icon-button" type="submit" disabled={createTopologyPending} title="新建拓扑" aria-label="新建拓扑">
          <Plus size={16} />
          <span className="sr-only">新建</span>
        </button>
      </form>
      <div className="toolbar-spacer" />
      <div className="workstation-stats">
        <span>{topologyName}</span>
        <span>{stats.deviceCount} 设备</span>
        <span>{stats.switchCount} 交换机</span>
        <span>{stats.upPortCount}/{stats.portCount} up</span>
        <span>{stats.cableCount} 线缆</span>
        <span>{stats.availableDeviceCount} 台可加入</span>
        <span>发现 {stats.discoverySummaryText}</span>
        <span className="status-inline">Zabbix {stats.syncStatusText}<StatusPill value={stats.syncStatusValue} /></span>
      </div>
    </div>
  );
}
