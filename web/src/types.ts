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
  virtual: boolean;
  alias?: string | null;
  operStatus: string;
  adminStatus: string;
  speedMbps?: number | null;
  media?: string | null;
  macAddress?: string | null;
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

export interface PortPage {
  items: Port[];
  total: number;
  limit: number;
  offset: number;
}

export interface CableLink {
  id: number;
  endpointAPortId: number;
  endpointBPortId: number;
  label?: string | null;
  cableNo?: string | null;
  vlanId?: number | null;
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

export interface DeviceProfilePort {
  name: string;
  media: string;
  speedMbps: number | null;
  role: string;
  row: number;
  order: number;
}

export interface DeviceProfile {
  key: string;
  models: string[];
  portCount: number;
  ports: DeviceProfilePort[];
}

export interface IngestPortPayload {
  name: string;
  ifIndex?: number | null;
  alias?: string | null;
  operStatus?: string | null;
  adminStatus?: string | null;
  speedMbps?: number | null;
  media?: string | null;
  macAddress?: string | null;
  portRole?: string | null;
  vlanSummary?: string | null;
  poeStatus?: string | null;
  lastTrafficInBps?: number | null;
  lastTrafficOutBps?: number | null;
  rxErrors?: number | null;
  txErrors?: number | null;
}

export interface IngestEndpointPayload {
  deviceId?: number | null;
  zabbixHostid?: string | null;
  mgmtIp?: string | null;
  displayName?: string | null;
  portName?: string | null;
  ifIndex?: number | null;
  macAddress?: string | null;
}

export interface IngestCablePayload {
  endpointA: IngestEndpointPayload;
  endpointB: IngestEndpointPayload;
  cableNo?: string | null;
  label?: string | null;
  vlanId?: number | null;
  notes?: string | null;
  color?: string | null;
  verifiedAt?: string | null;
}

export interface IngestDevicePayload {
  displayName: string;
  role: 'switch' | 'server' | 'custom' | string;
  mgmtIp?: string | null;
  zabbixHostid?: string | null;
  model?: string | null;
  status?: string | null;
  health?: string | null;
  lastSeenAt?: string | null;
  source?: string;
  enabled?: boolean;
  strictPhysicalPorts?: boolean;
  ports: IngestPortPayload[];
}

export interface IngestPayload {
  source?: string;
  topologyId?: number | null;
  strictPhysicalPorts?: boolean;
  physicalPortNamePatterns?: string[];
  maxPhysicalPortsPerDevice?: number | null;
  devices: IngestDevicePayload[];
  cables: IngestCablePayload[];
}

export interface IngestResult {
  devices: number;
  ports: number;
  cables: number;
}

export interface IpAddrIngestPayload {
  displayName: string;
  output: string;
  topologyId?: number | null;
  mgmtIp?: string | null;
  source?: string;
  strictPhysicalPorts?: boolean;
  physicalPortNamePatterns?: string[];
}

export interface ZabbixDiscoveredDevice {
  zabbixHostid: string;
  displayName: string;
  role: string;
  model?: string | null;
  mgmtIp?: string | null;
  portCount: number;
  synced: boolean;
  action?: 'new' | 'update' | 'synced';
  existingDeviceId?: number | null;
  changes?: Array<{ field: string; current?: string | number | boolean | null; incoming?: string | number | boolean | null }>;
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
  details?: Record<string, unknown> | null;
}

export interface SyncStatus {
  latest?: SyncRun | null;
  zabbixConfigured: boolean;
  readOnly?: boolean;
}

export interface ImportDryRun {
  valid: boolean;
  devices: number;
  ports: number;
  cableLinks: number;
  layouts: number;
  existingDevices: number;
  newDevices: number;
  warnings: string[];
}

export interface QualityIssue {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  category: string;
  title: string;
  message: string;
  deviceId?: number | null;
  portId?: number | null;
  linkId?: number | null;
  topologyId?: number | null;
}

export interface AuditLog {
  id: number;
  actor?: string | null;
  action: string;
  resourceType: string;
  resourceId?: string | null;
  details?: Record<string, unknown> | null;
  createdAt: string;
}
