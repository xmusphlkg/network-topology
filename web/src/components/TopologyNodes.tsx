import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Box, Network, Server } from 'lucide-react';
import type { Device, Port } from '../types';
import { PortMatrix } from './PortMatrix';
import { StatusPill } from './StatusPill';

type NodeData = {
  device: Device;
  ports: Port[];
  selectedPortId?: number | null;
  highlighted?: boolean;
  onPortClick?: (port: Port) => void;
};

export function SwitchNode({ data }: NodeProps & { data: NodeData }) {
  const ports = data.ports || [];
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
      <PortMatrix ports={ports} selectedPortId={data.selectedPortId} onSelect={data.onPortClick} compact />
      {ports.map((port, index) => (
        <Handle
          key={port.id}
          id={`port-${port.id}`}
          type="source"
          position={Position.Right}
          style={{ top: 54 + (index % Math.max(ports.length, 1)) * 2, opacity: 0 }}
        />
      ))}
    </div>
  );
}

export function EndpointNode({ data }: NodeProps & { data: NodeData }) {
  const ports = data.ports || [];
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
      <div className="endpoint-ports">
        {ports.map((port) => (
          <button
            key={port.id}
            className={`endpoint-port ${port.operStatus === 'up' ? 'up' : ''} ${data.selectedPortId === port.id ? 'selected' : ''}`}
            onClick={() => data.onPortClick?.(port)}
            title={[port.name, port.vlanSummary ? `VLAN ${port.vlanSummary}` : '', port.alias || ''].filter(Boolean).join(' · ')}
          >
            {port.name}
          </button>
        ))}
      </div>
      {ports.map((port, index) => (
        <Handle
          key={port.id}
          id={`port-${port.id}`}
          type="target"
          position={Position.Left}
          style={{ top: 52 + index * 22, opacity: 0 }}
        />
      ))}
    </div>
  );
}

function deviceSubtitle(device: Device) {
  const model = (device.model || '').trim();
  if (model && !['null', 'none', 'unknown'].includes(model.toLowerCase())) {
    return model;
  }
  return device.mgmtIp || device.role || '-';
}
