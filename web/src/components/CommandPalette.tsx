import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { Activity, Cable, Box, GitBranch, Network, Search, Server, ServerCog, X } from 'lucide-react';
import type { Device, Port, TopologySummary } from '../types';

type PaletteItem = {
  id: string;
  label: string;
  meta: string;
  badge: string;
  keywords: string[];
  icon: ReactNode;
  action: () => void;
  kind: 'page' | 'topology' | 'device' | 'port';
};

interface Props {
  open: boolean;
  topologies: TopologySummary[];
  devices: Device[];
  ports: Port[];
  currentTopologyId?: number;
  onClose: () => void;
  onNavigate: (to: string) => void;
}

export function CommandPalette({ open, topologies, devices, ports, currentTopologyId, onClose, onNavigate }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setActiveIndex(0);
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const allItems = useMemo(() => buildItems(topologies, devices, ports, onNavigate, currentTopologyId), [
    currentTopologyId,
    devices,
    onNavigate,
    ports,
    topologies,
  ]);

  const groupedItems = useMemo(() => {
    const terms = query
      .trim()
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);

    const byKind = {
      page: [...allItems.filter((item) => item.kind === 'page')],
      topology: [...allItems.filter((item) => item.kind === 'topology')],
      device: [...allItems.filter((item) => item.kind === 'device')],
      port: [...allItems.filter((item) => item.kind === 'port')],
    };

    const match = (item: PaletteItem) => {
      if (!terms.length) return true;
      const haystack = [item.label, item.meta, item.badge, ...item.keywords].join(' ').toLowerCase();
      return terms.every((term) => haystack.includes(term));
    };

    const result: {
      page: PaletteItem[];
      topology: PaletteItem[];
      device: PaletteItem[];
      port: PaletteItem[];
    } = {
      page: byKind.page.filter(match),
      topology: byKind.topology.filter(match),
      device: byKind.device.filter(match),
      port: byKind.port.filter(match),
    };

    return {
      page: result.page,
      topology: result.topology,
      device: result.device,
      port: result.port,
    };
  }, [allItems, query]);

  const flatItems = useMemo(() => {
    return [...groupedItems.page, ...groupedItems.topology, ...groupedItems.device, ...groupedItems.port];
  }, [groupedItems]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query, open]);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        return;
      }
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose, open]);

  function choose(item: PaletteItem) {
    item.action();
    onClose();
  }

  function handleInputKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (!flatItems.length) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
      }
      return;
    }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((current) => (current + 1) % flatItems.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((current) => (current - 1 + flatItems.length) % flatItems.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      choose(flatItems[Math.max(0, Math.min(activeIndex, flatItems.length - 1))]);
    }
  }

  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div className="command-overlay" onMouseDown={onClose} role="presentation">
      <div className="command-panel" role="dialog" aria-modal="true" aria-label="快速命令" onMouseDown={(event) => event.stopPropagation()}>
        <div className="command-head">
          <label className="command-search">
            <Search size={16} />
            <input
              ref={inputRef}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={handleInputKeyDown}
              placeholder="搜索页面、拓扑、设备、端口"
            />
          </label>
          <button className="icon-button" type="button" title="关闭" onClick={onClose} aria-label="关闭命令面板">
            <X size={16} />
          </button>
        </div>

        <div className="command-summary">
          <span>{flatItems.length} 项结果</span>
          <span>Enter 执行，Esc 关闭</span>
        </div>

        <div className="command-list" role="listbox" aria-label="快速命令结果">
          {flatItems.length ? (
            <>
              <CommandSection title="页面" items={groupedItems.page} offset={0} activeIndex={activeIndex} onChoose={choose} onHover={setActiveIndex} />
              <CommandSection title="拓扑" items={groupedItems.topology} offset={groupedItems.page.length} activeIndex={activeIndex} onChoose={choose} onHover={setActiveIndex} />
              <CommandSection title="设备" items={groupedItems.device} offset={groupedItems.page.length + groupedItems.topology.length} activeIndex={activeIndex} onChoose={choose} onHover={setActiveIndex} />
              <CommandSection
                title="端口"
                items={groupedItems.port}
                offset={groupedItems.page.length + groupedItems.topology.length + groupedItems.device.length}
                activeIndex={activeIndex}
                onChoose={choose}
                onHover={setActiveIndex}
              />
            </>
          ) : (
            <div className="muted-note">没有找到匹配项。</div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}

function CommandSection({
  title,
  items,
  offset,
  activeIndex,
  onChoose,
  onHover,
}: {
  title: string;
  items: PaletteItem[];
  offset: number;
  activeIndex: number;
  onChoose: (item: PaletteItem) => void;
  onHover: (index: number) => void;
}) {
  if (!items.length) return null;
  return (
    <section>
      <h4 className="command-group-title">{title}</h4>
      {items.map((item, localIndex) => {
        const absoluteIndex = offset + localIndex;
        return (
          <button
            key={item.id}
            type="button"
            className={`command-item ${absoluteIndex === activeIndex ? 'active' : ''}`}
            role="option"
            aria-selected={absoluteIndex === activeIndex}
            onMouseEnter={() => onHover(absoluteIndex)}
            onClick={() => onChoose(item)}
          >
            <span className="command-item-icon">{item.icon}</span>
            <span className="command-item-body">
              <strong>{item.label}</strong>
              <small>{item.meta}</small>
            </span>
            <span className="command-item-badge">{item.badge}</span>
          </button>
        );
      })}
    </section>
  );
}

function buildItems(topologies: TopologySummary[], devices: Device[], ports: Port[], onNavigate: (to: string) => void, currentTopologyId?: number): PaletteItem[] {
  const topologyQuery = currentTopologyId ? `?topologyId=${currentTopologyId}` : '';
  const portScopeHint = currentTopologyId ? `（当前拓扑）` : '';

  const routeItems: PaletteItem[] = [
    {
      id: 'route-topology',
      label: '拓扑总览',
      meta: '打开拓扑工作台',
      badge: '页面',
      keywords: ['拓扑', '工作台', 'topology'],
      icon: <GitBranch size={16} />,
      kind: 'page',
      action: () => onNavigate('/topology'),
    },
    {
      id: 'route-ports',
      label: '端口列表',
      meta: `查看端口与 VLAN${portScopeHint}`,
      badge: '页面',
      keywords: ['端口', 'vlan', 'ports', currentTopologyId ? '当前拓扑' : '全部'],
      icon: <Cable size={16} />,
      kind: 'page',
      action: () => onNavigate(`/ports${topologyQuery}`),
    },
    {
      id: 'route-devices',
      label: '设备管理',
      meta: '设备台账与删除',
      badge: '页面',
      keywords: ['设备', 'devices', currentTopologyId ? '当前拓扑' : '全部'],
      icon: <ServerCog size={16} />,
      kind: 'page',
      action: () => onNavigate(`/devices${currentTopologyId ? topologyQuery : ''}`),
    },
    {
      id: 'route-sync',
      label: '同步诊断',
      meta: 'Zabbix 状态与同步',
      badge: '页面',
      keywords: ['同步', 'zabbix', 'sync'],
      icon: <Activity size={16} />,
      kind: 'page',
      action: () => onNavigate('/sync'),
    },
    {
      id: 'route-ports-up',
      label: 'up 端口',
      meta: '仅看运行中的端口',
      badge: '筛选',
      keywords: ['端口', 'up', '运行'],
      icon: <Cable size={16} />,
      kind: 'page',
      action: () => onNavigate('/ports?status=up'),
    },
    {
      id: 'route-ports-down',
      label: 'down 端口',
      meta: '仅看下线端口',
      badge: '筛选',
      keywords: ['端口', 'down', '下线'],
      icon: <Cable size={16} />,
      kind: 'page',
      action: () => onNavigate('/ports?status=down'),
    },
    {
      id: 'route-ports-stale',
      label: '过期端口',
      meta: '仅看 stale 端口',
      badge: '筛选',
      keywords: ['端口', 'stale', '过期'],
      icon: <Cable size={16} />,
      kind: 'page',
      action: () => onNavigate('/ports?status=stale'),
    },
  ];

  const topologyItems = [...topologies]
    .sort((a, b) => Number(b.isDefault) - Number(a.isDefault) || a.name.localeCompare(b.name))
    .map((topology) => ({
      id: `topology-${topology.id}`,
      label: topology.name,
      meta: topology.description || `${topology.deviceCount} 台设备`,
      badge: topology.isDefault ? '默认' : '拓扑',
      keywords: [topology.name, topology.description || '', topology.isDefault ? '默认' : '', '拓扑'],
      icon: <Network size={16} />,
      kind: 'topology' as const,
      action: () => onNavigate(`/topology?topologyId=${topology.id}`),
    }));

  const deviceItems = [...devices]
    .sort((a, b) => a.displayName.localeCompare(b.displayName))
    .map((device) => ({
      id: `device-${device.id}`,
      label: device.displayName,
      meta: [device.mgmtIp, device.model, device.role].filter(Boolean).join(' · '),
      badge: device.stale ? '过期' : device.source,
      keywords: [device.displayName, device.mgmtIp || '', device.model || '', device.role || '', device.source || ''],
      icon: device.role === 'switch' ? <Network size={16} /> : device.role === 'server' ? <Server size={16} /> : <Box size={16} />,
      kind: 'device' as const,
      action: () => onNavigate(`/devices/${device.id}`),
    }));

  const portItems = [...ports]
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((port) => ({
      id: `port-${port.id}`,
      label: `${port.name}`,
      meta: [port.alias || '', port.vlanSummary || '', port.operStatus || ''].filter(Boolean).join(' · '),
      badge: port.stale ? 'stale' : '端口',
      keywords: [port.name, port.alias || '', port.vlanSummary || '', port.macAddress || '', port.operStatus || '', port.media || ''],
      icon: <Cable size={16} />,
      kind: 'port' as const,
      action: () => onNavigate(`/devices/${port.deviceId}?portId=${port.id}`),
    }));

  return [...routeItems, ...topologyItems, ...deviceItems, ...portItems];
}
