import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Box, Network, PencilLine, Plus, Save, Search, Server, Trash2, X } from 'lucide-react';
import { api } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { CopyLinkButton } from '../components/CopyLinkButton';
import { dateTime } from '../lib/format';
import { MetricStrip } from '../components/MetricStrip';
import { StatusPill } from '../components/StatusPill';
import { useFeedback } from '../components/FeedbackCenter';

type DeviceRoleFilter = 'all' | 'switch' | 'server' | 'custom';

export function DevicesPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const feedback = useFeedback();
  const topologies = useQuery({ queryKey: queryKeys.topologies(), queryFn: () => api.topologies() });
  const topologyIdQuery = Number(searchParams.get('topologyId'));
  const topologyFilter = Number.isFinite(topologyIdQuery) && topologyIdQuery > 0 ? topologyIdQuery : '';
  const devices = useQuery({
    queryKey: queryKeys.devices({ includeDisabled: true, topologyId: topologyFilter || undefined }),
    queryFn: () => api.devices({ includeDisabled: true, topologyId: topologyFilter || undefined }),
  });
  const [displayName, setDisplayName] = useState('');
  const [role, setRole] = useState('custom');
  const [topologyId, setTopologyId] = useState<number | ''>('');
  const searchQuery = searchParams.get('q') || '';
  const roleQuery = parseRoleFilter(searchParams.get('role'));
  const [search, setSearch] = useState(searchQuery);
  const [roleFilter, setRoleFilter] = useState<DeviceRoleFilter>(roleQuery);
  const [editingDeviceId, setEditingDeviceId] = useState<number | null>(null);
  const [editingDisplayName, setEditingDisplayName] = useState('');

  useEffect(() => {
    setSearch(searchQuery);
  }, [searchQuery]);

  useEffect(() => {
    setTopologyId(topologyFilter);
  }, [topologyFilter]);

  useEffect(() => {
    if (!topologies.data?.length || !topologyFilter) {
      return;
    }
    const hasTopology = topologies.data.some((topology) => topology.id === topologyFilter);
    if (!hasTopology) {
      const next = new URLSearchParams(searchParams);
      next.delete('topologyId');
      setSearchParams(next, { replace: true });
      setTopologyId('');
    }
  }, [searchParams, topologyFilter, topologies.data, setSearchParams]);

  useEffect(() => {
    setRoleFilter(roleQuery);
  }, [roleQuery]);

  function updateSearch(value: string) {
    setSearch(value);
    const next = new URLSearchParams(searchParams);
    if (value.trim()) {
      next.set('q', value);
    } else {
      next.delete('q');
    }
    setSearchParams(next, { replace: true });
  }

  function updateRoleFilter(value: DeviceRoleFilter) {
    setRoleFilter(value);
    const next = new URLSearchParams(searchParams);
    if (value === 'all') {
      next.delete('role');
    } else {
      next.set('role', value);
    }
    setSearchParams(next, { replace: true });
  }

  const filteredDevices = useMemo(() => {
    const terms = search
      .trim()
      .toLowerCase()
      .split(/\s+/)
      .filter(Boolean);
    return (devices.data || []).filter((device) => {
      const roleMatches =
        roleFilter === 'all'
          ? true
          : roleFilter === 'custom'
            ? device.role !== 'switch' && device.role !== 'server'
            : device.role === roleFilter;
      if (!roleMatches) return false;
      if (!terms.length) return true;
      const haystack = [device.displayName, device.role, device.source, device.model, device.mgmtIp]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return terms.every((term) => haystack.includes(term));
    });
  }, [devices.data, roleFilter, search]);

  const switchCount = useMemo(() => (devices.data || []).filter((device) => device.role === 'switch').length, [devices.data]);
  const serverCount = useMemo(() => (devices.data || []).filter((device) => device.role === 'server').length, [devices.data]);
  const customCount = useMemo(() => (devices.data || []).filter((device) => device.role !== 'switch' && device.role !== 'server').length, [devices.data]);
  const totalCount = devices.data?.length || 0;
  const disabledCount = useMemo(() => (devices.data || []).filter((device) => !device.enabled).length, [devices.data]);

  const scopeLabel = useMemo(() => {
    if (!topologyFilter) return '全部拓扑';
    const target = topologies.data?.find((topology) => topology.id === topologyFilter);
    return target ? target.name : `拓扑 #${topologyFilter}`;
  }, [topologyFilter, topologies.data]);
  const create = useMutation({
    mutationFn: api.createDevice,
    onSuccess: () => {
      setDisplayName('');
      queryClient.invalidateQueries({ queryKey: queryKeys.devicesAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologyAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      feedback.pushToast('设备创建成功', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });
  const remove = useMutation({
    mutationFn: api.deleteDevice,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devicesAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologyAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      feedback.pushToast('设备已删除', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });
  const rename = useMutation({
    mutationFn: (payload: { id: number; displayName: string }) => api.updateDevice(payload.id, { displayName: payload.displayName }),
    onSuccess: () => {
      setEditingDeviceId(null);
      setEditingDisplayName('');
      queryClient.invalidateQueries({ queryKey: queryKeys.devicesAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologyAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      feedback.pushToast('显示名称已保存', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!displayName.trim()) return;
    create.mutate({ displayName: displayName.trim(), role, ...(topologyId ? { topologyId } : {}) });
  }

  function updateTopologyFilter(nextTopologyId: number | '') {
    setTopologyId(nextTopologyId);
    const next = new URLSearchParams(searchParams);
    if (nextTopologyId) {
      next.set('topologyId', String(nextTopologyId));
    } else {
      next.delete('topologyId');
    }
    setSearchParams(next, { replace: true });
  }

  function deleteDevice(id: number, name: string) {
    void feedback
      .confirm({
        title: '删除设备',
        message: `删除设备「${name}」及其端口和线缆？`,
        confirmText: '确认删除',
        danger: true,
      })
      .then((confirmed) => {
        if (confirmed) {
          remove.mutate(id);
        }
      });
  }

  function startRename(deviceId: number, name: string) {
    setEditingDeviceId(deviceId);
    setEditingDisplayName(name);
  }

  function cancelRename() {
    setEditingDeviceId(null);
    setEditingDisplayName('');
  }

  function submitRename(event: FormEvent, deviceId: number) {
    event.preventDefault();
    const nextName = editingDisplayName.trim();
    if (!nextName) return;
    rename.mutate({ id: deviceId, displayName: nextName });
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>设备管理</h1>
          <p>{filteredDevices.length} / {devices.data?.length || 0} 台设备 · {scopeLabel}</p>
        </div>
        <div className="toolbar">
          <CopyLinkButton />
        </div>
      </div>
      <MetricStrip
        items={[
          { label: '总设备', value: totalCount },
          { label: '交换机', value: switchCount },
          { label: '服务器', value: serverCount },
          { label: '其他', value: customCount },
          { label: '已禁用', value: disabledCount },
        ]}
      />
      <section className="workbench-toolbar">
        <label className="workbench-search">
          <Search size={15} />
          <input value={search} onChange={(event) => updateSearch(event.target.value)} placeholder="搜索设备、IP、型号、来源" />
        </label>
        <div className="filter-chip-group">
          <button type="button" className={`filter-chip ${roleFilter === 'all' ? 'active' : ''}`} onClick={() => updateRoleFilter('all')} title="全部设备">
            <span className="sr-only">全部</span><strong>{devices.data?.length || 0}</strong>
          </button>
          <button type="button" className={`filter-chip ${roleFilter === 'switch' ? 'active' : ''}`} onClick={() => updateRoleFilter('switch')} title="交换机">
            <Network size={14} /><span className="sr-only">交换机</span><strong>{switchCount}</strong>
          </button>
          <button type="button" className={`filter-chip ${roleFilter === 'server' ? 'active' : ''}`} onClick={() => updateRoleFilter('server')} title="服务器">
            <Server size={14} /><span className="sr-only">服务器</span><strong>{serverCount}</strong>
          </button>
          <button type="button" className={`filter-chip ${roleFilter === 'custom' ? 'active' : ''}`} onClick={() => updateRoleFilter('custom')} title="其他设备">
            <Box size={14} /><span className="sr-only">其他</span><strong>{customCount}</strong>
          </button>
        </div>
      </section>
        <form className="inline-form" onSubmit={submit}>
          <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} placeholder="设备名称" />
          <select
            value={topologyId}
            onChange={(event) => updateTopologyFilter(event.target.value ? Number(event.target.value) : '')}
            aria-label="筛选拓扑 / 新建设备目标拓扑"
          >
            <option value="">全部拓扑（新增后默认绑定当前默认拓扑）</option>
            {(topologies.data || []).map((topology) => (
              <option key={topology.id} value={topology.id}>
                {topology.name}
              </option>
            ))}
          </select>
          <select value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="custom">自定义</option>
            <option value="server">服务器</option>
            <option value="switch">交换机</option>
          </select>
          <button className="icon-button" title="新增设备" aria-label="新增设备"><Plus size={16} /></button>
        </form>
      <section className="panel">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>设备</th>
                <th>角色</th>
                <th>来源</th>
                <th>状态</th>
                <th>型号</th>
                <th>IP</th>
                <th>同步</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredDevices.map((device) => (
                <tr key={device.id}>
                  <td>
                    {editingDeviceId === device.id ? (
                      <form className="inline-rename-form" onSubmit={(event) => submitRename(event, device.id)}>
                        <input
                          value={editingDisplayName}
                          onChange={(event) => setEditingDisplayName(event.target.value)}
                          aria-label="显示名称"
                        />
                        <button className="icon-button" type="submit" title="保存显示名称" disabled={rename.isPending}>
                          <Save size={14} />
                        </button>
                        <button className="icon-button" type="button" title="取消" onClick={cancelRename}>
                          <X size={14} />
                        </button>
                      </form>
                    ) : (
                      <span className="device-name-cell">
                        <Link to={`/devices/${device.id}`}>{device.displayName}</Link>
                        <button className="icon-button" type="button" title="修改显示名称" onClick={() => startRename(device.id, device.displayName)}>
                          <PencilLine size={14} />
                        </button>
                      </span>
                    )}
                  </td>
                  <td>{device.role}</td>
                  <td>{device.source}</td>
                  <td><StatusPill value={device.health} /></td>
                  <td>{device.model || '-'}</td>
                  <td>{device.mgmtIp || '-'}</td>
                  <td>{dateTime(device.lastSeenAt)}</td>
                  <td>
                    <button className="danger-icon" type="button" title="删除设备" onClick={() => deleteDevice(device.id, device.displayName)} disabled={remove.isPending}>
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!filteredDevices.length ? <div className="muted-note tight">没有匹配的设备。</div> : null}
        </div>
      </section>
    </div>
  );
}

function parseRoleFilter(value: string | null): DeviceRoleFilter {
  if (value === 'switch' || value === 'server' || value === 'custom') return value;
  return 'all';
}
