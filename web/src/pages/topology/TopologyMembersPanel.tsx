import type { Device } from '../../types';
import { DeviceCompactCard } from '../../components/DeviceCompactCard';

interface Props {
  availableDevices: Device[];
  selectedTopologyDevices: number[];
  selectedAvailableDevices: Device[];
  filteredAvailableDevicesCount: number;
  selectableAvailableDevices: Device[];
  noPortAvailableCount: number;
  canAddTopologyDevices: boolean;
  attachDevicesPending: boolean;
  deviceSearch: string;
  onDeviceSearchChange: (value: string) => void;
  onAddTopologyDeviceToSelection: (deviceIdText: string) => void;
  onRemoveTopologyDeviceSelection: (deviceId: number) => void;
  onAddSelectedTopologyDevices: () => void;
}

export function TopologyMembersPanel({
  availableDevices,
  selectedTopologyDevices,
  selectedAvailableDevices,
  filteredAvailableDevicesCount,
  selectableAvailableDevices,
  noPortAvailableCount,
  canAddTopologyDevices,
  attachDevicesPending,
  deviceSearch,
  onDeviceSearchChange,
  onAddTopologyDeviceToSelection,
  onRemoveTopologyDeviceSelection,
  onAddSelectedTopologyDevices,
}: Props) {
  if (availableDevices.length === 0) {
    return <div className="muted-note">当前拓扑已包含全部设备。</div>;
  }

  return (
    <div className="device-picker">
      <div className="rail-workspace-actions">
        <button
          className="text-button"
          type="button"
          onClick={onAddSelectedTopologyDevices}
          disabled={!canAddTopologyDevices || attachDevicesPending}
        >
          加入 ({selectedTopologyDevices.length})
        </button>
      </div>
      <input
        className="rail-search"
        value={deviceSearch}
        onChange={(event) => onDeviceSearchChange(event.target.value)}
        placeholder="搜索设备、IP、型号"
      />
      <select
        className="rail-select"
        value=""
        onChange={(event) => onAddTopologyDeviceToSelection(event.target.value)}
        disabled={!selectableAvailableDevices.length}
        aria-label="选择可加入设备"
      >
        <option value="">{selectableAvailableDevices.length ? '从下拉栏选择设备' : '没有匹配设备'}</option>
        {selectableAvailableDevices.slice(0, 80).map((device) => (
          <option key={device.id} value={device.id}>
            {deviceOptionLabel(device)}
          </option>
        ))}
      </select>
      <div className="rail-meta compact">
        <span>匹配 <strong>{filteredAvailableDevicesCount}</strong></span>
        <span>无网口 <strong>{noPortAvailableCount}</strong></span>
      </div>
      {selectedAvailableDevices.length ? (
        <div className="selected-device-list">
          {selectedAvailableDevices.map((device) => (
            <DeviceCompactCard
              key={device.id}
              device={device}
              asButton
              title="点击移除"
              onClick={() => onRemoveTopologyDeviceSelection(device.id)}
              trailing={<em>{device.stale ? '无网口' : '待加入'}</em>}
            />
          ))}
        </div>
      ) : (
        <div className="muted-note tight">先搜索并从下拉栏选择设备。</div>
      )}
    </div>
  );
}

function deviceOptionLabel(device: Device) {
  const detail = device.mgmtIp || device.model || device.source;
  const status = device.stale ? '无网口' : device.role === 'switch' ? '交换机' : device.role === 'server' ? '服务器' : '其他';
  return [device.displayName, detail, status].filter(Boolean).join(' · ');
}
