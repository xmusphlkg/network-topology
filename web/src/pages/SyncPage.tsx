import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { RefreshCw } from 'lucide-react';
import { api } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import { CopyLinkButton } from '../components/CopyLinkButton';
import { dateTime, number } from '../lib/format';
import { MetricStrip } from '../components/MetricStrip';
import { StatusPill } from '../components/StatusPill';

export function SyncPage() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: queryKeys.topologySyncStatus(), queryFn: api.syncStatus, refetchInterval: 10000 });
  const runs = useQuery({ queryKey: queryKeys.syncRuns(8), queryFn: () => api.syncRuns(8), refetchInterval: 15000 });
  const run = useMutation({
    mutationFn: () => api.runSync(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.topologySyncStatus() });
      queryClient.invalidateQueries({ queryKey: queryKeys.syncRuns() });
    },
  });
  const latest = status.data?.latest;
  const history = runs.data || [];
  const statusText = latest ? (latest.status === 'success' ? '正常' : latest.status === 'failed' ? '失败' : '运行中') : '待同步';
  const statusTone = latest ? (latest.status === 'success' ? 'ok' : latest.status === 'failed' ? 'critical' : 'unknown') : 'unknown';
  const configuredText = status.data?.zabbixConfigured ? '已配置' : '未配置';

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
              <button className="text-button" type="button" onClick={() => run.mutate()} disabled={run.isPending || status.isFetching}>
                <RefreshCw size={16} />立即同步
              </button>
              <button className="text-button" type="button" onClick={() => status.refetch()} disabled={status.isFetching}>
                刷新状态
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
          </div>
          {latest?.errorMessage ? <div className="error-panel">最近同步错误：{latest.errorMessage}</div> : <div className="muted-note tight">最近同步结果会显示在这里。</div>}
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
      </div>
    </div>
  );
}
