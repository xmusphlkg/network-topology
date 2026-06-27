import type {
  CableLink,
  Device,
  DeviceProfile,
  AuditLog,
  ImportDryRun,
  Port,
  PortPage,
  PortSeries,
  QualityIssue,
  SyncRun,
  SyncStatus,
  TopologyGraph,
  TopologySummary,
  ZabbixDiscoveredDevice,
  IngestPayload,
  IngestResult,
  IngestDevicePayload,
  IpAddrIngestPayload,
} from '../types';

const basePath = import.meta.env.BASE_URL && import.meta.env.BASE_URL !== '/' ? import.meta.env.BASE_URL.replace(/\/$/, '') : '';
const API_BASE = import.meta.env.VITE_API_BASE || basePath;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers || {}),
    },
  });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = errorMessage(body, message);
    } catch {
      // keep default
    }
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

function errorMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== 'object') return fallback;
  const detail = 'detail' in body ? (body as { detail?: unknown }).detail : undefined;
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== 'object') return '';
        const record = item as { loc?: unknown; msg?: unknown };
        const path = Array.isArray(record.loc) ? record.loc.filter((part) => part !== 'body').join('.') : '';
        const msg = typeof record.msg === 'string' ? record.msg : '';
        return [path, msg].filter(Boolean).join(': ');
      })
      .filter(Boolean);
    if (messages.length) return messages.join('; ');
  }
  if ('message' in body && typeof (body as { message?: unknown }).message === 'string') {
    return (body as { message: string }).message;
  }
  return fallback;
}

function queryString(values: Record<string, string | number | boolean | undefined | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value === undefined || value === null || value === '') continue;
    search.set(key, String(value));
  }
  const raw = search.toString();
  return raw ? `?${raw}` : '';
}

type DeviceQueryParams = {
  role?: string;
  search?: string;
  q?: string;
  topologyId?: number;
  includeDisabled?: boolean;
};

type DevicePortQueryParams = {
  includeVirtual?: boolean;
};

type PortQueryParams = {
  deviceId?: number;
  topologyId?: number;
  status?: string;
  includeStale?: boolean;
  includeVirtual?: boolean;
  media?: string;
  speed?: string;
  search?: string;
  q?: string;
  limit?: number;
  offset?: number;
};

export const api = {
  deviceProfiles: () => request<DeviceProfile[]>('/api/device-profiles'),
  topology: (topologyId?: number) => request<TopologyGraph>(`/api/topology${topologyId ? `?topologyId=${topologyId}` : ''}`),
  topologies: () => request<TopologySummary[]>('/api/topologies'),
  createTopology: (payload: { name: string; description?: string | null; isDefault?: boolean }) =>
    request<TopologySummary>('/api/topologies', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  updateTopology: (topologyId: number, payload: { name?: string; description?: string | null; isDefault?: boolean }) =>
    request<TopologySummary>(`/api/topologies/${topologyId}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),
  assignDevicesToTopology: (topologyId: number, payload: { deviceIds: number[] }) =>
    request<TopologySummary>(`/api/topologies/${topologyId}/devices`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  removeDeviceFromTopology: (topologyId: number, deviceId: number) =>
    request<TopologySummary>(`/api/topologies/${topologyId}/devices/${deviceId}`, {
      method: 'DELETE',
    }),
  discoveredZabbixDevices: (topologyId?: number) =>
    request<ZabbixDiscoveredDevice[]>(`/api/zabbix/discovered-devices${topologyId ? `?topologyId=${topologyId}` : ''}`),
  importZabbixToTopology: (topologyId: number, hostids: string[]) =>
    request<TopologySummary>(`/api/topologies/${topologyId}/sync-and-import`, {
      method: 'POST',
      body: JSON.stringify({ hostids }),
    }),
  exportTopologyJson: (topologyId: number) => request<Record<string, unknown>>(`/api/topologies/${topologyId}/json-export`),
  dryRunImportTopologyJson: (topologyId: number, payload: Record<string, unknown>) =>
    request<ImportDryRun>(`/api/topologies/${topologyId}/json-import/dry-run`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  importTopologyJson: (topologyId: number, payload: Record<string, unknown>) =>
    request<TopologySummary>(`/api/topologies/${topologyId}/json-import`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  applyDeviceProfile: (deviceId: number, payload: { profileKey: string; replaceProfilePorts?: boolean }) =>
    request<Device>(`/api/devices/${deviceId}/apply-profile`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  syncPush: (payload: IngestPayload) =>
    request<IngestResult>('/api/sync/push', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  syncPushFromCommand: (payload: IngestPayload) =>
    request<IngestResult>('/api/sync/command-push', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  syncIpAddr: (payload: IpAddrIngestPayload) =>
    request<IngestResult>('/api/sync/ip-addr', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),
  saveLayout: (
    nodes: Array<{ nodeId: string; x: number; y: number }>,
    layoutKey = 'default',
    viewport?: Record<string, unknown> | null,
  ) =>
    request<{ ok: boolean }>('/api/topology/layout', {
      method: 'PATCH',
      body: JSON.stringify({ layoutKey, nodes, viewport }),
    }),
  devices: (params: DeviceQueryParams = {}) => request<Device[]>(`/api/devices${queryString(params)}`),
  createDevice: (payload: Partial<Device> & { displayName: string; role: string; ports?: Array<{ name: string; speedMbps?: number | null }> }) =>
    request<Device>('/api/devices', { method: 'POST', body: JSON.stringify(payload) }),
  syncPushExample: (): IngestPayload => ({
    source: 'agent',
    strictPhysicalPorts: true,
    physicalPortNamePatterns: ['wan', 'lan', 'ge', 'xe', 'xge', 'eth', 'eno', 'ens', 'enp', 'enx', 'em', 'ib', 'bond', 'ten', 'te', 'idrac', 'ipmi', 'bmc', 'ilo'],
    maxPhysicalPortsPerDevice: null,
    topologyId: null,
    devices: [
      {
        displayName: 'compute-01',
        role: 'server',
        ports: [{ name: 'ens1f0', macAddress: '52:54:00:aa:bb:cc', operStatus: 'up' }],
      },
      {
        displayName: 'tor-01',
        role: 'switch',
        ports: [{ name: 'XGE0/1', operStatus: 'up' }],
      },
    ],
    cables: [
      {
        endpointA: { displayName: 'tor-01', portName: 'XGE0/1' },
        endpointB: { macAddress: '52:54:00:aa:bb:cc' },
        vlanId: 10,
        label: 'mac-learned uplink',
      },
    ],
  }),
  updateDevice: (id: number, payload: Partial<Device>) => request<Device>(`/api/devices/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteDevice: (id: number) => request<{ ok: boolean }>(`/api/devices/${id}`, { method: 'DELETE' }),
  ports: (params: PortQueryParams = {}) => request<Port[]>(`/api/ports${queryString(params)}`),
  portsPage: (params: PortQueryParams = {}) => request<PortPage>(`/api/ports/page${queryString(params)}`),
  devicePorts: (id: number, params: DevicePortQueryParams = {}) =>
    request<Port[]>(`/api/devices/${id}/ports${queryString(params)}`),
  createPort: (deviceId: number, payload: Partial<Port> & { name: string }) =>
    request<Port>(`/api/devices/${deviceId}/ports`, { method: 'POST', body: JSON.stringify(payload) }),
  updatePort: (id: number, payload: Partial<Port>) => request<Port>(`/api/ports/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deletePort: (id: number) => request<{ ok: boolean }>(`/api/ports/${id}`, { method: 'DELETE' }),
  portSeries: (id: number, range: string) => request<PortSeries>(`/api/ports/${id}/series?range=${range}`),
  createCable: (payload: { endpointAPortId: number; endpointBPortId: number; replaceExisting?: boolean; label?: string | null; cableNo?: string | null; vlanId?: number | null; color?: string | null; notes?: string | null }) =>
    request<CableLink>('/api/cable-links', { method: 'POST', body: JSON.stringify(payload) }),
  updateCable: (id: number, payload: Partial<CableLink>) => request<CableLink>(`/api/cable-links/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteCable: (id: number) => request<{ ok: boolean }>(`/api/cable-links/${id}`, { method: 'DELETE' }),
  syncStatus: () => request<SyncStatus>('/api/sync/status'),
  syncRuns: (limit = 8) => request<SyncRun[]>(`/api/sync/runs?limit=${limit}`),
  qualityIssues: (topologyId?: number) => request<QualityIssue[]>(`/api/quality/issues${topologyId ? `?topologyId=${topologyId}` : ''}`),
  auditLogs: (limit = 50) => request<AuditLog[]>(`/api/audit-logs?limit=${limit}`),
  runSync: (topologyId?: number) =>
    request<SyncRun>(`/api/sync/zabbix/run${topologyId ? `?topologyId=${topologyId}` : ''}`, { method: 'POST' }),
};
