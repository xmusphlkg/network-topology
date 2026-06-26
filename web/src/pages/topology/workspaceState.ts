import { defaultSwitchPortLayoutKey, normalizeSwitchPortLayoutKey } from '../../lib/switchPortLayouts';

export type RailToolKey = 'members' | 'discovery' | 'inspector';

export interface RailWorkspaceState {
  overviewOpen: boolean;
  activeTool: RailToolKey;
}

const railWorkspaceStorageKey = 'switch-topology:topology-rail-workspace';
const topologyPortLayoutStorageKey = 'switch-topology:switch-port-layout';
const devicePortLayoutStorageKey = 'switch-topology:device-port-layouts';

function isRailToolKey(value: unknown): value is RailToolKey {
  return value === 'members' || value === 'discovery' || value === 'inspector';
}

export function loadRailWorkspaceState(): RailWorkspaceState {
  const fallback: RailWorkspaceState = {
    overviewOpen: true,
    activeTool: 'members',
  };
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = window.localStorage.getItem(railWorkspaceStorageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<RailWorkspaceState> & Partial<Record<'overview' | RailToolKey, boolean>>;
    return {
      overviewOpen:
        typeof parsed.overviewOpen === 'boolean'
          ? parsed.overviewOpen
          : typeof parsed.overview === 'boolean'
            ? parsed.overview
            : fallback.overviewOpen,
      activeTool:
        isRailToolKey(parsed.activeTool)
          ? parsed.activeTool
          : parsed.members
            ? 'members'
            : parsed.discovery
              ? 'discovery'
              : parsed.inspector
                ? 'inspector'
                : fallback.activeTool,
    };
  } catch {
    return fallback;
  }
}

export function saveRailWorkspaceState(state: RailWorkspaceState) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(railWorkspaceStorageKey, JSON.stringify(state));
}

export function loadSwitchPortLayout(): string {
  if (typeof window === 'undefined') return defaultSwitchPortLayoutKey;
  try {
    return normalizeSwitchPortLayoutKey(window.localStorage.getItem(topologyPortLayoutStorageKey));
  } catch {
    return defaultSwitchPortLayoutKey;
  }
}

export function saveSwitchPortLayout(layoutKey: string) {
  if (typeof window === 'undefined') return;
  window.localStorage.setItem(topologyPortLayoutStorageKey, layoutKey);
}

export function loadDevicePortLayouts(topologyId: number | null): Record<number, string> {
  if (typeof window === 'undefined' || topologyId == null) return {};
  try {
    const raw = window.localStorage.getItem(devicePortLayoutStorageKey);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, Record<string, string>>;
    const scoped = parsed[String(topologyId)] || {};
    return Object.fromEntries(
      Object.entries(scoped)
        .map(([deviceId, layoutKey]) => [Number(deviceId), normalizeSwitchPortLayoutKey(layoutKey)] as const)
        .filter(([deviceId]) => Number.isFinite(deviceId)),
    );
  } catch {
    return {};
  }
}

export function saveDevicePortLayouts(topologyId: number | null, layouts: Record<number, string>) {
  if (typeof window === 'undefined' || topologyId == null) return;
  let parsed: Record<string, Record<string, string>> = {};
  try {
    const raw = window.localStorage.getItem(devicePortLayoutStorageKey);
    parsed = raw ? JSON.parse(raw) : {};
  } catch {
    parsed = {};
  }
  parsed[String(topologyId)] = Object.fromEntries(
    Object.entries(layouts).map(([deviceId, layoutKey]) => [deviceId, normalizeSwitchPortLayoutKey(layoutKey)]),
  );
  window.localStorage.setItem(devicePortLayoutStorageKey, JSON.stringify(parsed));
}
