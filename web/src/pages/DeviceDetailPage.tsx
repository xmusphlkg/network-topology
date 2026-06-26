import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, PencilLine, Plus, Save, Search, Trash2, X } from 'lucide-react';
import { api } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { CopyLinkButton } from '../components/CopyLinkButton';
import { bps, dateTime, speed } from '../lib/format';
import type { DeviceProfile, Port } from '../types';
import { EChart } from '../components/EChart';
import { MetricStrip } from '../components/MetricStrip';
import { PortMatrix } from '../components/PortMatrix';
import { StatusPill } from '../components/StatusPill';
import { useFeedback } from '../components/FeedbackCenter';
import { useI18n } from '../i18n/I18nProvider';

export function DeviceDetailPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const id = Number(useParams().id);
  const feedback = useFeedback();
  const { t } = useI18n();
  const devices = useQuery({ queryKey: queryKeys.devices(), queryFn: () => api.devices({ includeDisabled: true }) });
  const [includeVirtualPorts, setIncludeVirtualPorts] = useState(false);
  const ports = useQuery({
    queryKey: queryKeys.devicePorts(id, { includeVirtual: includeVirtualPorts }),
    queryFn: () => api.devicePorts(id, { includeVirtual: includeVirtualPorts }),
    enabled: Boolean(id),
  });
  const deviceProfiles = useQuery({ queryKey: queryKeys.deviceProfiles(), queryFn: api.deviceProfiles, staleTime: 30_000 });
  const device = devices.data?.find((item) => item.id === id);
  const selectedPortIdQuery = searchParams.get('portId') || '';
  const selectedPort = useMemo(() => {
    if (!ports.data?.length) return null;
    const parsed = Number(selectedPortIdQuery);
    if (selectedPortIdQuery && Number.isFinite(parsed)) {
      return ports.data.find((port) => port.id === parsed) || ports.data[0] || null;
    }
    return ports.data[0] || null;
  }, [ports.data, selectedPortIdQuery]);
  const [newPortName, setNewPortName] = useState('');
  const [newPortAlias, setNewPortAlias] = useState('');
  const [newPortSpeed, setNewPortSpeed] = useState('');
  const [newPortMedia, setNewPortMedia] = useState('');
  const [newPortMac, setNewPortMac] = useState('');
  const [newPortRole, setNewPortRole] = useState('');
  const [newPortVlan, setNewPortVlan] = useState('');
  const [editName, setEditName] = useState('');
  const [editAlias, setEditAlias] = useState('');
  const [editOperStatus, setEditOperStatus] = useState('unknown');
  const [editAdminStatus, setEditAdminStatus] = useState('unknown');
  const [editSpeed, setEditSpeed] = useState('');
  const [editMedia, setEditMedia] = useState('');
  const [editMac, setEditMac] = useState('');
  const [editRole, setEditRole] = useState('');
  const [editVlan, setEditVlan] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [editingDisplayName, setEditingDisplayName] = useState(false);
  const [selectedProfile, setSelectedProfile] = useState('');
  const [replaceProfilePorts, setReplaceProfilePorts] = useState(false);
  const [portSearch, setPortSearch] = useState('');
  const [trafficRange, setTrafficRange] = useState<'1h' | '6h' | '24h' | '7d'>('24h');
  const series = useQuery({
    queryKey: queryKeys.portSeries(selectedPort?.id || 'none', trafficRange),
    queryFn: () => api.portSeries(selectedPort!.id, trafficRange),
    enabled: Boolean(selectedPort?.id),
  });

  const chartOption = useMemo(() => {
    const points = series.data?.points || [];
    if (!selectedPort || !points.length) {
      return null;
    }
    return {
      tooltip: { trigger: 'axis' },
      legend: { top: 0, data: ['上行', '下行'] },
      grid: { top: 36, left: 54, right: 18, bottom: 42 },
      xAxis: { type: 'time' },
      yAxis: { type: 'value', axisLabel: { formatter: (value: number) => bps(value) } },
      dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18 }],
      series: [
        { name: '上行', type: 'line', showSymbol: false, data: points.map((point) => [point.ts * 1000, point.inBps]) },
        { name: '下行', type: 'line', showSymbol: false, data: points.map((point) => [point.ts * 1000, point.outBps]) },
      ],
    };
  }, [selectedPort, series.data?.points]);

  useEffect(() => {
    if (!selectedPort) return;
    setEditName(selectedPort.name || '');
    setEditAlias(selectedPort.alias || '');
    setEditOperStatus(selectedPort.operStatus || 'unknown');
    setEditAdminStatus(selectedPort.adminStatus || 'unknown');
    setEditSpeed(selectedPort.speedMbps == null ? '' : String(selectedPort.speedMbps));
    setEditMedia(selectedPort.media || '');
    setEditMac(selectedPort.macAddress || '');
    setEditRole(selectedPort.portRole || '');
    setEditVlan(selectedPort.vlanSummary || '');
  }, [selectedPort?.id, selectedPort?.updatedAt]);

  useEffect(() => {
    if (!device) return;
    setDisplayName(device.displayName);
  }, [device?.displayName]);

  useEffect(() => {
    const model = device?.model || '';
    if (!deviceProfiles.data?.length) return;
    const match = deviceProfiles.data.find((profile) => profile.models.some((item) => item.toLowerCase() === model.toLowerCase()));
    setSelectedProfile(match?.key || deviceProfiles.data[0]?.key || '');
  }, [device?.model, deviceProfiles.data]);

  const filteredPorts = useMemo(() => {
    const query = portSearch.trim().toLowerCase();
    return (ports.data || []).filter((port) => {
      if (!query) return true;
      return [port.name, port.alias, port.vlanSummary, port.media, port.macAddress, port.operStatus]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(query);
    });
  }, [ports.data, portSearch]);
  const totalPorts = ports.data?.length || 0;
  const upPorts = useMemo(() => (ports.data || []).filter((port) => port.operStatus === 'up').length, [ports.data]);
  const downPorts = useMemo(() => (ports.data || []).filter((port) => port.operStatus === 'down').length, [ports.data]);
  const vlanPorts = useMemo(() => (ports.data || []).filter((port) => Boolean(port.vlanSummary?.trim())).length, [ports.data]);
  const manualPorts = useMemo(() => (ports.data || []).filter((port) => port.source === 'manual').length, [ports.data]);

  useEffect(() => {
    if (!ports.data?.length) {
      if (selectedPortIdQuery) {
        setSearchParams({}, { replace: true });
      }
      return;
    }
    if (!selectedPortIdQuery) {
      setSearchParams({ portId: String(ports.data[0].id) }, { replace: true });
    }
  }, [ports.data, selectedPortIdQuery, setSearchParams]);

  function selectPort(port: Port | null) {
    const next = new URLSearchParams(searchParams);
    if (port) {
      next.set('portId', String(port.id));
    } else {
      next.delete('portId');
    }
    setSearchParams(next, { replace: true });
  }

  const createPort = useMutation({
    mutationFn: () =>
      api.createPort(id, {
        name: newPortName.trim(),
        alias: emptyToNull(newPortAlias),
        speedMbps: numberOrNull(newPortSpeed),
        media: emptyToNull(newPortMedia),
        macAddress: emptyToNull(newPortMac),
        portRole: emptyToNull(newPortRole),
        vlanSummary: emptyToNull(newPortVlan),
      }),
    onSuccess: (created) => {
      selectPort(created);
      setNewPortName('');
      setNewPortAlias('');
      setNewPortSpeed('');
      setNewPortMedia('');
      setNewPortMac('');
      setNewPortRole('');
      setNewPortVlan('');
      invalidateDeviceData(queryClient, id);
      feedback.pushToast('端口创建成功', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const updatePort = useMutation({
    mutationFn: () =>
      api.updatePort(selectedPort!.id, {
        name: editName.trim(),
        alias: emptyToNull(editAlias),
        operStatus: editOperStatus,
        adminStatus: editAdminStatus,
        speedMbps: numberOrNull(editSpeed),
        media: emptyToNull(editMedia),
        macAddress: emptyToNull(editMac),
        portRole: emptyToNull(editRole),
        vlanSummary: emptyToNull(editVlan),
      }),
    onSuccess: () => {
      invalidateDeviceData(queryClient, id);
      feedback.pushToast('端口更新成功', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const deletePort = useMutation({
    mutationFn: (portId: number) => api.deletePort(portId),
    onSuccess: (_result, deletedPortId) => {
      const remaining = (ports.data || []).filter((port) => port.id !== deletedPortId);
      if (selectedPort?.id === deletedPortId) {
        selectPort(remaining[0] || null);
      }
      invalidateDeviceData(queryClient, id);
      feedback.pushToast('端口已删除', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const deleteDevice = useMutation({
    mutationFn: api.deleteDevice,
    onSuccess: () => {
      invalidateDeviceData(queryClient, id);
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      navigate('/devices');
      feedback.pushToast('设备已删除', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const updateDisplayName = useMutation({
    mutationFn: () => api.updateDevice(id, { displayName }),
    onSuccess: () => {
      invalidateDeviceData(queryClient, id);
      setEditingDisplayName(false);
      feedback.pushToast(t('rename') + '成功', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const applyProfile = useMutation({
    mutationFn: () =>
      api.applyDeviceProfile(id, {
        profileKey: selectedProfile,
        replaceProfilePorts,
      }),
    onSuccess: () => {
      invalidateDeviceData(queryClient, id);
      feedback.pushToast(t('applyTemplate') + '成功', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  function submitNewPort(event: FormEvent) {
    event.preventDefault();
    if (!newPortName.trim()) return;
    createPort.mutate();
  }

  function submitPortUpdate(event: FormEvent) {
    event.preventDefault();
    if (!selectedPort || !editName.trim()) return;
    updatePort.mutate();
  }

  function submitDisplayName(event: FormEvent) {
    event.preventDefault();
    if (!displayName.trim()) return;
    updateDisplayName.mutate();
  }

  function cancelDisplayNameEdit() {
    setEditingDisplayName(false);
    setDisplayName(device?.displayName || '');
  }

  function submitProfile(event: FormEvent) {
    event.preventDefault();
    if (!selectedProfile) return;
    applyProfile.mutate();
  }

  function confirmDeleteSelectedPort() {
    if (!selectedPort) return;
    void feedback
      .confirm({
        title: '删除端口',
        message: `删除端口「${selectedPort.name}」及其相关线缆？`,
        confirmText: '确认删除',
        danger: true,
      })
      .then((confirmed) => {
        if (confirmed) {
          deletePort.mutate(selectedPort.id);
        }
      });
  }

  function confirmDeleteDevice() {
    if (!device) return;
    void feedback
      .confirm({
        title: '删除设备',
        message: `删除设备「${device.displayName}」及其端口和线缆？`,
        confirmText: '确认删除',
        danger: true,
      })
      .then((confirmed) => {
        if (confirmed) {
          deleteDevice.mutate(device.id);
        }
      });
  }

  if (!device) {
    return (
      <div className="page">
        <Link className="back-link" to="/topology"><ArrowLeft size={16} />返回</Link>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <Link className="back-link" to="/topology"><ArrowLeft size={16} />返回</Link>
          {editingDisplayName ? (
            <form className="inline-form inline-form--compact device-name-form" onSubmit={submitDisplayName}>
              <input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
              <button className="icon-button" type="submit" title={t('save')} disabled={updateDisplayName.isPending}>
                <Save size={16} />
              </button>
              <button className="icon-button" type="button" onClick={cancelDisplayNameEdit} title={t('cancel')}>
                <X size={16} />
              </button>
            </form>
          ) : (
            <div className="device-title">
              <h1>{device.displayName}</h1>
              <button
                className="icon-button"
                type="button"
                title={t('rename')}
                onClick={() => setEditingDisplayName(true)}
              >
                <PencilLine size={16} />
              </button>
            </div>
          )}
          <p>{device.model || '-'} · {device.mgmtIp || '-'}</p>
        </div>
        <div className="toolbar">
          <CopyLinkButton />
          <StatusPill value={device.health} />
          <button className="icon-button danger-button" type="button" onClick={confirmDeleteDevice} disabled={deleteDevice.isPending} title={t('delete')}>
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      <section className="info-grid">
        <Info label="设备名称" value={device.displayName} />
        <Info label="IP地址" value={device.mgmtIp || '-'} />
        <Info label="设备型号" value={device.model || '-'} />
        <Info label="来源" value={device.source} />
        <Info label="状态" value={device.status} />
        <Info label="最后同步" value={dateTime(device.lastSeenAt)} />
      </section>

      <MetricStrip
        items={[
          { label: '总端口', value: totalPorts },
          { label: 'up', value: upPorts },
          { label: 'down', value: downPorts },
          { label: '带 VLAN', value: vlanPorts },
          { label: '手工端口', value: manualPorts },
        ]}
      />

      <section className="panel">
        <div className="section-head">
          <h2>{t('deviceProfiles')}</h2>
          <button
            className="text-button"
            onClick={submitProfile}
            type="submit"
            form="device-profile-form"
            disabled={!selectedProfile || applyProfile.isPending}
          >
            <Save size={14} />{t('applyTemplate')}
          </button>
        </div>
        <form id="device-profile-form" className="device-profile-form" onSubmit={submitProfile}>
          <label className="device-profile-select">
            <span>模板</span>
            <select value={selectedProfile} onChange={(event) => setSelectedProfile(event.target.value)}>
              <option value="">选择模板</option>
              {deviceProfiles.data?.map((profile) => (
                <option key={profile.key} value={profile.key}>
                  {profile.key}（{profile.portCount} 端口）
                </option>
              ))}
            </select>
          </label>
          <label className="compact-checkbox">
            <input type="checkbox" checked={replaceProfilePorts} onChange={(event) => setReplaceProfilePorts(event.target.checked)} />
            <span>{t('replaceTemplatePorts')}</span>
          </label>
        </form>
      </section>

      <section className="port-workbench">
        <form className="panel port-edit-panel" onSubmit={submitNewPort}>
          <div className="section-head">
            <h2>新增网口</h2>
            <button className="text-button" type="submit" disabled={!newPortName.trim() || createPort.isPending}>
              <Plus size={16} />新增
            </button>
          </div>
          <div className="port-form-grid">
            <label>
              <span>端口名</span>
              <input value={newPortName} onChange={(event) => setNewPortName(event.target.value)} placeholder="iDRAC / eno1 / XGE0/1" />
            </label>
            <label>
              <span>别名</span>
              <input value={newPortAlias} onChange={(event) => setNewPortAlias(event.target.value)} placeholder="BMC 管理口" />
            </label>
            <label>
              <span>速率 Mbps</span>
              <input value={newPortSpeed} onChange={(event) => setNewPortSpeed(event.target.value)} inputMode="decimal" placeholder="1000" />
            </label>
            <label>
              <span>介质</span>
              <select value={newPortMedia} onChange={(event) => setNewPortMedia(event.target.value)}>
                <option value="">未指定</option>
                <option value="copper">电口</option>
                <option value="fiber">光口</option>
                <option value="virtual">虚拟</option>
              </select>
            </label>
            <label>
              <span>MAC</span>
              <input value={newPortMac} onChange={(event) => setNewPortMac(event.target.value)} placeholder="52:54:00:aa:bb:cc" />
            </label>
            <label>
              <span>角色</span>
              <select value={newPortRole} onChange={(event) => setNewPortRole(event.target.value)}>
                <option value="">未指定</option>
                <option value="access">access</option>
                <option value="uplink">uplink</option>
                <option value="management">management</option>
              </select>
            </label>
            <label>
              <span>VLAN</span>
              <input value={newPortVlan} onChange={(event) => setNewPortVlan(event.target.value)} placeholder="PVID 10 / trunk 10,20" />
            </label>
          </div>
        </form>

        <form className="panel port-edit-panel" onSubmit={submitPortUpdate}>
          <div className="section-head">
            <h2>编辑端口</h2>
            <div className="side-actions">
              <button className="danger-button" type="button" onClick={confirmDeleteSelectedPort} disabled={!selectedPort || deletePort.isPending}>
                <Trash2 size={16} />删除
              </button>
              <button className="text-button" type="submit" disabled={!selectedPort || !editName.trim() || updatePort.isPending}>
                <Save size={16} />保存
              </button>
            </div>
          </div>
          {selectedPort ? (
            <div className="port-form-grid">
              <label>
                <span>端口名</span>
                <input value={editName} onChange={(event) => setEditName(event.target.value)} />
              </label>
              <label>
                <span>别名</span>
                <input value={editAlias} onChange={(event) => setEditAlias(event.target.value)} />
              </label>
              <label>
                <span>运行状态</span>
                <select value={editOperStatus} onChange={(event) => setEditOperStatus(event.target.value)}>
                  <option value="unknown">unknown</option>
                  <option value="up">up</option>
                  <option value="down">down</option>
                  <option value="shutdown">shutdown</option>
                </select>
              </label>
              <label>
                <span>管理状态</span>
                <select value={editAdminStatus} onChange={(event) => setEditAdminStatus(event.target.value)}>
                  <option value="unknown">unknown</option>
                  <option value="up">up</option>
                  <option value="down">down</option>
                  <option value="shutdown">shutdown</option>
                </select>
              </label>
              <label>
                <span>速率 Mbps</span>
                <input value={editSpeed} onChange={(event) => setEditSpeed(event.target.value)} inputMode="decimal" />
              </label>
              <label>
                <span>介质</span>
                <select value={editMedia} onChange={(event) => setEditMedia(event.target.value)}>
                  <option value="">未指定</option>
                  <option value="copper">电口</option>
                  <option value="fiber">光口</option>
                  <option value="virtual">虚拟</option>
                </select>
              </label>
              <label>
                <span>MAC</span>
                <input value={editMac} onChange={(event) => setEditMac(event.target.value)} placeholder="52:54:00:aa:bb:cc" />
              </label>
              <label>
                <span>角色</span>
                <select value={editRole} onChange={(event) => setEditRole(event.target.value)}>
                  <option value="">未指定</option>
                  <option value="access">access</option>
                  <option value="uplink">uplink</option>
                  <option value="management">management</option>
                </select>
              </label>
              <label>
                <span>VLAN</span>
                <input value={editVlan} onChange={(event) => setEditVlan(event.target.value)} placeholder="PVID 10 / trunk 10,20" />
              </label>
            </div>
          ) : (
            <div className="muted-note tight">当前设备暂无端口。</div>
          )}
        </form>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>接口状态</h2>
          <div className="legend">
            <span><i className="dot high" />10G以上</span>
            <span><i className="dot mid" />1G/2.5G</span>
            <span><i className="dot low" />100M</span>
            <span><i className="dot down" />未连接</span>
          </div>
        </div>
        <PortMatrix
          ports={ports.data || []}
          selectedPortId={selectedPort?.id}
          onSelect={selectPort}
          compact={false}
          columns={null}
          rows={device.role === 'switch' ? 2 : 1}
          arrangement={device.role === 'switch' ? 'odd-even' : 'server'}
          hideVirtual={!includeVirtualPorts}
        />
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>端口列表</h2>
          <label className="workbench-search compact">
            <Search size={15} />
            <input value={portSearch} onChange={(event) => setPortSearch(event.target.value)} placeholder="搜索端口、别名、VLAN、MAC" />
          </label>
          <label className="compact-checkbox">
            <input type="checkbox" checked={includeVirtualPorts} onChange={(event) => setIncludeVirtualPorts(event.target.checked)} />
            <span>包含虚拟口</span>
          </label>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>端口</th>
                <th>状态</th>
                <th>协商速率</th>
                <th>介质</th>
                <th>MAC</th>
                <th>VLAN</th>
                <th>5min 上/下行</th>
                <th>别名</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredPorts.map((port) => (
                <tr key={port.id} className={selectedPort?.id === port.id ? 'selected-row' : ''} onClick={() => selectPort(port)}>
                  <td><Link to={`/devices/${device.id}?portId=${port.id}`}>{port.name}</Link></td>
                  <td><StatusPill value={port.operStatus} /></td>
                  <td>{speed(port.speedMbps)}</td>
                  <td>{port.media || '-'}</td>
                  <td>{port.macAddress || '-'}</td>
                  <td>{port.vlanSummary || '-'}</td>
                  <td>{bps(port.lastTrafficInBps)} / {bps(port.lastTrafficOutBps)}</td>
                  <td>{port.alias || '-'}</td>
                  <td>
                      <button
                        className="danger-icon"
                        type="button"
                        title="删除端口"
                        onClick={(event) => {
                          event.stopPropagation();
                          void feedback
                            .confirm({
                              title: '删除端口',
                              message: `删除端口「${port.name}」及其相关线缆？`,
                              confirmText: '确认删除',
                              danger: true,
                            })
                            .then((confirmed) => {
                              if (confirmed) {
                                deletePort.mutate(port.id);
                              }
                            });
                        }}
                        disabled={deletePort.isPending}
                      >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!filteredPorts.length ? <div className="muted-note tight">没有匹配的端口。</div> : null}
        </div>
      </section>

      <section className="panel">
        <div className="section-head">
          <h2>端口流量</h2>
          <div className="rail-workspace-actions">
            {(['1h', '6h', '24h', '7d'] as const).map((range) => (
              <button
                key={range}
                type="button"
                className={`text-button ${trafficRange === range ? 'is-active' : ''}`}
                onClick={() => setTrafficRange(range)}
                disabled={series.isFetching}
              >
                {range}
              </button>
            ))}
          </div>
          <span>{selectedPort?.name || '-'}</span>
        </div>
        {series.isLoading ? (
          <div className="muted-note tight">正在加载流量数据...</div>
        ) : !selectedPort ? (
          <div className="muted-note tight">请先选择端口。</div>
        ) : chartOption ? (
          <EChart option={chartOption} height={300} />
        ) : (
          <div className="muted-note tight">{series.data?.error || '该端口当前无可用流量数据。'}</div>
        )}
        {series.data?.error ? <div className="error-panel compact">{series.data.error}</div> : null}
      </section>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-item">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function emptyToNull(value: string) {
  const text = value.trim();
  return text ? text : null;
}

function numberOrNull(value: string) {
  const text = value.trim();
  if (!text) return null;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
}

function invalidateDeviceData(queryClient: ReturnType<typeof useQueryClient>, deviceId: number) {
  queryClient.invalidateQueries({ queryKey: queryKeys.devicesAll() });
  queryClient.invalidateQueries({ queryKey: queryKeys.devicePorts(deviceId) });
  queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
  queryClient.invalidateQueries({ queryKey: queryKeys.topologyAll() });
}
