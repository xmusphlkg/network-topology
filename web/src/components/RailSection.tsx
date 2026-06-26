import type { ReactNode } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';

interface Props {
  title: string;
  panelKey: string;
  open: boolean;
  onToggle: () => void;
  badge?: string;
  action?: ReactNode;
  children: ReactNode;
}

export function RailSection({ title, panelKey, open, onToggle, badge, action, children }: Props) {
  return (
    <section className={`rail-section panel ${panelKey} ${open ? 'is-open' : 'is-collapsed'}`}>
      <button type="button" className="rail-section-toggle" onClick={onToggle} aria-expanded={open}>
        <span className="rail-section-title">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          <strong>{title}</strong>
        </span>
        <span className="rail-section-badge">{badge || ''}</span>
      </button>
      {open ? (
        <div className="rail-section-body">
          {action ? <div className="rail-section-action">{action}</div> : null}
          {children}
        </div>
      ) : null}
    </section>
  );
}
