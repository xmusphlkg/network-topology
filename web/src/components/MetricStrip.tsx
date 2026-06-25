import type { ReactNode } from 'react';

export interface MetricItem {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
}

interface Props {
  items: MetricItem[];
}

export function MetricStrip({ items }: Props) {
  return (
    <section className="summary-strip" aria-label="关键指标">
      {items.map((item) => (
        <div className="summary-item" key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
          {item.detail ? <small>{item.detail}</small> : null}
        </div>
      ))}
    </section>
  );
}
