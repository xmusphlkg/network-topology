import type {
  CableLink,
  Device,
  Port,
  PortSeries,
  SyncRun,
  SyncStatus,
  TopologyGraph,
  TopologySummary,
  ZabbixDiscoveredDevice,
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

type PortQueryParams = {
  deviceId?: number;
  topologyId?: number;
  status?: string;
  includeStale?: boolean;
  search?: string;
  q?: string;
  limit?: number;
  offset?: number;
};

export const api = {
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
  discoveredZabbixDevices: (topologyId?: number) =>
    request<ZabbixDiscoveredDevice[]>(`/api/zabbix/discovered-devices${topologyId ? `?topologyId=${topologyId}` : ''}`),
  importZabbixToTopology: (topologyId: number, hostids: string[]) =>
    request<TopologySummary>(`/api/topologies/${topologyId}/sync-and-import`, {
      method: 'POST',
      body: JSON.stringify({ hostids }),
    }),
  exportTopologyJson: (topologyId: number) => request<Record<string, unknown>>(`/api/topologies/${topologyId}/json-export`),
  importTopologyJson: (topologyId: number, payload: Record<string, unknown>) =>
    request<TopologySummary>(`/api/topologies/${topologyId}/json-import`, {
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
  updateDevice: (id: number, payload: Partial<Device>) => request<Device>(`/api/devices/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteDevice: (id: number) => request<{ ok: boolean }>(`/api/devices/${id}`, { method: 'DELETE' }),
  ports: (params: PortQueryParams = {}) => request<Port[]>(`/api/ports${queryString(params)}`),
  devicePorts: (id: number) => request<Port[]>(`/api/devices/${id}/ports`),
  createPort: (deviceId: number, payload: Partial<Port> & { name: string }) =>
    request<Port>(`/api/devices/${deviceId}/ports`, { method: 'POST', body: JSON.stringify(payload) }),
  updatePort: (id: number, payload: Partial<Port>) => request<Port>(`/api/ports/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deletePort: (id: number) => request<{ ok: boolean }>(`/api/ports/${id}`, { method: 'DELETE' }),
  portSeries: (id: number, range: string) => request<PortSeries>(`/api/ports/${id}/series?range=${range}`),
  createCable: (payload: { endpointAPortId: number; endpointBPortId: number; label?: string | null; cableNo?: string | null; color?: string | null; notes?: string | null }) =>
    request<CableLink>('/api/cable-links', { method: 'POST', body: JSON.stringify(payload) }),
  updateCable: (id: number, payload: Partial<CableLink>) => request<CableLink>(`/api/cable-links/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteCable: (id: number) => request<{ ok: boolean }>(`/api/cable-links/${id}`, { method: 'DELETE' }),
  syncStatus: () => request<SyncStatus>('/api/sync/status'),
  syncRuns: (limit = 8) => request<SyncRun[]>(`/api/sync/runs?limit=${limit}`),
  runSync: (topologyId?: number) =>
    request<SyncRun>(`/api/sync/zabbix/run${topologyId ? `?topologyId=${topologyId}` : ''}`, { method: 'POST' }),
};
