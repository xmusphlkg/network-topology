import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Filter, Search, Router } from 'lucide-react';
import { api } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { CopyLinkButton } from '../components/CopyLinkButton';
import { bps, speed } from '../lib/format';
import { MetricStrip } from '../components/MetricStrip';
import { StatusPill } from '../components/StatusPill';
import type { Device, Port } from '../types';

type PortStatusFilter = 'all' | 'up' | 'down' | 'shutdown' | 'stale';
type MediaFilter = 'all' | 'copper' | 'fiber' | 'virtual';
type SpeedFilter = 'all' | 'slow' | '1g' | '10g';

export function PortsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const searchQuery = searchParams.get('q') || '';
  const statusQuery = parseStatusFilter(searchParams.get('status'));
  const topologyIdQuery = Number(searchParams.get('topologyId'));
  const topologyId = Number.isFinite(topologyIdQuery) && topologyIdQuery > 0 ? topologyIdQuery : undefined;
  const mediaFilter = parseMediaFilter(searchParams.get('media'));
  const speedFilter = parseSpeedFilter(searchParams.get('speed'));
  const includeStaleQuery = searchParams.get('includeStale');
  const includeStale = includeStaleQuery === null ? true : includeStaleQuery !== 'false';
  const includeVirtualQuery = searchParams.get('includeVirtual');
  const includeVirtual = includeVirtualQuery === null ? false : includeVirtualQuery === 'true';
  const pageSize = 80;
  const offsetQuery = Number(searchParams.get('offset'));
  const offset = Number.isFinite(offsetQuery) && offsetQuery >= 0 ? offsetQuery : 0;

  const [search, setSearch] = useState(searchQuery);
  const [statusFilter, setStatusFilter] = useState<PortStatusFilter>(statusQuery);

  const topologies = useQuery({ queryKey: queryKeys.topologies(), queryFn: () => api.topologies(), staleTime: 60_000 });
  const ports = useQuery({
    queryKey: queryKeys.ports({
      topologyId,
      status: statusFilter === 'all' ? undefined : statusFilter,
      includeStale,
      includeVirtual,
      media: mediaFilter === 'all' ? undefined : mediaFilter,
      speed: speedFilter === 'all' ? undefined : speedFilter,
      search: search.trim(),
      limit: pageSize,
      offset,
    }),
    queryFn: () =>
      api.portsPage({
        topologyId,
        status: statusFilter === 'all' ? undefined : statusFilter,
        includeStale,
        includeVirtual,
        media: mediaFilter === 'all' ? undefined : mediaFilter,
        speed: speedFilter === 'all' ? undefined : speedFilter,
        search: search.trim(),
        limit: pageSize,
        offset,
      }),
  });
  const scopeDevices = useQuery({
    queryKey: queryKeys.devices({ topologyId, includeDisabled: true }),
    queryFn: () => api.devices({ topologyId, includeDisabled: true }),
  });

  const deviceById = useMemo(() => {
    const map = new Map<number, Device>();
    for (const device of scopeDevices.data || []) {
      map.set(device.id, device);
    }
    return map;
  }, [scopeDevices.data]);

  const scopeLabel = useMemo(() => {
    if (!topologyId || !topologies.data?.length) return '全部拓扑';
    return topologies.data.find((item) => item.id === topologyId)?.name || `拓扑 #${topologyId}`;
  }, [topologyId, topologies.data]);

  const scopeHint = useMemo(() => {
    const mediaHint = mediaFilter === 'all' ? '全部介质' : `介质 ${mediaFilter}`;
    const speedHint = speedFilter === 'all' ? '全部速率' : speedFilter === 'slow' ? '<1G' : `>=${speedFilter}`;
    const staleHint = includeStale ? '包含 stale' : '排除 stale';
    const statusHint = statusFilter === 'all' ? '全部状态' : statusFilter;
    const virtualHint = includeVirtual ? '含虚拟口' : '仅物理口';
    return `${scopeLabel} · ${statusHint} · ${mediaHint} · ${speedHint} · ${staleHint} · ${virtualHint}`;
  }, [scopeLabel, statusFilter, mediaFilter, speedFilter, includeStale, includeVirtual]);

  const mediaList = useMemo(() => {
    const items = new Set<string>();
    for (const port of ports.data?.items || []) {
      if (port.media) {
        items.add(port.media);
      }
    }
    return ['all', ...Array.from(items).sort()];
  }, [ports.data?.items]);

  useEffect(() => {
    setSearch(searchQuery);
  }, [searchQuery]);

  useEffect(() => {
    if (!topologyId) {
      return;
    }
    const hasTopology = (topologies.data || []).some((topology) => topology.id === topologyId);
    if (!hasTopology && topologies.data?.length) {
      const next = new URLSearchParams(searchParams);
      next.delete('topologyId');
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams, topologyId, topologies.data]);

  useEffect(() => {
    setStatusFilter(statusQuery);
  }, [statusQuery]);

  function updateSearch(value: string) {
    setSearch(value);
    const next = new URLSearchParams(searchParams);
    if (value.trim()) {
      next.set('q', value);
    } else {
      next.delete('q');
    }
    next.delete('offset');
    setSearchParams(next, { replace: true });
  }

  function updateStatusFilter(value: PortStatusFilter) {
    setStatusFilter(value);
    const next = new URLSearchParams(searchParams);
    if (value === 'all') {
      next.delete('status');
    } else {
      next.set('status', value);
    }
    next.delete('offset');
    setSearchParams(next, { replace: true });
  }

  function updateTopologyFilter(nextTopologyId: number | undefined) {
    const next = new URLSearchParams(searchParams);
    if (nextTopologyId) {
      next.set('topologyId', String(nextTopologyId));
    } else {
      next.delete('topologyId');
    }
    next.delete('offset');
    setSearchParams(next, { replace: true });
  }

  function updateIncludeStale(next: boolean) {
    const nextSearch = new URLSearchParams(searchParams);
    if (next) {
      nextSearch.delete('includeStale');
    } else {
      nextSearch.set('includeStale', 'false');
    }
    nextSearch.delete('offset');
    setSearchParams(nextSearch, { replace: true });
  }

  function updateIncludeVirtual(next: boolean) {
    const nextSearch = new URLSearchParams(searchParams);
    if (next) {
      nextSearch.set('includeVirtual', 'true');
    } else {
      nextSearch.delete('includeVirtual');
    }
    nextSearch.delete('offset');
    setSearchParams(nextSearch, { replace: true });
  }

  function updateMediaFilter(value: MediaFilter) {
    const next = new URLSearchParams(searchParams);
    if (value === 'all') {
      next.delete('media');
    } else {
      next.set('media', value);
    }
    next.delete('offset');
    setSearchParams(next, { replace: true });
  }

  function updateSpeedFilter(value: SpeedFilter) {
    const next = new URLSearchParams(searchParams);
    if (value === 'all') {
      next.delete('speed');
    } else {
      next.set('speed', value);
    }
    next.delete('offset');
    setSearchParams(next, { replace: true });
  }

  const sourceRows = useMemo(() => ports.data?.items || [], [ports.data?.items]);
  const rows = sourceRows;
  const totalRows = ports.data?.total || 0;
  const currentPage = Math.floor(offset / pageSize) + 1;
  const totalPages = Math.max(Math.ceil(totalRows / pageSize), 1);
  const canPrev = offset > 0;
  const canNext = offset + pageSize < totalRows;

  const upCount = useMemo(() => sourceRows.filter((port) => port.operStatus === 'up').length, [sourceRows]);
  const downCount = useMemo(() => sourceRows.filter((port) => port.operStatus === 'down').length, [sourceRows]);
  const staleCount = useMemo(() => sourceRows.filter((port) => port.stale).length, [sourceRows]);
  const vlanCount = useMemo(() => sourceRows.filter((port) => Boolean(port.vlanSummary?.trim())).length, [sourceRows]);

  function updateOffset(nextOffset: number) {
    const next = new URLSearchParams(searchParams);
    if (nextOffset > 0) {
      next.set('offset', String(nextOffset));
    } else {
      next.delete('offset');
    }
    setSearchParams(next, { replace: true });
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>端口列表</h1>
          <p>
            第 {currentPage}/{totalPages} 页 · {rows.length} / {totalRows} 个端口 · {scopeHint}
          </p>
        </div>
        <div className="toolbar">
          <CopyLinkButton />
        </div>
      </div>
      <MetricStrip
        items={[
          { label: '总端口', value: totalRows },
          { label: 'up', value: upCount },
          { label: 'down', value: downCount },
          { label: 'stale', value: staleCount },
          { label: '带 VLAN', value: vlanCount },
        ]}
      />

      <section className="workbench-toolbar">
        <label className="workbench-search">
          <Search size={16} />
          <input value={search} onChange={(event) => updateSearch(event.target.value)} placeholder="搜索端口、设备、VLAN" />
        </label>
        <div className="filter-chip-group">
          <button type="button" className={`filter-chip ${statusFilter === 'all' ? 'active' : ''}`} onClick={() => updateStatusFilter('all')}>
            全部 <strong>{totalRows}</strong>
          </button>
          <button type="button" className={`filter-chip ${statusFilter === 'up' ? 'active' : ''}`} onClick={() => updateStatusFilter('up')}>
            up <strong>{upCount}</strong>
          </button>
          <button type="button" className={`filter-chip ${statusFilter === 'down' ? 'active' : ''}`} onClick={() => updateStatusFilter('down')}>
            down <strong>{downCount}</strong>
          </button>
          <button type="button" className={`filter-chip ${statusFilter === 'stale' ? 'active' : ''}`} onClick={() => updateStatusFilter('stale')}>
            stale <strong>{staleCount}</strong>
          </button>
          <label className="scope-select-wrap" aria-label="拓扑范围">
            <select value={topologyId || ''} onChange={(event) => updateTopologyFilter(event.target.value ? Number(event.target.value) : undefined)}>
              <option value="">全部拓扑</option>
              {(topologies.data || []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label className="scope-select-wrap" aria-label="介质过滤">
            <select value={mediaFilter} onChange={(event) => updateMediaFilter(event.target.value as MediaFilter)}>
              <option value="all">全部介质</option>
              {mediaList
                .filter((item) => item !== 'all')
                .map((media) => (
                  <option key={media} value={media}>
                    {media}
                  </option>
                ))}
            </select>
          </label>
          <label className="scope-select-wrap" aria-label="速率范围">
            <select value={speedFilter} onChange={(event) => updateSpeedFilter(event.target.value as SpeedFilter)}>
              <option value="all">全部速率</option>
              <option value="slow">&lt;1G</option>
              <option value="1g">&gt;=1G</option>
              <option value="10g">&gt;=10G</option>
            </select>
          </label>
          <label className="scope-select-wrap" aria-label="是否显示 stale 端口">
            <button type="button" className={`filter-chip ${includeStale ? 'active' : ''}`} onClick={() => updateIncludeStale(!includeStale)}>
              包含 stale <strong>{includeStale ? '是' : '否'}</strong>
            </button>
          </label>
          <button
            type="button"
            className={`icon-button ${includeVirtual ? 'is-active' : ''}`}
            title={includeVirtual ? '已显示虚拟口' : '仅显示物理口'}
            onClick={() => updateIncludeVirtual(!includeVirtual)}
          >
            <Filter size={15} />
            <Router size={13} />
          </button>
        </div>
      </section>

      <section className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>设备</th>
                <th>端口</th>
                <th>状态</th>
                <th>速率</th>
                <th>介质</th>
                <th>MAC</th>
                <th>VLAN</th>
                <th>上/下行</th>
                <th>别名</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((port) => {
                const device = deviceById.get(port.deviceId);
                return (
                  <tr key={port.id}>
                    <td>{device ? <Link to={`/devices/${device.id}?portId=${port.id}`}>{device.displayName}</Link> : '-'}</td>
                    <td>{port.name}</td>
                    <td><StatusPill value={port.operStatus} /></td>
                    <td>{speed(port.speedMbps)}</td>
                    <td>{port.media || '-'}</td>
                    <td>{port.macAddress || '-'}</td>
                    <td>{port.vlanSummary || '-'}</td>
                    <td>{bps(port.lastTrafficInBps)} / {bps(port.lastTrafficOutBps)}</td>
                    <td>{port.alias || '-'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {!rows.length ? <div className="muted-note tight">没有匹配的端口。</div> : null}
        </div>
        <div className="table-pagination">
          <button className="text-button" type="button" disabled={!canPrev || ports.isFetching} onClick={() => updateOffset(Math.max(offset - pageSize, 0))}>
            上一页
          </button>
          <span>{offset + 1}-{Math.min(offset + pageSize, totalRows)} / {totalRows}</span>
          <button className="text-button" type="button" disabled={!canNext || ports.isFetching} onClick={() => updateOffset(offset + pageSize)}>
            下一页
          </button>
        </div>
      </section>
    </div>
  );
}

function parseStatusFilter(value: string | null): PortStatusFilter {
  if (value === 'up' || value === 'down' || value === 'shutdown' || value === 'stale') return value;
  return 'all';
}

function parseMediaFilter(value: string | null): MediaFilter {
  if (value === 'copper' || value === 'fiber' || value === 'virtual') return value;
  return 'all';
}

function parseSpeedFilter(value: string | null): SpeedFilter {
  if (value === 'slow' || value === '1g' || value === '10g') return value;
  return 'all';
}
