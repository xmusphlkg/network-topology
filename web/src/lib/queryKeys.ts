export const queryKeys = {
  topologies: () => ['topologies'] as const,
  topology: (topologyId?: number | null) => ['topology', { topologyId: topologyId ?? 'default' }] as const,
  devices: (params?: Record<string, unknown>) => ['devices', params || {}] as const,
  ports: (params?: Record<string, unknown>) => ['ports', params || {}] as const,
  topologySyncStatus: () => ['sync-status'] as const,
  syncRuns: (limit: number = 8) => ['sync-runs', limit] as const,
  zabbixDiscovered: (topologyId?: number | null) => ['zabbix-discovered-devices', topologyId ?? 'default'] as const,
  devicePorts: (deviceId: number) => ['device-ports', deviceId] as const,
  commandPaletteData: () => ['command-palette-data'] as const,
};

