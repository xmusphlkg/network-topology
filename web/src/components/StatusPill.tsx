const labels: Record<string, string> = {
  ok: '正常',
  warning: '关注',
  critical: '严重',
  offline: '离线',
  stale: '过期',
  unknown: '未知',
  up: 'up',
  down: 'down',
  shutdown: '关闭',
};

export function StatusPill({ value }: { value: string }) {
  return <span className={`status-pill ${tone(value)}`}>{labels[value] || value}</span>;
}

function tone(value: string) {
  if (['ok', 'up', 'active'].includes(value)) return 'ok';
  if (['critical', 'offline', 'down'].includes(value)) return 'bad';
  if (['warning', 'stale', 'lower-layer-down'].includes(value)) return 'warn';
  return 'muted';
}

