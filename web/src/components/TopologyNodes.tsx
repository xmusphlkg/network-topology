import { useUpdateNodeInternals, type NodeProps } from '@xyflow/react';
import { useEffect, type MouseEvent } from 'react';
import { Box, Network, Server } from 'lucide-react';
import type { Device, Port } from '../types';
import { PortMatrix } from './PortMatrix';
import { StatusPill } from './StatusPill';

type NodeData = {
  device: Device;
  ports: Port[];
  selectedPortId?: number | null;
  candidatePortId?: number | null;
  highlighted?: boolean;
  onPortClick?: (port: Port, event?: MouseEvent<HTMLButtonElement>) => void;
  portLayoutColumns?: number | null;
  portLayoutRows?: 1 | 2;
  portLayoutArrangement?: 'sequential' | 'odd-even' | 'server';
  hideVirtualPorts?: boolean;
  compact?: boolean;
  linkedPortIds?: readonly number[];
};

export function SwitchNode({ id, data }: NodeProps & { data: NodeData }) {
  const ports = data.ports || [];
  useRefreshPortHandles(String(id), data);
  const upPorts = ports.filter((port) => port.operStatus === 'up').length;
  return (
    <div className={`topology-node switch-node ${data.highlighted ? 'highlighted-node' : ''}`}>
      <div className="node-head">
        <Network size={16} />
        <div>
          <strong>{data.device.displayName}</strong>
          <small>{deviceSubtitle(data.device)}</small>
        </div>
        <StatusPill value={data.device.health} />
      </div>
      <div className="node-facts">
        <span>{data.device.mgmtIp || '-'}</span>
        <span>{upPorts}/{ports.length} up</span>
      </div>
      <PortMatrix
        ports={ports}
        selectedPortId={data.selectedPortId}
        candidatePortId={data.candidatePortId}
        onSelect={data.onPortClick}
        compact={data.compact}
        columns={data.portLayoutColumns}
        rows={data.portLayoutRows}
        arrangement={data.portLayoutArrangement}
        hideVirtual={data.hideVirtualPorts}
        labelMode="number"
        flowHandles
        linkedPortIds={data.linkedPortIds}
      />
    </div>
  );
}

export function EndpointNode({ id, data }: NodeProps & { data: NodeData }) {
  const ports = data.ports || [];
  useRefreshPortHandles(String(id), data);
  const Icon = data.device.role === 'server' ? Server : Box;
  const upPorts = ports.filter((port) => port.operStatus === 'up').length;
  return (
    <div className={`topology-node endpoint-node ${data.device.role === 'server' ? 'server-node' : 'custom-node'} ${data.highlighted ? 'highlighted-node' : ''}`}>
      <div className="node-head">
        <Icon size={16} />
        <div>
          <strong>{data.device.displayName}</strong>
          <small>{deviceSubtitle(data.device)}</small>
        </div>
        <StatusPill value={data.device.health} />
      </div>
      <div className="node-facts">
        <span>{data.device.mgmtIp || '-'}</span>
        <span>{upPorts}/{ports.length} up</span>
      </div>
      <PortMatrix
        ports={ports}
        selectedPortId={data.selectedPortId}
        candidatePortId={data.candidatePortId}
        onSelect={data.onPortClick}
        compact
        columns={data.portLayoutColumns}
        rows={data.portLayoutRows}
        arrangement={data.portLayoutArrangement}
        hideVirtual={data.hideVirtualPorts ?? true}
        labelMode={data.device.role === 'server' ? 'name' : 'number'}
        flowHandles
        linkedPortIds={data.linkedPortIds}
      />
    </div>
  );
}

function useRefreshPortHandles(nodeId: string, data: NodeData) {
  const updateNodeInternals = useUpdateNodeInternals();
  const ports = data.ports || [];
  const signature = [
    ports.map((port) => port.id).join(','),
    data.portLayoutColumns ?? '',
    data.portLayoutRows ?? '',
    data.portLayoutArrangement ?? '',
    data.hideVirtualPorts ?? '',
    data.compact ?? '',
    data.linkedPortIds?.join(',') ?? '',
  ].join('|');

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => updateNodeInternals(nodeId));
    return () => window.cancelAnimationFrame(frame);
  }, [nodeId, signature, updateNodeInternals]);
}

function deviceSubtitle(device: Device) {
  const model = (device.model || '').trim();
  if (model && !['null', 'none', 'unknown'].includes(model.toLowerCase())) {
    return model;
  }
  return device.mgmtIp || device.role || '-';
}
