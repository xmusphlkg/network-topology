export interface SwitchPortLayoutTemplate {
  key: string;
  label: string;
  description: string;
  columns: number | null;
  rows: 1 | 2;
  compact: boolean;
  arrangement: 'sequential' | 'odd-even' | 'server';
  hideVirtual: boolean;
  hint: string;
}

export const switchPortLayoutTemplates: SwitchPortLayoutTemplate[] = [
  {
    key: 'single-row',
    label: '单排',
    description: '端口按自然顺序单排横向排列',
    columns: null,
    rows: 1,
    compact: false,
    arrangement: 'sequential',
    hideVirtual: true,
    hint: '所有端口在一行完整显示',
  },
  {
    key: 'double-row-horizontal',
    label: '双排横向',
    description: '先排满上排，再排下排，例如 1-12 / 13-24',
    columns: null,
    rows: 2,
    compact: false,
    arrangement: 'sequential',
    hideVirtual: true,
    hint: '横向顺序读取，适合前面板上下两排',
  },
  {
    key: 'double-row-vertical',
    label: '双排纵向',
    description: '按列成对排列，例如上排 1/3/5，下排 2/4/6',
    columns: null,
    rows: 2,
    compact: false,
    arrangement: 'odd-even',
    hideVirtual: true,
    hint: '纵向顺序读取，贴近很多交换机端口编号方式',
  },
] as const;

export const defaultSwitchPortLayoutKey = 'double-row-vertical';

export function normalizeSwitchPortLayoutKey(raw: string | null): string {
  if (raw && switchPortLayoutTemplates.some((item) => item.key === raw)) {
    return raw;
  }
  return defaultSwitchPortLayoutKey;
}

export function getSwitchPortLayout(key: string): SwitchPortLayoutTemplate {
  return switchPortLayoutTemplates.find((item) => item.key === key) || switchPortLayoutTemplates[0];
}
