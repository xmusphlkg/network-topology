export function bps(value?: number | null): string {
  if (value === null || value === undefined) return '-';
  const units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps'];
  let scaled = Math.max(value, 0);
  let unit = 0;
  while (scaled >= 1000 && unit < units.length - 1) {
    scaled /= 1000;
    unit += 1;
  }
  return `${scaled >= 10 ? scaled.toFixed(0) : scaled.toFixed(1)} ${units[unit]}`;
}

export function speed(value?: number | null): string {
  if (!value) return '-';
  if (value >= 1000) {
    const gbps = value / 1000;
    return `${gbps % 1 === 0 ? gbps.toFixed(0) : gbps.toFixed(1)}G`;
  }
  return `${value % 1 === 0 ? value.toFixed(0) : value.toFixed(1)}M`;
}

export function dateTime(value?: string | null): string {
  if (!value) return '-';
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(new Date(value));
}

export function number(value?: number | null, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
}
