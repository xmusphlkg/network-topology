import type { Port } from '../types';

export function isVirtualPortName(name: string): boolean {
  const text = (name || '').trim().toLowerCase();
  if (!text) return false;

  // Common virtual/aggregate/stack interface naming patterns
  if (/^vlan\d*/.test(text)) return true;
  if (/^vwan\d*/.test(text)) return true;
  if (/^vlanif\d*/.test(text)) return true;
  if (/^vxlan\d*/.test(text)) return true;
  if (/^vpc\d*/.test(text)) return true;
  if (/^lo\d*$/.test(text)) return true;
  if (/^loopback$/.test(text)) return true;
  if (/^vir(?![a-z])/i.test(text)) return true;

  return (
    /^(docker|veth|virbr|tun|tap|wg|br\d*|bridge\d*|bond\d*|dummy\d*|ifb\d*)\b/.test(text) ||
    /^v\w{0,2}lan\d*[./:.-]?\w*$/.test(text) ||
    /(?:^|[^a-z0-9])(vlan|vlanif|vwan|vxlan|vpc|bridge|dummy|ifb)\d*[a-z0-9_.:@-]*/.test(text) ||
    /(?:^|[^a-z0-9])interface\s+(vlan|vwan|vxlan)\d*/.test(text)
  );
}

export function physicalPorts(ports: Port[]): Port[] {
  return (ports || []).filter((port) => !isVirtualPortName(port.name));
}
