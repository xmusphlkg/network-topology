import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CircleSlash2, Copy, History, RefreshCw, Send, Terminal } from 'lucide-react';
import { api } from '../lib/api';
import { buildSyncPayload, syncPushTemplates } from '../lib/syncTemplates';
import { queryKeys } from '../lib/queryKeys';
import { CopyLinkButton } from '../components/CopyLinkButton';
import { dateTime, number } from '../lib/format';
import { MetricStrip } from '../components/MetricStrip';
import { useFeedback } from '../components/FeedbackCenter';
import { StatusPill } from '../components/StatusPill';
import { useI18n } from '../i18n/I18nProvider';

const defaultPushTemplate = syncPushTemplates[0];

export function SyncPage() {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const { t } = useI18n();
  const [selectedTemplateKey, setSelectedTemplateKey] = useState(defaultPushTemplate.key);
  const [ingestSource, setIngestSource] = useState('agent');
  const [pushPayloadText, setPushPayloadText] = useState(() => JSON.stringify(api.syncPushExample(), null, 2));
  const [strictPhysicalPorts, setStrictPhysicalPorts] = useState(true);
  const [physicalPortNamePatterns, setPhysicalPortNamePatterns] = useState('wan\nlan\nge\nxe\nxge\neth\neno\nens\nenp\nenx\nem\nib\nbond\nidrac\nipmi\nbmc\nilo');
  const [maxPhysicalPortsPerDevice, setMaxPhysicalPortsPerDevice] = useState('');
  const [pushPayloadError, setPushPayloadError] = useState('');
  const [pushPayloadSummary, setPushPayloadSummary] = useState('');
  const [ipAddrDeviceName, setIpAddrDeviceName] = useState('');
  const [ipAddrMgmtIp, setIpAddrMgmtIp] = useState('');
  const [ipAddrTopologyId, setIpAddrTopologyId] = useState<number | ''>('');
  const [ipAddrOutput, setIpAddrOutput] = useState('');
  const [ipAddrSummary, setIpAddrSummary] = useState('');
  const [ipAddrError, setIpAddrError] = useState('');

  const topologies = useQuery({ queryKey: queryKeys.topologies(), queryFn: api.topologies, staleTime: 60000 });
  const status = useQuery({ queryKey: queryKeys.topologySyncStatus(), queryFn: api.syncStatus, refetchInterval: 10000 });
  const runs = useQuery({ queryKey: queryKeys.syncRuns(8), queryFn: () => api.syncRuns(8), refetchInterval: 15000 });
  const quality = useQuery({ queryKey: ['quality-issues'], queryFn: () => api.qualityIssues(), refetchInterval: 30000 });
  const audit = useQuery({ queryKey: ['audit-logs'], queryFn: () => api.auditLogs(12), refetchInterval: 30000 });

  const run = useMutation({
    mutationFn: () => api.runSync(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.topologySyncStatus() });
      queryClient.invalidateQueries({ queryKey: queryKeys.syncRuns() });
    },
  });

  const push = useMutation({
    mutationFn: (payloadText: string) => {
      const payload = buildSyncPayload(payloadText, {
        strictPhysicalPorts,
        patternText: physicalPortNamePatterns,
        maxPhysicalPortsPerDevice,
      });
      payload.source = ingestSource;
      return api.syncPush(payload);
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.topologyAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologySyncStatus() });
      setPushPayloadError('');
      setPushPayloadSummary(`设备 ${result.devices}，端口 ${result.ports}，线缆 ${result.cables} 条已写入/更新`);
      feedback.pushToast(t('syncPushSuccess'), 'success');
    },
    onError: (error: Error) => {
      setPushPayloadError(error.message);
      setPushPayloadSummary('');
      feedback.pushToast(error.message, 'error', 5000);
    },
  });

  const commandPush = useMutation({
    mutationFn: (payloadText: string) => {
      const payload = buildSyncPayload(payloadText, {
        strictPhysicalPorts,
        patternText: physicalPortNamePatterns,
        maxPhysicalPortsPerDevice,
      });
      payload.source = ingestSource;
      return api.syncPushFromCommand(payload);
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.topologyAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologySyncStatus() });
      setPushPayloadError('');
      setPushPayloadSummary(`设备 ${result.devices}，端口 ${result.ports}，线缆 ${result.cables} 条已写入/更新`);
      feedback.pushToast(t('commandPushSuccess'), 'success');
    },
    onError: (error: Error) => {
      setPushPayloadError(error.message);
      setPushPayloadSummary('');
      feedback.pushToast(error.message, 'error', 5000);
    },
  });

  const ipAddrPush = useMutation({
    mutationFn: () =>
      api.syncIpAddr({
        displayName: ipAddrDeviceName.trim(),
        mgmtIp: ipAddrMgmtIp.trim() || null,
        topologyId: ipAddrTopologyId || null,
        output: ipAddrOutput,
        source: 'command',
        strictPhysicalPorts: true,
        physicalPortNamePatterns: ['eth', 'eno', 'ens', 'enp', 'enx', 'em', 'ib', 'bond', 'wan', 'lan', 'idrac', 'ipmi', 'bmc', 'ilo'],
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.topologyAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.devicesAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      setIpAddrError('');
      setIpAddrSummary(`已解析设备 ${result.devices}，端口 ${result.ports}`);
      feedback.pushToast('ip addr 已解析入库', 'success');
    },
    onError: (error: Error) => {
      setIpAddrSummary('');
      setIpAddrError(error.message);
      feedback.pushToast(error.message, 'error', 5000);
    },
  });

  function syncFormFromTemplate(template: (typeof syncPushTemplates)[number]) {
    setStrictPhysicalPorts(template.strictPhysicalPorts);
    setPhysicalPortNamePatterns(template.physicalPortNamePatterns.join('\n'));
    setMaxPhysicalPortsPerDevice(template.maxPhysicalPortsPerDevice == null || template.maxPhysicalPortsPerDevice < 1 ? '' : String(template.maxPhysicalPortsPerDevice));
    setPushPayloadError('');
    setPushPayloadSummary('');
    setPushPayloadText(
      JSON.stringify(
        {
          source: ingestSource,
          strictPhysicalPorts: template.strictPhysicalPorts,
          physicalPortNamePatterns: template.physicalPortNamePatterns,
          maxPhysicalPortsPerDevice: template.maxPhysicalPortsPerDevice,
          topologyId: null,
          devices: [
            {
              displayName: 'compute-01',
              role: 'server',
              ports: [{ name: 'ens1f0', macAddress: '52:54:00:aa:bb:cc', operStatus: 'up' }],
            },
            {
              displayName: 'tor-01',
              role: 'switch',
              ports: [{ name: 'XGE0/1', operStatus: 'up' }],
            },
          ],
          cables: [
            {
              endpointA: { displayName: 'tor-01', portName: 'XGE0/1' },
              endpointB: { macAddress: '52:54:00:aa:bb:cc' },
              vlanId: 10,
              label: 'mac-learned uplink',
            },
          ],
        },
        null,
        2,
      ),
    );
  }

  function setTemplateByKey(nextKey: string) {
    const template = syncPushTemplates.find((item) => item.key === nextKey) || defaultPushTemplate;
    setSelectedTemplateKey(template.key);
    syncFormFromTemplate(template);
  }

  function updateJsonPayload(nextText: string) {
    setPushPayloadText(nextText);
    setPushPayloadError('');
    setPushPayloadSummary('');
  }

  function runPush() {
    setPushPayloadError('');
    setPushPayloadSummary('');
    push.mutate(pushPayloadText);
  }

  function runCommandPush() {
    setPushPayloadError('');
    setPushPayloadSummary('');
    commandPush.mutate(pushPayloadText);
  }

  function runIpAddrPush() {
    setIpAddrError('');
    setIpAddrSummary('');
    if (!ipAddrDeviceName.trim() || !ipAddrOutput.trim()) {
      setIpAddrError('设备名和 ip -d addr/ip addr 输出不能为空');
      return;
    }
    ipAddrPush.mutate();
  }

  async function copyCommandPushCurl() {
    const endpoint = `${window.location.origin}/api/sync/command-push`;
    const command = `curl -sS -X POST '${endpoint}' -H 'Content-Type: application/json' --data-raw ${shellQuote(pushPayloadText)}`;
    try {
      await navigator.clipboard.writeText(command);
      feedback.pushToast('命令已复制', 'success');
    } catch (error) {
      feedback.pushToast(error instanceof Error ? error.message : '复制命令失败', 'error');
    }
  }

  const latest = status.data?.latest;
  const history = runs.data || [];
  const statusText = latest ? (latest.status === 'success' ? '正常' : latest.status === 'failed' ? '失败' : '运行中') : '待同步';
  const statusTone = latest ? (latest.status === 'success' ? 'ok' : latest.status === 'failed' ? 'critical' : 'unknown') : 'unknown';
  const configuredText = status.data?.readOnly ? '只读模式' : status.data?.zabbixConfigured ? '已配置' : '未配置';
  const detailHostids = Array.isArray(latest?.details?.hostids) ? latest?.details?.hostids.length : null;

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1>同步诊断</h1>
          <p>Zabbix {status.data?.zabbixConfigured ? '已配置' : '未配置'}</p>
        </div>
        <div className="toolbar">
          <CopyLinkButton />
        </div>
      </div>
      <div className="sync-workbench">
        <section className="panel sync-control-panel">
          <div className="section-head">
            <h2>同步控制</h2>
            <span className="rail-workspace-badge">{configuredText}</span>
          </div>
          <section className="workbench-toolbar sync-toolbar">
            <div className="toolbar-group">
              <button className="text-button" type="button" onClick={() => run.mutate()} disabled={run.isPending || status.isFetching} title={t('sync')}>
                <RefreshCw size={16} />立即同步
              </button>
              <button className="text-button" type="button" onClick={() => status.refetch()} disabled={status.isFetching} title={t('refresh')}>
                <span>刷新状态</span>
              </button>
            </div>
            <div className="workstation-stats">
              <span>最近 {latest ? dateTime(latest.startedAt) : '-'}</span>
              <span className="status-inline">
                <StatusPill value={statusTone} />
              </span>
            </div>
          </section>
          <MetricStrip
            items={[
              { label: 'Zabbix', value: configuredText },
              { label: '最近状态', value: statusText },
              { label: '设备写入', value: latest ? number(latest.devicesUpserted, 0) : '-' },
              { label: '端口写入', value: latest ? number(latest.portsUpserted, 0) : '-' },
              { label: '过期设备', value: latest ? number(latest.staleDevices, 0) : '-' },
            ]}
          />
        </section>

        <section className="panel sync-detail-panel">
          <div className="section-head">
            <h2>最近运行</h2>
            <span className="rail-workspace-badge">{latest ? `#${latest.id}` : '暂无记录'}</span>
          </div>
          <div className="sync-detail-list">
            <div className="sync-detail-row">
              <span>运行状态</span>
              <div className="sync-detail-value"><StatusPill value={statusTone} /></div>
            </div>
            <div className="sync-detail-row">
              <span>开始时间</span>
              <strong>{dateTime(latest?.startedAt)}</strong>
            </div>
            <div className="sync-detail-row">
              <span>结束时间</span>
              <strong>{dateTime(latest?.finishedAt)}</strong>
            </div>
            <div className="sync-detail-row">
              <span>耗时</span>
              <strong>{latest?.durationMs ? `${number(latest.durationMs, 0)} ms` : '-'}</strong>
            </div>
            <div className="sync-detail-row">
              <span>设备总数</span>
              <strong>{latest ? number(latest.devicesSeen, 0) : '-'}</strong>
            </div>
            <div className="sync-detail-row">
              <span>设备写入</span>
              <strong>{latest ? number(latest.devicesUpserted, 0) : '-'}</strong>
            </div>
            <div className="sync-detail-row">
              <span>端口写入</span>
              <strong>{latest ? number(latest.portsUpserted, 0) : '-'}</strong>
            </div>
            <div className="sync-detail-row">
              <span>过期设备</span>
              <strong>{latest ? number(latest.staleDevices, 0) : '-'}</strong>
            </div>
            <div className="sync-detail-row">
              <span>Host 明细</span>
              <strong>{detailHostids == null ? '-' : `${detailHostids} 个 hostid`}</strong>
            </div>
          </div>
          {latest?.errorMessage ? <div className="error-panel">最近同步错误：{latest.errorMessage}</div> : <div className="muted-note tight">最近同步结果会显示在这里。</div>}
        </section>

        <section className="panel sync-history-panel">
          <div className="section-head">
            <h2>数据质量</h2>
            <span className="rail-workspace-badge">{quality.data?.length || 0} 项</span>
          </div>
          {(quality.data || []).length ? (
            <div className="quality-list">
              {(quality.data || []).slice(0, 12).map((issue) => (
                <div className={`quality-row ${issue.severity}`} key={issue.id}>
                  <AlertTriangle size={15} />
                  <span>
                    <strong>{issue.title}</strong>
                    <small>{issue.message}</small>
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="muted-note tight">暂未发现数据质量问题。</div>
          )}
        </section>

        <section className="panel sync-history-panel">
          <div className="section-head">
            <h2>操作审计</h2>
            <span className="rail-workspace-badge">{audit.data?.length || 0} 条</span>
          </div>
          {(audit.data || []).length ? (
            <div className="sync-history-list">
              {(audit.data || []).map((item) => (
                <div className="sync-history-row" key={item.id}>
                  <div className="sync-history-main">
                    <strong>{item.action}</strong>
                    <span>{item.resourceType} {item.resourceId || '-'}</span>
                  </div>
                  <div className="sync-history-metrics">
                    <span>{item.actor || 'system'}</span>
                    <span>{dateTime(item.createdAt)}</span>
                  </div>
                  <div className="sync-history-state">
                    <History size={15} />
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="muted-note tight">还没有操作审计记录。</div>
          )}
        </section>

        <section className="panel sync-history-panel">
          <div className="section-head">
            <h2>最近历史</h2>
            <span className="rail-workspace-badge">{history.length} 条</span>
          </div>
          {history.length ? (
            <div className="sync-history-list">
              {history.map((item) => (
                <div className="sync-history-row" key={item.id}>
                  <div className="sync-history-main">
                    <strong>{dateTime(item.startedAt)}</strong>
                    <span>{item.status === 'success' ? '成功' : item.status === 'failed' ? '失败' : '运行中'}</span>
                  </div>
                  <div className="sync-history-metrics">
                    <span>设备 {number(item.devicesUpserted, 0)}</span>
                    <span>端口 {number(item.portsUpserted, 0)}</span>
                    <span>过期 {number(item.staleDevices, 0)}</span>
                    <span>{item.durationMs ? `${number(item.durationMs, 0)} ms` : '-'}</span>
                  </div>
                  <div className="sync-history-state">
                    <StatusPill value={item.status === 'success' ? 'ok' : item.status === 'failed' ? 'critical' : 'unknown'} />
                    {item.errorMessage ? <small title={item.errorMessage}>{item.errorMessage}</small> : null}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="muted-note tight">还没有同步历史。</div>
          )}
        </section>

        <section className="panel sync-push-panel sync-history-panel">
          <div className="section-head">
            <h2>{t('pushSync')}</h2>
            <span className="rail-workspace-badge">{t('syncSource')}</span>
          </div>
          <div className="muted-note tight">{t('pushPayloadHint')}</div>

          <div className="compact-toolbar" role="group" aria-label="推送模板">
            {syncPushTemplates.map((template) => (
              <button
                key={template.key}
                className={`icon-button ${selectedTemplateKey === template.key ? 'is-active' : ''}`}
                type="button"
            title={`${template.title}`}
                onClick={() => setTemplateByKey(template.key)}
              >
                <CircleSlash2 size={14} />
                <span>{template.label}</span>
              </button>
            ))}
          </div>

          <label className="compact-checkbox">
            <input
              type="checkbox"
              checked={strictPhysicalPorts}
              onChange={(event) => setStrictPhysicalPorts(event.target.checked)}
            />
            {t('strictPhysical') || '严格物理口模式'}
          </label>

          <label className="inline-form-item">
            <span>{t('dataSource')}</span>
            <select
              value={ingestSource}
              onChange={(event) => setIngestSource(event.target.value)}
            >
              <option value="agent">agent</option>
              <option value="zabbix">zabbix</option>
              <option value="command">command</option>
              <option value="manual">manual</option>
            </select>
          </label>

          <label className="inline-form-item">
            <span>端口名匹配关键词（回车或逗号分隔）</span>
            <textarea
              className="sync-push-patterns"
              value={physicalPortNamePatterns}
              onChange={(event) => setPhysicalPortNamePatterns(event.target.value)}
              placeholder="wan\nlan\nge\nxe\nxge\neth\n"
              rows={2}
            />
          </label>

          <label className="inline-form-item">
            <span>每设备物理口上限（空/小于或等于 0 表示不限制）</span>
            <input
              type="number"
              min={0}
              value={maxPhysicalPortsPerDevice}
              onChange={(event) => setMaxPhysicalPortsPerDevice(event.target.value)}
              placeholder="例如 8"
            />
          </label>

          <div className="sync-push-form">
            <div className="workbench-toolbar sync-toolbar">
              <button className="text-button" type="button" onClick={runPush} disabled={push.isPending || commandPush.isPending} title={t('push') || '提交推送'}>
                <Send size={16} />
                {push.isPending ? '推送中...' : '提交推送'}
              </button>
              <button
                className="text-button"
                type="button"
                onClick={runCommandPush}
                disabled={push.isPending || commandPush.isPending}
                title="从服务器端命令推送"
              >
                <Terminal size={16} />
                {commandPush.isPending ? '命令推送中...' : '命令推送'}
              </button>
              <button
                className="icon-button"
                type="button"
                onClick={copyCommandPushCurl}
                title="复制服务器端 curl 命令"
                aria-label="复制服务器端 curl 命令"
              >
                <Copy size={16} />
              </button>
            </div>
            <textarea
              className="sync-push-textarea"
              value={pushPayloadText}
              onChange={(event) => updateJsonPayload(event.target.value)}
              spellCheck={false}
            />
            {pushPayloadError ? <div className="error-panel compact">JSON 错误：{pushPayloadError}</div> : null}
            {pushPayloadSummary ? <div className="muted-note compact">{pushPayloadSummary}</div> : null}
          </div>
        </section>

        <section className="panel sync-history-panel">
          <div className="section-head">
            <h2>ip -d addr 解析</h2>
            <span className="rail-workspace-badge">服务器网卡</span>
          </div>
          <div className="port-form-grid">
            <label>
              <span>设备显示名</span>
              <input value={ipAddrDeviceName} onChange={(event) => setIpAddrDeviceName(event.target.value)} placeholder="compute-01" />
            </label>
            <label>
              <span>管理 IP</span>
              <input value={ipAddrMgmtIp} onChange={(event) => setIpAddrMgmtIp(event.target.value)} placeholder="可选" />
            </label>
            <label>
              <span>目标拓扑</span>
              <select value={ipAddrTopologyId} onChange={(event) => setIpAddrTopologyId(event.target.value ? Number(event.target.value) : '')}>
                <option value="">默认拓扑</option>
                {(topologies.data || []).map((topology) => (
                  <option key={topology.id} value={topology.id}>
                    {topology.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <textarea
            className="sync-push-textarea"
            value={ipAddrOutput}
            onChange={(event) => {
              setIpAddrOutput(event.target.value);
              setIpAddrError('');
              setIpAddrSummary('');
            }}
            placeholder="建议粘贴服务器上的 ip -d addr 输出；普通 ip addr 也可用"
            spellCheck={false}
          />
          <div className="rail-workspace-actions">
            <button className="text-button" type="button" onClick={runIpAddrPush} disabled={ipAddrPush.isPending}>
              <Terminal size={16} />
              {ipAddrPush.isPending ? '解析中...' : '解析并推送'}
            </button>
          </div>
          {ipAddrError ? <div className="error-panel compact">{ipAddrError}</div> : null}
          {ipAddrSummary ? <div className="muted-note compact">{ipAddrSummary}</div> : null}
        </section>
      </div>
    </div>
  );
}

function shellQuote(value: string) {
  return `'${value.replace(/'/g, "'\\''")}'`;
}
