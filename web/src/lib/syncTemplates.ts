import type { IngestPayload } from '../types';

export interface SyncTemplate {
  key: string;
  label: string;
  title: string;
  strictPhysicalPorts: boolean;
  physicalPortNamePatterns: string[];
  maxPhysicalPortsPerDevice: number | null;
}

export const syncPushBasePayload: Omit<IngestPayload, 'devices' | 'cables'> = {
  source: 'agent',
  topologyId: null,
  strictPhysicalPorts: true,
  physicalPortNamePatterns: ['ge', 'xe', 'xge', 'eth', 'eno', 'ens', 'enp', 'enx', 'em', 'idrac', 'ipmi', 'bmc', 'ilo'],
  maxPhysicalPortsPerDevice: null,
};

export const syncPushTemplates: SyncTemplate[] = [
  {
    key: 'agent-default',
    label: '默认',
    title: '默认模板（不限制端口）',
    strictPhysicalPorts: true,
    physicalPortNamePatterns: ['ge', 'xe', 'xge', 'eth', 'eno', 'ens', 'enp', 'enx', 'em', 'idrac', 'ipmi', 'bmc', 'ilo'],
    maxPhysicalPortsPerDevice: null,
  },
  {
    key: 'agent-ikuai',
    label: 'iKuai',
    title: 'iKuai 常见模板（过滤虚拟口 + 限制端口数量）',
    strictPhysicalPorts: true,
    physicalPortNamePatterns: ['wan', 'lan', 'ge', 'xe', 'xge', 'eth', 'te', 'ten', 'fa', 'gi'],
    maxPhysicalPortsPerDevice: 8,
  },
  {
    key: 'agent-server',
    label: '服务器',
    title: '服务器常见网口模板',
    strictPhysicalPorts: true,
    physicalPortNamePatterns: ['eno', 'eth', 'ens', 'enp', 'enx', 'em', 'p', 'ib', 'bond', 'xge', 'te', 'gi', 'idrac', 'ipmi', 'bmc', 'ilo'],
    maxPhysicalPortsPerDevice: 12,
  },
] as const;

export function splitPatterns(input: string): string[] {
  return input
    .split(/[\n,]/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean)
    .filter((item, index, all) => all.indexOf(item) === index);
}

function parseMaxPhysicalPorts(input: string): number | null | undefined {
  const normalized = input.trim();
  if (!normalized) return undefined;
  const parsed = Number.parseInt(normalized, 10);
  if (!Number.isFinite(parsed) || parsed <= 0) return undefined;
  return parsed;
}

export function buildSyncPayload(
  payloadText: string,
  settings: {
    strictPhysicalPorts: boolean;
    patternText: string;
    maxPhysicalPortsPerDevice: string;
  },
): IngestPayload {
  const parsed = JSON.parse(payloadText);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error('推送数据不是标准的 JSON 对象');
  }

  const physicalPortNamePatterns = splitPatterns(settings.patternText);
  const maxPhysicalPorts = parseMaxPhysicalPorts(settings.maxPhysicalPortsPerDevice);
  const payload: IngestPayload = {
    ...syncPushBasePayload,
    ...parsed,
    devices: Array.isArray(parsed.devices) ? parsed.devices : [],
    cables: Array.isArray(parsed.cables) ? parsed.cables : [],
    strictPhysicalPorts: settings.strictPhysicalPorts,
    physicalPortNamePatterns,
  };

  if (maxPhysicalPorts == null) {
    delete payload.maxPhysicalPortsPerDevice;
  } else {
    payload.maxPhysicalPortsPerDevice = maxPhysicalPorts;
  }

  return payload;
}
