import type { ReactNode } from 'react';
import { Box, Network, Server } from 'lucide-react';
import type { Device } from '../types';
import { StatusPill } from './StatusPill';

interface Props {
  device: Device;
  active?: boolean;
  asButton?: boolean;
  title?: string;
  trailing?: ReactNode;
  meta?: ReactNode;
  className?: string;
  onClick?: () => void;
}

export function DeviceCompactCard({
  device,
  active = false,
  asButton = false,
  title,
  trailing,
  meta,
  className = '',
  onClick,
}: Props) {
  const Icon = device.role === 'switch' ? Network : device.role === 'server' ? Server : Box;
  const content = (
    <>
      <Icon size={15} />
      <span className="device-compact-main">
        <strong>{device.displayName}</strong>
        <small>{device.mgmtIp || device.model || device.source || device.role}</small>
      </span>
      <span className="device-compact-side">
        {trailing ?? <StatusPill value={device.health} />}
        {meta}
      </span>
    </>
  );
  const classes = `device-compact-card ${active ? 'is-active' : ''} ${className}`.trim();

  if (asButton || onClick) {
    return (
      <button type="button" className={classes} title={title || device.displayName} onClick={onClick}>
        {content}
      </button>
    );
  }

  return (
    <div className={classes} title={title || device.displayName}>
      {content}
    </div>
  );
}
