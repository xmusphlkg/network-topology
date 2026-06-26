import { Handle, Position } from '@xyflow/react';
import { useMemo, type MouseEvent } from 'react';
import type { Port } from '../types';
import { speed } from '../lib/format';
import { isVirtualPortName } from '../lib/portFilters';

interface Props {
  ports: Port[];
  selectedPortId?: number | null;
  candidatePortId?: number | null;
  onSelect?: (port: Port, event?: MouseEvent<HTMLButtonElement>) => void;
  compact?: boolean;
  columns?: number | null;
  rows?: 1 | 2;
  arrangement?: 'sequential' | 'odd-even' | 'server';
  hideVirtual?: boolean;
  labelMode?: 'name' | 'number';
  flowHandles?: boolean;
  linkedPortIds?: readonly number[];
}

export function PortMatrix({
  ports,
  selectedPortId,
  candidatePortId,
  onSelect,
  compact = false,
  columns,
  rows = 2,
  arrangement = 'sequential',
  hideVirtual = false,
  labelMode = 'name',
  flowHandles = false,
  linkedPortIds = [],
}: Props) {
  const visiblePorts = hideVirtual ? ports.filter((port) => !isVirtualPortName(port.name)) : ports;
  const sorted = arrangePorts(visiblePorts, arrangement);
  const gridColumns = resolveGridColumns(sorted.length, rows, columns);
  const linkedPortIdSet = useMemo(() => new Set(linkedPortIds), [linkedPortIds]);
  return (
    <div className="port-matrix-scroll">
      <div
        className={`port-matrix ${compact ? 'compact' : ''} rows-${rows} arrangement-${arrangement}`}
        style={{
          gridTemplateColumns: `repeat(${gridColumns}, minmax(var(--port-cell-min), max-content))`,
          gridTemplateRows: `repeat(${rows}, auto)`,
          gridAutoFlow: arrangement === 'odd-even' ? 'column' : 'row',
        }}
      >
        {sorted.map((port) => {
          const showFlowHandles = flowHandles && linkedPortIdSet.has(port.id);
          return (
            <div className="port-cell-wrap" key={port.id}>
              {showFlowHandles ? (
                <>
                  <Handle
                    id={`port-${port.id}-top`}
                    type="target"
                    position={Position.Top}
                    isConnectable={false}
                    className="port-flow-handle port-flow-handle-top port-flow-handle-target"
                  />
                  <Handle
                    id={`port-${port.id}-bottom`}
                    type="target"
                    position={Position.Bottom}
                    isConnectable={false}
                    className="port-flow-handle port-flow-handle-bottom port-flow-handle-target"
                  />
                </>
              ) : null}
              <button
                className={`port-cell nodrag nopan ${portTone(port)} ${selectedPortId === port.id ? 'selected' : ''} ${candidatePortId === port.id ? 'candidate' : ''}`}
                title={[port.name, port.operStatus, speed(port.speedMbps), port.macAddress || '', port.vlanSummary ? `VLAN ${port.vlanSummary}` : '', port.alias || ''].filter(Boolean).join(' · ')}
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect?.(port, event);
                }}
                onDoubleClick={(event) => event.stopPropagation()}
              >
                <span>{portLabel(port.name, labelMode)}</span>
              </button>
              {showFlowHandles ? (
                <>
                  <Handle
                    id={`port-${port.id}-top`}
                    type="source"
                    position={Position.Top}
                    isConnectable={false}
                    className="port-flow-handle port-flow-handle-top port-flow-handle-source"
                  />
                  <Handle
                    id={`port-${port.id}-bottom`}
                    type="source"
                    position={Position.Bottom}
                    isConnectable={false}
                    className="port-flow-handle port-flow-handle-bottom port-flow-handle-source"
                  />
                </>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function portLabel(name: string, labelMode: 'name' | 'number') {
  if (labelMode === 'name') return name;
  const text = name.trim();
  const match = text.match(/(\d+)(?!.*\d)/);
  return match?.[1] || text;
}

function resolveGridColumns(portCount: number, rows: 1 | 2, columns?: number | null) {
  if (typeof columns === 'number' && Number.isFinite(columns) && columns > 0) {
    return Math.max(1, Math.ceil(columns));
  }
  if (rows === 1) return Math.max(1, portCount);
  return Math.max(1, Math.ceil(portCount / 2));
}

export function arrangePorts(ports: Port[], arrangement: Props['arrangement'] = 'sequential') {
  const sorted = [...ports].sort(arrangement === 'server' ? serverPortCompare : portCompare);
  return sorted;
}

export function portCompare(a: Port, b: Port) {
  return portOrder(a.name) - portOrder(b.name) || a.name.localeCompare(b.name);
}

function portOrder(name: string) {
  const number = lastPortNumber(name) ?? 999;
  const upper = name.toUpperCase();
  const prefix = upper.startsWith('Q') ? 400 : upper.startsWith('X') ? 300 : upper.startsWith('TE') ? 250 : 100;
  return prefix + number;
}

function serverPortCompare(a: Port, b: Port) {
  return serverPortOrder(a.name) - serverPortOrder(b.name) || portCompare(a, b);
}

function serverPortOrder(name: string) {
  const text = name.toLowerCase();
  const number = lastPortNumber(text) ?? 999;
  if (/^(idrac|ipmi|bmc|ilo)/.test(text)) return 10 + number;
  if (/^(eno|em|p\d+p|ens|enp)/.test(text)) return 100 + number;
  if (/^(eth|xge|xe|te|gi|ge)/.test(text)) return 200 + number;
  return 500 + number;
}

function lastPortNumber(name: string) {
  const match = name.match(/(\d+)(?!.*\d)/);
  return match ? Number(match[1]) : null;
}

function portTone(port: Port) {
  if (port.stale) return 'stale';
  if (port.operStatus === 'shutdown') return 'closed';
  if (port.operStatus === 'down') return 'down';
  const speedTone = speedClass(port.speedMbps);
  if (port.operStatus === 'up') return speedTone;
  if (speedTone !== 'speed-low' || port.media) return `${speedTone} status-unknown`;
  return 'down';
}

function speedClass(speedMbps?: number | null) {
  if ((speedMbps || 0) >= 10000) return 'speed-high';
  if ((speedMbps || 0) >= 1000) return 'speed-mid';
  return 'speed-low';
}
