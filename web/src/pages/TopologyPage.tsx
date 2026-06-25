import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  applyNodeChanges,
  type Edge,
  type Node,
  type NodeChange,
  type ReactFlowInstance,
} from '@xyflow/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Activity, Box, Cable, Check, ChevronDown, ChevronRight, Download, Link, Network, Plus, RefreshCw, Save, Search, Server, Upload } from 'lucide-react';
import { api } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { CableLink, Device, Port, ZabbixDiscoveredDevice } from '../types';
import { SwitchNode, EndpointNode } from '../components/TopologyNodes';
import { StatusPill } from '../components/StatusPill';
import { useFeedback } from '../components/FeedbackCenter';

const nodeTypes = { switchNode: SwitchNode, endpointNode: EndpointNode };
type DeviceRoleFilter = 'all' | 'switch' | 'server' | 'custom';
type RailToolKey = 'members' | 'discovery' | 'inspector';
type PendingLink = { a: Port; b?: Port };
interface RailWorkspaceState {
  overviewOpen: boolean;
  activeTool: RailToolKey;
}

const railWorkspaceStorageKey = 'switch-topology:topology-rail-workspace';

function isRailToolKey(value: unknown): value is RailToolKey {
  return value === 'members' || value === 'discovery' || value === 'inspector';
}

function loadRailWorkspaceState(): RailWorkspaceState {
  const fallback: RailWorkspaceState = {
    overviewOpen: true,
    activeTool: 'members',
  };
  if (typeof window === 'undefined') return fallback;
  try {
    const raw = window.localStorage.getItem(railWorkspaceStorageKey);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Partial<RailWorkspaceState> & Partial<Record<'overview' | 'members' | 'discovery' | 'inspector', boolean>>;
    return {
      overviewOpen: typeof parsed.overviewOpen === 'boolean' ? parsed.overviewOpen : typeof parsed.overview === 'boolean' ? parsed.overview : fallback.overviewOpen,
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

export function TopologyPage() {
  const queryClient = useQueryClient();
  const feedback = useFeedback();
  const [searchParams, setSearchParams] = useSearchParams();
  const jsonImportRef = useRef<HTMLInputElement | null>(null);
  const topologies = useQuery({ queryKey: queryKeys.topologies(), queryFn: () => api.topologies() });
  const syncStatus = useQuery({ queryKey: queryKeys.topologySyncStatus(), queryFn: api.syncStatus, staleTime: 30000 });
  const [topologyId, setTopologyId] = useState<number | null>(null);
  const [selectedPort, setSelectedPort] = useState<Port | null>(null);
  const [connectMode, setConnectMode] = useState(false);
  const [pendingLink, setPendingLink] = useState<PendingLink | null>(null);
  const [editingCable, setEditingCable] = useState<CableLink | null>(null);
  const [cableNo, setCableNo] = useState('');
  const [label, setLabel] = useState('');
  const [notes, setNotes] = useState('');
  const [newTopologyName, setNewTopologyName] = useState('');
  const [newTopologyDefault, setNewTopologyDefault] = useState(false);
  const [movedNodes, setMovedNodes] = useState<Record<string, { x: number; y: number }>>({});
  const [layoutDirty, setLayoutDirty] = useState(false);
  const [lastSavedLayout, setLastSavedLayout] = useState<number | null>(null);
  const [discoveredSelection, setDiscoveredSelection] = useState<Set<string>>(new Set());
  const [topologyDeviceSelection, setTopologyDeviceSelection] = useState<Set<number>>(new Set());
  const [deviceRoleFilter, setDeviceRoleFilter] = useState<DeviceRoleFilter>('all');
  const [highlightedDeviceId, setHighlightedDeviceId] = useState<number | null>(null);
  const [deviceSearch, setDeviceSearch] = useState('');
  const [deviceOverviewSearch, setDeviceOverviewSearch] = useState('');
  const [railWorkspace, setRailWorkspace] = useState<RailWorkspaceState>(() => loadRailWorkspaceState());
  const [layoutKey, setLayoutKey] = useState('default');
  const [hasRestoredViewport, setHasRestoredViewport] = useState(false);
  const topologyIdParam = searchParams.get('topologyId') || '';
  const activeRailTool = railWorkspace.activeTool;
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(railWorkspaceStorageKey, JSON.stringify(railWorkspace));
  }, [railWorkspace]);

  useEffect(() => {
    if (!topologies.data?.length) return;
    const requestedId = Number(topologyIdParam);
    const hasRequestedTopology = topologyIdParam && !Number.isNaN(requestedId) && topologies.data.some((topology) => topology.id === requestedId);
    if (hasRequestedTopology && topologyId !== requestedId) {
      setTopologyId(requestedId);
      return;
    }
    const found = topologyId !== null ? topologies.data.find((topology) => topology.id === topologyId) : null;
    if (found) return;
    const defaultTopology = topologies.data.find((topology) => topology.isDefault) || topologies.data[0];
    setTopologyId(defaultTopology.id);
    if (topologyIdParam !== String(defaultTopology.id)) {
      setSearchParams({ topologyId: String(defaultTopology.id) }, { replace: true });
    }
    setLayoutKey(`topology:${defaultTopology.id}`);
  }, [setSearchParams, topologyId, topologyIdParam, topologies.data]);

  const topologyQuery = useQuery({
    queryKey: queryKeys.topology(topologyId),
    queryFn: () => api.topology(topologyId || undefined),
    enabled: topologyId !== null,
  });

  useEffect(() => {
    setLayoutKey(topologyId ? `topology:${topologyId}` : 'default');
    setMovedNodes({});
    setLayoutDirty(false);
    setLastSavedLayout(null);
    setSelectedPort(null);
    setEditingCable(null);
    setPendingLink(null);
    setHasRestoredViewport(false);
    setDiscoveredSelection(new Set());
    setTopologyDeviceSelection(new Set());
    setDeviceRoleFilter('all');
    setHighlightedDeviceId(null);
    setDeviceSearch('');
  }, [topologyId]);

  useEffect(() => {
    if (!topologyId) return;
    if (topologyIdParam !== String(topologyId)) {
      setSearchParams({ topologyId: String(topologyId) }, { replace: true });
    }
  }, [setSearchParams, topologyId, topologyIdParam]);

  const discovered = useQuery({
    queryKey: queryKeys.zabbixDiscovered(topologyId),
    queryFn: () => api.discoveredZabbixDevices(topologyId || undefined),
    enabled: topologyId !== null && syncStatus.data?.zabbixConfigured === true && activeRailTool === 'discovery',
    retry: false,
  });

  const devices = useQuery({
    queryKey: queryKeys.devices({ includeDisabled: true }),
    queryFn: () => api.devices({ includeDisabled: true }),
  });

  const createTopology = useMutation({
    mutationFn: () => api.createTopology({ name: newTopologyName.trim() || '新建拓扑', isDefault: newTopologyDefault }),
    onSuccess: (created) => {
      setNewTopologyName('');
      setNewTopologyDefault(false);
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      setTopologyId(created.id);
      setLayoutKey(`topology:${created.id}`);
      feedback.pushToast('拓扑已创建', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const createCable = useMutation({
    mutationFn: api.createCable,
    onSuccess: () => {
      setSelectedPort(null);
      setPendingLink(null);
      setCableNo('');
      setLabel('');
      setNotes('');
      setLastSavedLayout(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      queryClient.invalidateQueries({ queryKey: queryKeys.ports() });
      feedback.pushToast('线缆已添加', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const runSync = useMutation({
    mutationFn: () => {
      if (!topologyId) return api.runSync();
      return api.runSync(topologyId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.topologySyncStatus() });
      queryClient.invalidateQueries({ queryKey: queryKeys.zabbixDiscovered(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      feedback.pushToast('同步任务已启动', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const importSelected = useMutation({
    mutationFn: () => api.importZabbixToTopology(topologyId || 0, Array.from(discoveredSelection)),
    onSuccess: () => {
      setDiscoveredSelection(new Set());
      queryClient.invalidateQueries({ queryKey: queryKeys.zabbixDiscovered(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      feedback.pushToast('选中主机已导入', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const importAll = useMutation({
    mutationFn: () => api.importZabbixToTopology(topologyId || 0, []),
    onSuccess: () => {
      setDiscoveredSelection(new Set());
      queryClient.invalidateQueries({ queryKey: queryKeys.zabbixDiscovered(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      feedback.pushToast('全部可导入主机已入拓扑', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const attachDevices = useMutation({
    mutationFn: (deviceIds: number[]) => api.assignDevicesToTopology(topologyId || 0, { deviceIds }),
    onSuccess: () => {
      setTopologyDeviceSelection(new Set());
      queryClient.invalidateQueries({ queryKey: queryKeys.devices() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      feedback.pushToast('设备已加入拓扑', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const importTopologyJson = useMutation({
    mutationFn: (payload: Record<string, unknown>) => api.importTopologyJson(topologyId || 0, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devices() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      feedback.pushToast('拓扑 JSON 已导入', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const saveLayout = useMutation({
    mutationFn: (payload: {
      nodes: Array<{ nodeId: string; x: number; y: number }>;
      viewport?: { x: number; y: number; zoom: number };
    }) => api.saveLayout(payload.nodes, layoutKey, payload.viewport),
    onSuccess: () => {
      setLayoutDirty(false);
      setLastSavedLayout(Date.now());
      feedback.pushToast('布局已保存', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const updateCable = useMutation({
    mutationFn: (payload: { id: number; cableNo?: string | null; label?: string | null; notes?: string | null }) =>
      api.updateCable(payload.id, {
        cableNo: payload.cableNo,
        label: payload.label,
        notes: payload.notes,
      }),
    onSuccess: () => {
      setEditingCable(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      feedback.pushToast('线缆信息已保存', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const deleteCable = useMutation({
    mutationFn: (linkId: number) => api.deleteCable(linkId),
    onSuccess: () => {
      setEditingCable(null);
      setPendingLink(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.ports() });
      feedback.pushToast('线缆已删除', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const candidatePortId = connectMode ? selectedPort?.id || null : null;

  const derivedNodes = useMemo<Node[]>(() => {
    const serverNodes = topologyQuery.data?.nodes || [];
    return serverNodes.map((node) => ({
      ...node,
      data: {
        ...node.data,
        highlighted: highlightedDeviceId === node.data.device.id,
        selectedPortId: selectedPort?.id,
        candidatePortId,
        onPortClick: (port: Port) => {
          if (!connectMode) {
            setSelectedPort(port);
            setEditingCable(null);
            setPendingLink(null);
            setCableNo('');
            setLabel('');
            setNotes('');
            return;
          }
          const normalizedPending = pendingLink;
          if (!normalizedPending || !normalizedPending.b) {
            setPendingLink({ a: port });
            setSelectedPort(port);
            setCableNo('');
            setLabel('');
            setNotes('');
            return;
          }
          if (normalizedPending.a.id === port.id) {
            setPendingLink(null);
            setSelectedPort(null);
            return;
          }
          setPendingLink({ ...normalizedPending, b: port });
          setCableNo('');
          setLabel(`${normalizedPending.a.name} - ${port.name}`);
          setNotes('');
          setSelectedCable(null);
          setActiveRailTool('inspector');
          setRailWorkspace((current) => (current.activeTool === 'inspector' ? current : { ...current, activeTool: 'inspector' }));
        },
      },
    }));
  }, [candidatePortId, connectMode, highlightedDeviceId, pendingLink, selectedPort, topologyQuery.data?.nodes]);

  const [nodes, setNodes] = useState<Node[]>([]);

  useEffect(() => {
    setNodes((currentNodes) => {
      const currentById = new Map(currentNodes.map((node) => [node.id, node]));
      return derivedNodes.map((node) => {
        const current = currentById.get(node.id);
        return {
          ...node,
          position: movedNodes[node.id] || current?.position || node.position,
          measured: current?.measured,
          width: current?.width,
          height: current?.height,
          selected: current?.selected,
          dragging: current?.dragging,
        };
      });
    });
  }, [derivedNodes, movedNodes]);

  const edges = useMemo<Edge[]>(() => (topologyQuery.data?.edges || []).map((edge) => ({ ...edge, animated: false })), [topologyQuery.data?.edges]);
  const deviceById = useMemo(() => new Map((topologyQuery.data?.devices || []).map((device) => [device.id, device])), [topologyQuery.data?.devices]);

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((currentNodes) => {
        const nextNodes = applyNodeChanges(changes, currentNodes);
        const moved: Record<string, { x: number; y: number }> = {};
        changes.forEach((change) => {
          if (change.type === 'position' && 'position' in change && change.position) {
            moved[change.id] = change.position;
          }
        });
        if (Object.keys(moved).length) {
          setMovedNodes((current) => ({ ...current, ...moved }));
          setLayoutDirty(true);
        }
        return nextNodes;
      });
    },
    [],
  );

  const candidatePort = pendingLink?.b;

  function applyLayoutViewport(topologyIdValue: number | null) {
    if (!flowInstance || topologyIdValue == null || hasRestoredViewport) return;
    const layoutViewport = topologyQuery.data?.layout?.viewport;
    if (!layoutViewport || typeof layoutViewport !== 'object') {
      flowInstance.fitView({ padding: 0.18, maxZoom: 1 });
      setHasRestoredViewport(true);
      return;
    }
    const x = Number((layoutViewport as { x?: number }).x);
    const y = Number((layoutViewport as { y?: number }).y);
    const zoom = Number((layoutViewport as { zoom?: number }).zoom);
    if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(zoom)) {
      flowInstance.setViewport({ x, y, zoom });
    }
    setHasRestoredViewport(true);
  }

  function handleFlowInit(instance: ReactFlowInstance) {
    setFlowInstance(instance);
    applyLayoutViewport(topologyId);
  }

  function handleEdgeClick(_: unknown, edge: Edge) {
    const edgeCableId = edge.data?.linkId;
    if (typeof edgeCableId !== 'number') return;
    const targetCable = (topologyQuery.data?.cableLinks || []).find((cable) => cable.id === edgeCableId);
    if (!targetCable) return;
    setEditingCable(targetCable);
    setSelectedPort(null);
    setPendingLink(null);
    setCableNo(targetCable.cableNo || '');
    setLabel(targetCable.label || '');
    setNotes(targetCable.notes || '');
    setActiveRailTool('inspector');
    setRailWorkspace((current) => (current.activeTool === 'inspector' ? current : { ...current, activeTool: 'inspector' }));
  }

  useEffect(() => {
    applyLayoutViewport(topologyId);
  }, [applyLayoutViewport, topologyId, topologyQuery.data?.layout?.viewport, topologyQuery.data?.nodes, flowInstance]);

  useEffect(() => {
    if (!connectMode) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setPendingLink(null);
        setSelectedPort(null);
        setEditingCable(null);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [connectMode]);

  const zabbixChecking = syncStatus.isLoading;
  const zabbixConfigured = syncStatus.data?.zabbixConfigured === true;
  const zabbixUnavailable = syncStatus.isSuccess && !zabbixConfigured;
  const discoveryError = discovered.error instanceof Error ? discovered.error.message : null;
  const discoveredDevices = discovered.data || [];
  const unsyncedDiscovered = discoveredDevices.filter((device) => !device.synced);
  const syncedDiscovered = discoveredDevices.filter((device) => device.synced);
  const topologyDeviceIds = useMemo(
    () => new Set((topologyQuery.data?.devices || []).map((device) => device.id)),
    [topologyQuery.data?.devices],
  );
  const allDeviceById = useMemo(
    () => new Map((devices.data || []).map((device: Device) => [device.id, device])),
    [devices.data],
  );
  const availableDevices = (devices.data || []).filter((device: Device) => device.enabled && !topologyDeviceIds.has(device.id));
  const normalizedDeviceSearch = deviceSearch.trim().toLowerCase();
  const filteredAvailableDevices = availableDevices.filter((device: Device) => {
    if (!normalizedDeviceSearch) return true;
    return [device.displayName, device.mgmtIp, device.model, device.source, device.role]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(normalizedDeviceSearch);
  });
  const selectableAvailableDevices = filteredAvailableDevices.filter((device: Device) => !topologyDeviceSelection.has(device.id));
  const selectedTopologyDevices = useMemo(() => Array.from(topologyDeviceSelection), [topologyDeviceSelection]);
  const selectedAvailableDevices = selectedTopologyDevices
    .map((deviceId) => allDeviceById.get(deviceId))
    .filter((device): device is Device => Boolean(device));
  const canAddTopologyDevices = topologyId !== null && selectedTopologyDevices.length > 0;
  const topologyDevices = topologyQuery.data?.devices || [];
  const filteredTopologyDevices = topologyDevices.filter((device) => {
    const search = deviceOverviewSearch.trim().toLowerCase();
    const roleMatch =
      deviceRoleFilter === 'all'
        ? true
        : deviceRoleFilter === 'custom'
          ? device.role !== 'switch' && device.role !== 'server'
          : device.role === deviceRoleFilter;
    if (!roleMatch) return false;
    if (!search) return true;
    return [device.displayName, device.mgmtIp, device.model, device.source, device.role]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(search);
  });
  const topologyPorts = topologyQuery.data?.ports || [];
  const cableLinks = topologyQuery.data?.cableLinks || [];
  const switchCount = topologyDevices.filter((device) => device.role === 'switch').length;
  const serverCount = topologyDevices.filter((device) => device.role === 'server').length;
  const customCount = topologyDevices.filter((device) => device.role !== 'switch' && device.role !== 'server').length;
  const noPortAvailableCount = availableDevices.filter((device: Device) => device.stale).length;
  const upPortCount = topologyPorts.filter((port) => port.operStatus === 'up').length;
  const latestSync = syncStatus.data?.latest;
  const syncStatusValue = zabbixUnavailable ? 'unknown' : latestSync?.status === 'success' ? 'ok' : zabbixConfigured ? 'ok' : 'unknown';
  const syncStatusText = zabbixChecking
    ? '检查中'
    : zabbixUnavailable
      ? '未配置'
      : latestSync?.status === 'success'
        ? '同步正常'
        : latestSync?.status === 'failed'
          ? '同步失败'
          : '待同步';
  const discoverySummaryText = !zabbixConfigured
    ? '未配置'
    : activeRailTool !== 'discovery'
      ? '未展开'
      : discovered.isFetching
        ? '加载中'
        : discoveryError
          ? '错误'
          : `${unsyncedDiscovered.length} 待导入`;
  const workspaceBadge =
    activeRailTool === 'members'
      ? `${selectedTopologyDevices.length} 待加入`
      : activeRailTool === 'discovery'
        ? discoverySummaryText
        : selectedPort
          ? `${deviceById.get(selectedPort.deviceId)?.displayName || '-'} · ${selectedPort.name}`
          : editingCable
            ? `编辑线缆 ${editingCable.id}`
            : pendingLink
              ? '已选线缆'
              : '未选择';
  const hasPendingSecondPort = Boolean(pendingLink?.b);

  function submitCable(event: FormEvent) {
    event.preventDefault();
    if (editingCable) {
      updateCable.mutate({
        id: editingCable.id,
        cableNo: cableNo.trim() || null,
        label: label.trim() || null,
        notes: notes.trim() || null,
      });
      return;
    }
    if (!pendingLink || !pendingLink.b || !topologyId) return;
    createCable.mutate({
      endpointAPortId: pendingLink.a.id,
      endpointBPortId: pendingLink.b.id,
      cableNo: cableNo.trim() || undefined,
      label: label.trim() || undefined,
      notes: notes.trim() || undefined,
      color: '#3274d9',
    });
  }
            return;
          }
          setPendingLink({ ...pendingLink, b: port });
          setCableNo('');
          setLabel(`${pendingLink.a.name} - ${port.name}`);
          setNotes('');
          setSelectedCable(null);
          setActiveRailTool('inspector');
          setRailWorkspace((current) => (current.activeTool === 'inspector' ? current : { ...current, activeTool: 'inspector' }));
        },
      },
    }));
  }, [candidatePortId, connectMode, highlightedDeviceId, pendingLink, selectedPort, topologyId, topologyQuery.data?.nodes]);

  const [nodes, setNodes] = useState<Node[]>([]);

  useEffect(() => {
    setNodes((currentNodes) => {
      const currentById = new Map(currentNodes.map((node) => [node.id, node]));
      return derivedNodes.map((node) => {
        const current = currentById.get(node.id);
        return {
          ...node,
          position: movedNodes[node.id] || current?.position || node.position,
          measured: current?.measured,
          width: current?.width,
          height: current?.height,
          selected: current?.selected,
          dragging: current?.dragging,
        };
      });
    });
  }, [derivedNodes, movedNodes]);

  const edges = useMemo<Edge[]>(() => (topologyQuery.data?.edges || []).map((edge) => ({ ...edge, animated: false })), [topologyQuery.data?.edges]);
  const deviceById = useMemo(() => new Map((topologyQuery.data?.devices || []).map((device) => [device.id, device])), [topologyQuery.data?.devices]);

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((currentNodes) => {
        const nextNodes = applyNodeChanges(changes, currentNodes);
        const moved: Record<string, { x: number; y: number }> = {};
        changes.forEach((change) => {
          if (change.type === 'position' && 'position' in change && change.position) {
            moved[change.id] = change.position;
          }
        });
        if (Object.keys(moved).length) {
          setMovedNodes((current) => ({ ...current, ...moved }));
          setLayoutDirty(true);
        }
        return nextNodes;
      });
    },
    [],
  );

  function handleFlowInit(instance: ReactFlowInstance) {
    setFlowInstance(instance);
    const layoutViewport = topologyQuery.data?.layout?.viewport;
    if (!layoutViewport || typeof layoutViewport !== 'object') return;
    const x = Number((layoutViewport as { x?: number }).x);
    const y = Number((layoutViewport as { y?: number }).y);
    const zoom = Number((layoutViewport as { zoom?: number }).zoom);
    if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(zoom)) {
      instance.setViewport({ x, y, zoom });
    }
  }

  useEffect(() => {
    if (!flowInstance || !topologyId) return;
    const layoutViewport = topologyQuery.data?.layout?.viewport;
    if (!layoutViewport || typeof layoutViewport !== 'object') return;
    const x = Number((layoutViewport as { x?: number }).x);
    const y = Number((layoutViewport as { y?: number }).y);
    const zoom = Number((layoutViewport as { zoom?: number }).zoom);
    if (Number.isFinite(x) && Number.isFinite(y) && Number.isFinite(zoom)) {
      flowInstance.setViewport({ x, y, zoom });
    }
  }, [flowInstance, topologyId, topologyQuery.data?.layout?.viewport]);

  useEffect(() => {
    if (!connectMode) {
      return;
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setPendingLink(null);
        setSelectedPort(null);
        setEditingCable(null);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [connectMode]);

  const zabbixChecking = syncStatus.isLoading;
  const zabbixConfigured = syncStatus.data?.zabbixConfigured === true;
  const zabbixUnavailable = syncStatus.isSuccess && !zabbixConfigured;
  const discoveryError = discovered.error instanceof Error ? discovered.error.message : null;
  const discoveredDevices = discovered.data || [];
  const unsyncedDiscovered = discoveredDevices.filter((device) => !device.synced);
  const syncedDiscovered = discoveredDevices.filter((device) => device.synced);
  const topologyDeviceIds = useMemo(
    () => new Set((topologyQuery.data?.devices || []).map((device) => device.id)),
    [topologyQuery.data?.devices],
  );
  const allDeviceById = useMemo(
    () => new Map((devices.data || []).map((device: Device) => [device.id, device])),
    [devices.data],
  );
  const availableDevices = (devices.data || []).filter((device: Device) => device.enabled && !topologyDeviceIds.has(device.id));
  const normalizedDeviceSearch = deviceSearch.trim().toLowerCase();
  const filteredAvailableDevices = availableDevices.filter((device: Device) => {
    if (!normalizedDeviceSearch) return true;
    return [device.displayName, device.mgmtIp, device.model, device.source, device.role]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(normalizedDeviceSearch);
  });
  const selectableAvailableDevices = filteredAvailableDevices.filter((device: Device) => !topologyDeviceSelection.has(device.id));
  const selectedTopologyDevices = useMemo(() => Array.from(topologyDeviceSelection), [topologyDeviceSelection]);
  const selectedAvailableDevices = selectedTopologyDevices
    .map((deviceId) => allDeviceById.get(deviceId))
    .filter((device): device is Device => Boolean(device));
  const canAddTopologyDevices = topologyId !== null && selectedTopologyDevices.length > 0;
  const topologyDevices = topologyQuery.data?.devices || [];
  const filteredTopologyDevices = topologyDevices.filter((device) => {
    const search = deviceOverviewSearch.trim().toLowerCase();
    const roleMatch =
      deviceRoleFilter === 'all'
        ? true
        : deviceRoleFilter === 'custom'
          ? device.role !== 'switch' && device.role !== 'server'
          : device.role === deviceRoleFilter;
    if (!roleMatch) return false;
    if (!search) return true;
    return [device.displayName, device.mgmtIp, device.model, device.source, device.role]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
      .includes(search);
  });
  const topologyPorts = topologyQuery.data?.ports || [];
  const cableLinks = topologyQuery.data?.cableLinks || [];
  const switchCount = topologyDevices.filter((device) => device.role === 'switch').length;
  const serverCount = topologyDevices.filter((device) => device.role === 'server').length;
  const customCount = topologyDevices.filter((device) => device.role !== 'switch' && device.role !== 'server').length;
  const noPortAvailableCount = availableDevices.filter((device: Device) => device.stale).length;
  const upPortCount = topologyPorts.filter((port) => port.operStatus === 'up').length;
  const latestSync = syncStatus.data?.latest;
  const syncStatusValue = zabbixUnavailable ? 'unknown' : latestSync?.status === 'failed' ? 'critical' : zabbixConfigured ? 'ok' : 'unknown';
  const syncStatusText = zabbixChecking
    ? '检查中'
    : zabbixUnavailable
      ? '未配置'
      : latestSync?.status === 'success'
        ? '同步正常'
        : latestSync?.status === 'failed'
        ? '同步失败'
          : '待同步';
  const discoverySummaryText = !zabbixConfigured
    ? '未配置'
    : activeRailTool !== 'discovery'
      ? '未展开'
      : discovered.isFetching
        ? '加载中'
        : discoveryError
          ? '错误'
          : `${unsyncedDiscovered.length} 待导入`;
  const workspaceBadge =
    activeRailTool === 'members'
      ? `${selectedTopologyDevices.length} 待加入`
      : activeRailTool === 'discovery'
        ? discoverySummaryText
        : selectedPort
          ? `${deviceById.get(selectedPort.deviceId)?.displayName || '-'} · ${selectedPort.name}`
          : pendingLink
            ? '已选线缆'
            : '未选择';

  function submitCable(event: FormEvent) {
    event.preventDefault();
    if (!pendingLink || !topologyId) return;
    createCable.mutate({
      endpointAPortId: pendingLink.a.id,
      endpointBPortId: pendingLink.b.id,
      cableNo: cableNo.trim() || undefined,
      label: label.trim() || undefined,
      notes: notes.trim() || undefined,
      color: '#3274d9',
    });
  }

  function submitTopology(event: FormEvent) {
    event.preventDefault();
    createTopology.mutate();
  }

  useEffect(() => {
    if (selectedPort || pendingLink) {
      setRailWorkspace((current) => (current.activeTool === 'inspector' ? current : { ...current, activeTool: 'inspector' }));
    }
  }, [pendingLink, selectedPort]);

  function toggleDiscovery(hostid: string) {
    const next = new Set(discoveredSelection);
    if (next.has(hostid)) {
      next.delete(hostid);
    } else {
      next.add(hostid);
    }
    setDiscoveredSelection(next);
  }

  function applyHostSelection() {
    importSelected.mutate();
  }

  function addTopologyDeviceToSelection(deviceIdText: string) {
    const deviceId = Number(deviceIdText);
    if (Number.isNaN(deviceId)) return;
    setTopologyDeviceSelection((current) => {
      const next = new Set(current);
      next.add(deviceId);
      return next;
    });
  }

  function removeTopologyDeviceSelection(deviceId: number) {
    setTopologyDeviceSelection((current) => {
      const next = new Set(current);
      next.delete(deviceId);
      return next;
    });
  }

  function focusTopologyDevice(deviceId: number) {
    setHighlightedDeviceId(deviceId);
    setSelectedPort(null);
  }

  function setActiveRailTool(tool: RailToolKey) {
    setRailWorkspace((current) => ({ ...current, activeTool: tool }));
  }

  function toggleOverview() {
    setRailWorkspace((current) => ({ ...current, overviewOpen: !current.overviewOpen }));
  }

  function addSelectedTopologyDevices() {
    if (!canAddTopologyDevices || !topologyId) return;
    attachDevices.mutate(selectedTopologyDevices);
  }

  function handleTopologyChange(topologyIdText: string) {
    const nextId = Number(topologyIdText);
    if (Number.isNaN(nextId)) return;
    setTopologyId(nextId);
    setSearchParams({ topologyId: String(nextId) }, { replace: true });
  }

  function saveCurrentLayout() {
    if (!topologyId) return;
    const payload = {
      nodes: nodes.map((node) => ({ nodeId: node.id, x: node.position.x, y: node.position.y })),
      viewport: flowInstance ? { ...flowInstance.getViewport() } : undefined,
    };
    saveLayout.mutate(payload);
  }

  const hasUnsavedLayout = layoutDirty;

  useEffect(() => {
    if (!topologyId || !layoutDirty) return;
    const timer = window.setTimeout(() => {
      saveCurrentLayout();
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [layoutDirty, nodes, topologyId]);

  async function exportJson() {
    if (!topologyId) return;
    const payload = await api.exportTopologyJson(topologyId);
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${topologyQuery.data?.topologyName || 'topology'}-${topologyId}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function importJsonFile(file: File | null) {
    if (!file || !topologyId) return;
    try {
      const text = await file.text();
      const payload = JSON.parse(text) as Record<string, unknown>;
      importTopologyJson.mutate(payload);
    } catch (error) {
      feedback.pushToast(
        error instanceof Error ? error.message : 'JSON 文件无法解析',
        'error',
      );
    }
  }

  return (
    <div className="page topology-page">
      <div className="workstation-toolbar">
        <div className="toolbar-group">
          <select
            value={topologyId ?? ''}
            onChange={(event) => handleTopologyChange(event.target.value)}
            aria-label="当前拓扑"
          >
            {(topologies.data || []).map((topology) => (
              <option key={topology.id} value={topology.id}>
                {topology.name}
              </option>
            ))}
          </select>
          <button
            className="icon-button"
            onClick={() => runSync.mutate()}
            title={zabbixUnavailable ? 'Zabbix 未配置' : '同步并导入 Zabbix 主机'}
            disabled={!zabbixConfigured || runSync.isPending}
          >
            <RefreshCw size={17} />
          </button>
          <button className="text-button" onClick={saveCurrentLayout} disabled={!nodes.length || saveLayout.isPending}>
            <Save size={16} />保存布局
          </button>
          <button className="icon-button" onClick={exportJson} title="导出 JSON" disabled={!topologyId}>
            <Download size={17} />
          </button>
          <button className="icon-button" onClick={() => jsonImportRef.current?.click()} title="导入 JSON" disabled={!topologyId || importTopologyJson.isPending}>
            <Upload size={17} />
          </button>
          <input
            ref={jsonImportRef}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(event) => {
              importJsonFile(event.target.files?.[0] || null);
              event.target.value = '';
            }}
          />
        </div>
        <form className="topology-create toolbar-group" onSubmit={submitTopology}>
          <input value={newTopologyName} onChange={(event) => setNewTopologyName(event.target.value)} placeholder="新建拓扑名称" />
          <label>
            <input
              type="checkbox"
              checked={newTopologyDefault}
              onChange={(event) => setNewTopologyDefault(event.target.checked)}
            />
            设为默认
          </label>
          <button className="text-button" type="submit" disabled={createTopology.isPending}>
            <Plus size={16} />新建
          </button>
        </form>
        <div className="toolbar-spacer" />
        <div className="workstation-stats">
          <span>{topologyQuery.data?.topologyName || '加载中'}</span>
          <span>{topologyDevices.length} 设备</span>
          <span>{switchCount} 交换机</span>
          <span>{upPortCount}/{topologyPorts.length} up</span>
          <span>{cableLinks.length} 线缆</span>
          <span>{availableDevices.length} 台可加入</span>
          <span>发现 {discoverySummaryText}</span>
          <span className="status-inline">Zabbix {syncStatusText}<StatusPill value={syncStatusValue} /></span>
        </div>
      </div>

      <div className="topology-content">
        <div className="topology-primary">
          <section className="topology-canvas">
            {nodes.length ? (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                fitView
                fitViewOptions={{ padding: 0.18, maxZoom: 1 }}
                onNodesChange={handleNodesChange}
                minZoom={0.25}
                maxZoom={1.6}
              >
                <Background gap={18} color="#e5ebf3" />
                <MiniMap pannable zoomable nodeStrokeWidth={2} />
                <Controls />
              </ReactFlow>
            ) : (
              <div className="empty-canvas">
                <h2>暂无拓扑数据</h2>
                <p>
                  同步 Zabbix 后会自动出现交换机、服务器和端口；也可以在设备管理中先新增自定义设备。
                </p>
                <button className="text-button" type="button" onClick={() => runSync.mutate()} disabled={!zabbixConfigured || runSync.isPending}>
                  <RefreshCw size={16} />
                  同步 Zabbix
                </button>
              </div>
            )}
          </section>
        </div>

        <aside className="topology-rail">
          <RailSection
            title="设备概览"
            panelKey="overview"
            open={railWorkspace.overviewOpen}
            onToggle={toggleOverview}
            badge={`${filteredTopologyDevices.length}/${topologyDevices.length}`}
          >
            <div className="panel-tools">
              <label className="rail-search-wrap">
                <Search size={14} />
                <input
                  value={deviceOverviewSearch}
                  onChange={(event) => setDeviceOverviewSearch(event.target.value)}
                  placeholder="搜索设备、IP、型号"
                />
              </label>
            </div>
            <div className="role-legend">
              <button
                type="button"
                className={`role-filter ${deviceRoleFilter === 'switch' ? 'active' : ''}`}
                onClick={() => setDeviceRoleFilter(deviceRoleFilter === 'switch' ? 'all' : 'switch')}
              >
                <RoleIcon role="switch" size={14} />
                <span>交换机</span>
                <strong>{switchCount}</strong>
              </button>
              <button
                type="button"
                className={`role-filter ${deviceRoleFilter === 'server' ? 'active' : ''}`}
                onClick={() => setDeviceRoleFilter(deviceRoleFilter === 'server' ? 'all' : 'server')}
              >
                <RoleIcon role="server" size={14} />
                <span>服务器</span>
                <strong>{serverCount}</strong>
              </button>
              <button
                type="button"
                className={`role-filter ${deviceRoleFilter === 'custom' ? 'active' : ''}`}
                onClick={() => setDeviceRoleFilter(deviceRoleFilter === 'custom' ? 'all' : 'custom')}
              >
                <RoleIcon role="custom" size={14} />
                <span>其他</span>
                <strong>{customCount}</strong>
              </button>
            </div>
            <div className="rail-list">
              {filteredTopologyDevices.map((device) => (
                <button
                  className={`rail-device clickable ${highlightedDeviceId === device.id ? 'is-active' : ''}`}
                  type="button"
                  key={device.id}
                  onClick={() => focusTopologyDevice(device.id)}
                >
                  <RoleIcon role={device.role} />
                  <span>
                    <strong>{device.displayName}</strong>
                    <small>{device.mgmtIp || device.model || device.role}</small>
                  </span>
                  <StatusPill value={device.health} />
                </button>
              ))}
              {!topologyDevices.length ? <div className="muted-note">当前拓扑暂无设备。</div> : null}
              {topologyDevices.length > 0 && !filteredTopologyDevices.length ? <div className="muted-note">当前筛选没有匹配设备。</div> : null}
            </div>
          </RailSection>

          <section className="rail-workspace panel">
            <div className="rail-workspace-head">
              <div>
                <h2>编辑工作区</h2>
                <p>在这里加入设备、处理发现结果和确认线缆。</p>
              </div>
              <span className="rail-workspace-badge">{workspaceBadge}</span>
            </div>
            <div className="rail-tab-strip" role="tablist" aria-label="右侧工作区">
              <button
                type="button"
                role="tab"
                aria-selected={activeRailTool === 'members'}
                className={`rail-tab ${activeRailTool === 'members' ? 'active' : ''}`}
                onClick={() => setActiveRailTool('members')}
              >
                <Plus size={14} />
                <span>设备加入</span>
                <strong>{selectedTopologyDevices.length}</strong>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeRailTool === 'discovery'}
                className={`rail-tab ${activeRailTool === 'discovery' ? 'active' : ''}`}
                onClick={() => setActiveRailTool('discovery')}
              >
                <Activity size={14} />
                <span>发现导入</span>
                <strong>{discoverySummaryText}</strong>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeRailTool === 'inspector'}
                className={`rail-tab ${activeRailTool === 'inspector' ? 'active' : ''}`}
                onClick={() => setActiveRailTool('inspector')}
              >
                <Cable size={14} />
                <span>端口线缆</span>
                <strong>{selectedPort ? deviceById.get(selectedPort.deviceId)?.displayName || '已选' : '未选择'}</strong>
              </button>
            </div>

            <div className="rail-workspace-body">
              {activeRailTool === 'members' ? (
                availableDevices.length === 0 ? (
                  <div className="muted-note">当前拓扑已包含全部设备。</div>
                ) : (
                  <div className="device-picker">
                    <div className="rail-workspace-actions">
                      <button
                        className="text-button"
                        type="button"
                        onClick={addSelectedTopologyDevices}
                        disabled={!canAddTopologyDevices || attachDevices.isPending}
                      >
                        加入 ({selectedTopologyDevices.length})
                      </button>
                    </div>
                    <input
                      className="rail-search"
                      value={deviceSearch}
                      onChange={(event) => setDeviceSearch(event.target.value)}
                      placeholder="搜索设备、IP、型号"
                    />
                    <select
                      className="rail-select"
                      value=""
                      onChange={(event) => addTopologyDeviceToSelection(event.target.value)}
                      disabled={!selectableAvailableDevices.length}
                      aria-label="选择可加入设备"
                    >
                      <option value="">{selectableAvailableDevices.length ? '从下拉栏选择设备' : '没有匹配设备'}</option>
                      {selectableAvailableDevices.slice(0, 80).map((device: Device) => (
                        <option key={device.id} value={device.id}>
                          {deviceOptionLabel(device)}
                        </option>
                      ))}
                    </select>
                    <div className="rail-meta compact">
                      <span>匹配 <strong>{filteredAvailableDevices.length}</strong></span>
                      <span>无网口 <strong>{noPortAvailableCount}</strong></span>
                    </div>
                    {selectedAvailableDevices.length ? (
                      <div className="selected-device-list">
                        {selectedAvailableDevices.map((device) => (
                          <button
                            type="button"
                            className="selected-device-chip"
                            key={device.id}
                            onClick={() => removeTopologyDeviceSelection(device.id)}
                            title="点击移除"
                          >
                            <RoleIcon role={device.role} size={14} />
                            <span>
                              <strong>{device.displayName}</strong>
                              <small>{device.mgmtIp || device.model || device.source}</small>
                            </span>
                            <em>{device.stale ? '无网口' : '待加入'}</em>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <div className="muted-note tight">先搜索并从下拉栏选择设备。</div>
                    )}
                  </div>
                )
              ) : activeRailTool === 'discovery' ? (
                zabbixChecking ? (
                  <div className="muted-note">正在检查 Zabbix 配置...</div>
                ) : zabbixUnavailable ? (
                  <div className="muted-note">Zabbix 未配置，发现与同步已暂停。</div>
                ) : discoveryError ? (
                  <div className="muted-note error-text">
                    <strong>Zabbix 发现失败</strong>
                    <span>{discoveryError}</span>
                  </div>
                ) : discovered.isLoading ? (
                  <div className="muted-note">正在加载发现设备...</div>
                ) : discoveredDevices.length === 0 ? (
                  <div className="muted-note">暂无可导入的 Zabbix 设备。</div>
                ) : (
                  <>
                    <div className="rail-meta">
                      <span>已同步 <strong>{syncedDiscovered.length}</strong></span>
                      <span>未同步 <strong>{unsyncedDiscovered.length}</strong></span>
                    </div>
                    <div className="rail-workspace-actions">
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => discovered.refetch()}
                        disabled={zabbixChecking || !zabbixConfigured || discovered.isFetching}
                      >
                        {discovered.isFetching ? '刷新中...' : '刷新'}
                      </button>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => importAll.mutate()}
                        disabled={zabbixChecking || !zabbixConfigured || discovered.isFetching || unsyncedDiscovered.length === 0 || importAll.isPending}
                      >
                        <Check size={16} />
                        全部导入
                      </button>
                      <button
                        type="button"
                        className="text-button"
                        onClick={applyHostSelection}
                        disabled={zabbixChecking || !zabbixConfigured || !discoveredSelection.size || importSelected.isPending}
                      >
                        导入选中
                      </button>
                    </div>
                    <div className="discovery-list">
                      {discoveredDevices.map((item: ZabbixDiscoveredDevice) => (
                        <label className="discovery-row" key={item.zabbixHostid}>
                          <input
                            type="checkbox"
                            checked={discoveredSelection.has(item.zabbixHostid)}
                            onChange={() => toggleDiscovery(item.zabbixHostid)}
                            disabled={item.synced}
                          />
                          <span className="discovery-main">
                            <strong>{item.displayName}</strong>
                            <small title={item.model || undefined}>{item.model || item.mgmtIp || '-'}</small>
                          </span>
                          <span className="discovery-meta">
                            <span>{item.role}</span>
                            <span>{item.portCount} 端口</span>
                            {item.synced ? <StatusPill value="ok" /> : <span>未导入</span>}
                          </span>
                        </label>
                      ))}
                    </div>
                  </>
                )
              ) : (
                <div className="inspector-stack">
                  <div className="inspector-hint">
                    {selectedPort
                      ? `${deviceById.get(selectedPort.deviceId)?.displayName || '-'} · ${selectedPort.name}`
                      : '选择一个端口开始打标'}
                  </div>
                  {pendingLink ? (
                    <form className="cable-form" onSubmit={submitCable}>
                      <strong>
                        {deviceById.get(pendingLink.a.deviceId)?.displayName || '-'} / {pendingLink.a.name}
                        <span> → </span>
                        {deviceById.get(pendingLink.b.deviceId)?.displayName || '-'} / {pendingLink.b.name}
                      </strong>
                      <input value={cableNo} onChange={(event) => setCableNo(event.target.value)} placeholder="线缆编号，例如 A-01" />
                      <input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="显示标签" />
                      <textarea value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="备注：机柜、配线架、确认人等" />
                      <div className="form-actions">
                        <button type="button" className="ghost-button" onClick={() => setPendingLink(null)}>
                          取消
                        </button>
                        <button type="submit" className="text-button" disabled={createCable.isPending}>
                          保存线缆
                        </button>
                      </div>
                    </form>
                  ) : (
                    <div className="muted-note tight">再次点击另一个端口即可创建人工确认线缆。</div>
                  )}
                </div>
              )}
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function RoleIcon({ role, size = 16 }: { role: string; size?: number }) {
  const Icon = role === 'switch' ? Network : role === 'server' ? Server : Box;
  return <Icon size={size} />;
}

function deviceOptionLabel(device: Device) {
  const detail = device.mgmtIp || device.model || device.source;
  const status = device.stale ? '无网口' : device.role === 'switch' ? '交换机' : device.role === 'server' ? '服务器' : '其他';
  return [device.displayName, detail, status].filter(Boolean).join(' · ');
}

function RailSection({
  title,
  panelKey,
  open,
  onToggle,
  badge,
  action,
  children,
}: {
  title: string;
  panelKey: string;
  open: boolean;
  onToggle: () => void;
  badge?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
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
