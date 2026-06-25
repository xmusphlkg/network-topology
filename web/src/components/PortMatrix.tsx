import type { Port } from '../types';
import { speed } from '../lib/format';

interface Props {
  ports: Port[];
  selectedPortId?: number | null;
  onSelect?: (port: Port) => void;
  compact?: boolean;
}

export function PortMatrix({ ports, selectedPortId, onSelect, compact = false }: Props) {
  const sorted = [...ports].sort(portCompare);
  return (
    <div className={`port-matrix ${compact ? 'compact' : ''}`}>
      {sorted.map((port) => (
        <button
          key={port.id}
          className={`port-cell ${portTone(port)} ${selectedPortId === port.id ? 'selected' : ''}`}
          title={[port.name, port.operStatus, speed(port.speedMbps), port.vlanSummary ? `VLAN ${port.vlanSummary}` : '', port.alias || ''].filter(Boolean).join(' · ')}
          onClick={() => onSelect?.(port)}
        >
          <span>{shortPortName(port.name)}</span>
        </button>
      ))}
    </div>
  );
}

function portCompare(a: Port, b: Port) {
  return portOrder(a.name) - portOrder(b.name) || a.name.localeCompare(b.name);
}

function portOrder(name: string) {
  const match = name.match(/(\d+)(?!.*\d)/);
  const number = match ? Number(match[1]) : 999;
  const prefix = name.toUpperCase().startsWith('Q') ? 300 : name.toUpperCase().startsWith('X') ? 200 : 100;
  return prefix + number;
}

function shortPortName(name: string) {
  const match = name.match(/(\d+)(?!.*\d)/);
  return match?.[1] || name.slice(0, 4);
}

function portTone(port: Port) {
  if (port.operStatus === 'up') {
    if ((port.speedMbps || 0) >= 10000) return 'speed-high';
    if ((port.speedMbps || 0) >= 1000) return 'speed-mid';
    return 'speed-low';
  }
  if (port.operStatus === 'shutdown') return 'closed';
  if (port.stale) return 'stale';
  return 'down';
}
