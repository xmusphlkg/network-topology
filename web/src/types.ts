export type Health = 'ok' | 'warning' | 'critical' | 'offline' | 'stale' | 'unknown' | string;

export interface Device {
  id: number;
  source: string;
  zabbixHostid?: string | null;
  role: 'switch' | 'server' | 'custom' | string;
  model?: string | null;
  mgmtIp?: string | null;
  displayName: string;
  status: string;
  health: Health;
  lastSeenAt?: string | null;
  stale: boolean;
  enabled: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface Port {
  id: number;
  deviceId: number;
  source: string;
  identity: string;
  ifIndex?: number | null;
  name: string;
  alias?: string | null;
  operStatus: string;
  adminStatus: string;
  speedMbps?: number | null;
  media?: string | null;
  portRole?: string | null;
  vlanSummary?: string | null;
  poeStatus?: string | null;
  lastTrafficInBps?: number | null;
  lastTrafficOutBps?: number | null;
  rxErrors?: number | null;
  txErrors?: number | null;
  stale: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface CableLink {
  id: number;
  endpointAPortId: number;
  endpointBPortId: number;
  label?: string | null;
  cableNo?: string | null;
  color?: string | null;
  notes?: string | null;
  verifiedAt?: string | null;
  createdBy?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface FlowNode {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: { device: Device; ports: Port[] };
}

export interface FlowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle: string;
  targetHandle: string;
  label?: string | null;
  style?: Record<string, unknown>;
  data?: Record<string, unknown>;
}

export interface TopologyLayout {
  topologyId?: number;
  layoutKey?: string;
  viewport?: Record<string, unknown> | null;
  nodes: Array<{
    nodeId: string;
    x: number;
    y: number;
    width?: number | null;
    height?: number | null;
    groupName?: string | null;
    hidden?: boolean;
  }>;
}

export interface TopologyGraph {
  generatedAt: string;
  topologyId: number;
  topologyName: string;
  summary?: TopologySummary;
  layout?: TopologyLayout;
  nodes: FlowNode[];
  edges: FlowEdge[];
  devices: Device[];
  ports: Port[];
  cableLinks: CableLink[];
  switchPanels: Array<{ deviceId: number; modelKey?: string | null; displayName: string; health: string; ports: Port[] }>;
}

export interface TopologySummary {
  id: number;
  name: string;
  description?: string | null;
  isDefault: boolean;
  deviceCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface ZabbixDiscoveredDevice {
  zabbixHostid: string;
  displayName: string;
  role: string;
  model?: string | null;
  mgmtIp?: string | null;
  portCount: number;
  synced: boolean;
}

export interface SeriesPoint {
  ts: number;
  inBps?: number | null;
  outBps?: number | null;
}

export interface PortSeries {
  portId: number;
  range: string;
  points: SeriesPoint[];
  error?: string | null;
}

export interface SyncRun {
  id: number;
  status: string;
  startedAt: string;
  finishedAt?: string | null;
  durationMs?: number | null;
  devicesSeen: number;
  devicesUpserted: number;
  portsUpserted: number;
  staleDevices: number;
  errorMessage?: string | null;
}

export interface SyncStatus {
  latest?: SyncRun | null;
  zabbixConfigured: boolean;
}
