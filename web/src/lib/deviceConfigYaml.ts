import type { Device, Port } from '../types';

export type DeviceYamlConfig = Partial<Pick<Device, 'displayName' | 'role' | 'model' | 'mgmtIp' | 'status' | 'health' | 'enabled'>>;
export type PortYamlConfig = Partial<Pick<Port, 'id' | 'name' | 'alias' | 'operStatus' | 'adminStatus' | 'speedMbps' | 'media' | 'macAddress' | 'portRole' | 'vlanSummary'>>;

export interface DeviceYamlDocument {
  device: DeviceYamlConfig;
  ports: PortYamlConfig[];
}

const editableKeys = new Set(['displayName', 'role', 'model', 'mgmtIp', 'status', 'health', 'enabled']);
const portKeys = new Set(['id', 'name', 'alias', 'operStatus', 'adminStatus', 'speedMbps', 'media', 'macAddress', 'portRole', 'vlanSummary']);

export function deviceToYaml(device: Device, ports: Port[] = []): string {
  const deviceLines = [
    `displayName: ${yamlValue(device.displayName)}`,
    `role: ${yamlValue(device.role)}`,
    `mgmtIp: ${yamlValue(device.mgmtIp || '')}`,
    `model: ${yamlValue(device.model || '')}`,
    `status: ${yamlValue(device.status || '')}`,
    `health: ${yamlValue(device.health || '')}`,
    `enabled: ${device.enabled ? 'true' : 'false'}`,
    'ports:',
  ];
  const portLines = ports.flatMap((port) => [
    `  - id: ${port.id}`,
    `    name: ${yamlValue(port.name)}`,
    `    alias: ${yamlValue(port.alias || '')}`,
    `    operStatus: ${yamlValue(port.operStatus || 'unknown')}`,
    `    adminStatus: ${yamlValue(port.adminStatus || 'unknown')}`,
    `    speedMbps: ${port.speedMbps ?? ''}`,
    `    media: ${yamlValue(port.media || '')}`,
    `    macAddress: ${yamlValue(port.macAddress || '')}`,
    `    portRole: ${yamlValue(port.portRole || '')}`,
    `    vlanSummary: ${yamlValue(port.vlanSummary || '')}`,
  ]);
  return [...deviceLines, ...portLines].join('\n');
}

export function parseDeviceYaml(input: string): DeviceYamlDocument {
  const output: DeviceYamlDocument = { device: {}, ports: [] };
  let inPorts = false;
  let currentPort: PortYamlConfig | null = null;

  for (const rawLine of input.split(/\r?\n/)) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith('#')) continue;
    if (line.trim() === 'ports:') {
      inPorts = true;
      continue;
    }

    if (inPorts) {
      const listItem = line.match(/^\s*-\s+([A-Za-z][A-Za-z0-9]*):\s*(.*)$/);
      if (listItem) {
        currentPort = {};
        output.ports.push(currentPort);
        assignPortValue(currentPort, listItem[1], listItem[2]);
        continue;
      }
      const portField = line.match(/^\s+([A-Za-z][A-Za-z0-9]*):\s*(.*)$/);
      if (portField && currentPort) {
        assignPortValue(currentPort, portField[1], portField[2]);
        continue;
      }
      if (!line.startsWith(' ')) {
        inPorts = false;
      } else {
        continue;
      }
    }

    const trimmed = line.trim();
    const separator = trimmed.indexOf(':');
    if (separator < 1) {
      throw new Error(`YAML 行缺少冒号：${rawLine}`);
    }
    const key = trimmed.slice(0, separator).trim();
    if (!editableKeys.has(key)) continue;
    const rawValue = trimmed.slice(separator + 1).trim();
    if (key === 'enabled') {
      output.device.enabled = parseYamlBoolean(rawValue);
    } else {
      const value = parseYamlString(rawValue);
      if (key === 'displayName') output.device.displayName = value;
      if (key === 'role') output.device.role = value;
      if (key === 'model') output.device.model = value || null;
      if (key === 'mgmtIp') output.device.mgmtIp = value || null;
      if (key === 'status') output.device.status = value;
      if (key === 'health') output.device.health = value;
    }
  }
  return output;
}

function assignPortValue(port: PortYamlConfig, key: string, rawValue: string) {
  if (!portKeys.has(key)) return;
  const value = parseYamlString(rawValue.trim());
  if (key === 'id') {
    const id = Number(value);
    if (Number.isFinite(id) && id > 0) port.id = id;
    return;
  }
  if (key === 'speedMbps') {
    const speed = Number(value);
    port.speedMbps = Number.isFinite(speed) && value !== '' ? speed : null;
    return;
  }
  if (key === 'name') port.name = value;
  if (key === 'alias') port.alias = value || null;
  if (key === 'operStatus') port.operStatus = value || 'unknown';
  if (key === 'adminStatus') port.adminStatus = value || 'unknown';
  if (key === 'media') port.media = value || null;
  if (key === 'macAddress') port.macAddress = value || null;
  if (key === 'portRole') port.portRole = value || null;
  if (key === 'vlanSummary') port.vlanSummary = value || null;
}

function yamlValue(value: string) {
  if (!value) return '""';
  if (/^[a-zA-Z0-9_.:/@-]+$/.test(value)) return value;
  return JSON.stringify(value);
}

function parseYamlString(value: string) {
  if (value === '""' || value === "''") return '';
  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }
  return value;
}

function parseYamlBoolean(value: string) {
  const normalized = value.toLowerCase();
  if (['true', 'yes', '1', 'on'].includes(normalized)) return true;
  if (['false', 'no', '0', 'off'].includes(normalized)) return false;
  throw new Error(`enabled 需要是 true/false：${value}`);
}
