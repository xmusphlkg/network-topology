import { FormEvent, type MouseEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
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
import {
  Activity,
  Box,
  Cable,
  Network,
  PencilLine,
  Plus,
  RefreshCw,
  Search,
  Server,
  Trash2,
} from 'lucide-react';
import { api } from '../lib/api';
import { queryKeys } from '../lib/queryKeys';
import type { CableLink, Device, Port } from '../types';
import { SwitchNode, EndpointNode } from '../components/TopologyNodes';
import { useFeedback } from '../components/FeedbackCenter';
import { DeviceCompactCard } from '../components/DeviceCompactCard';
import { RailSection } from '../components/RailSection';
import { getSwitchPortLayout, switchPortLayoutTemplates } from '../lib/switchPortLayouts';
import {
  loadRailWorkspaceState,
  loadSwitchPortLayout,
  loadDevicePortLayouts,
  saveDevicePortLayouts,
  saveRailWorkspaceState,
  saveSwitchPortLayout,
  type RailToolKey,
  type RailWorkspaceState,
} from './topology/workspaceState';
import { TopologyToolbar } from './topology/TopologyToolbar';
import { CableInspector } from './topology/CableInspector';
import { TopologyMembersPanel } from './topology/TopologyMembersPanel';
import { TopologyDiscoveryPanel } from './topology/TopologyDiscoveryPanel';
import { DeviceEditDialog } from './topology/DeviceEditDialog';
import { parseDeviceYaml } from '../lib/deviceConfigYaml';

const nodeTypes = { switchNode: SwitchNode, endpointNode: EndpointNode };
type DeviceRoleFilter = 'all' | 'switch' | 'server' | 'custom';
type PendingLink = { a: Port; b?: Port };

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
  const [vlanId, setVlanId] = useState('');
  const [notes, setNotes] = useState('');
  const [highlightedCableId, setHighlightedCableId] = useState<number | null>(null);
  const [newTopologyName, setNewTopologyName] = useState('');
  const [newTopologyDefault, setNewTopologyDefault] = useState(false);
  const [movedNodes, setMovedNodes] = useState<Record<string, { x: number; y: number }>>({});
  const [hasLayoutDirty, setHasLayoutDirty] = useState(false);
  const [discoveredSelection, setDiscoveredSelection] = useState<Set<string>>(new Set());
  const [topologyDeviceSelection, setTopologyDeviceSelection] = useState<Set<number>>(new Set());
  const [deviceRoleFilter, setDeviceRoleFilter] = useState<DeviceRoleFilter>('all');
  const [highlightedDeviceId, setHighlightedDeviceId] = useState<number | null>(null);
  const [deviceSearch, setDeviceSearch] = useState('');
  const [deviceOverviewSearch, setDeviceOverviewSearch] = useState('');
  const [railWorkspace, setRailWorkspace] = useState<RailWorkspaceState>(() => loadRailWorkspaceState());
  const [layoutKey, setLayoutKey] = useState('default');
  const [hasRestoredViewport, setHasRestoredViewport] = useState(false);
  const [switchPortLayoutKey, setSwitchPortLayoutKey] = useState(() => loadSwitchPortLayout());
  const [devicePortLayouts, setDevicePortLayouts] = useState<Record<number, string>>({});
  const [editingDevice, setEditingDevice] = useState<Device | null>(null);
  const [savingDeviceConfig, setSavingDeviceConfig] = useState(false);
  const topologyIdParam = searchParams.get('topologyId') || '';
  const activeRailTool = railWorkspace.activeTool;
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null);

  useEffect(() => {
    saveRailWorkspaceState(railWorkspace);
  }, [railWorkspace]);

  useEffect(() => {
    saveSwitchPortLayout(switchPortLayoutKey);
  }, [switchPortLayoutKey]);

  useEffect(() => {
    setDevicePortLayouts(loadDevicePortLayouts(topologyId));
  }, [topologyId]);

  useEffect(() => {
    saveDevicePortLayouts(topologyId, devicePortLayouts);
  }, [devicePortLayouts, topologyId]);

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
    setHasLayoutDirty(false);
    setSelectedPort(null);
    setEditingCable(null);
    setPendingLink(null);
    setConnectMode(false);
    setHasRestoredViewport(false);
    setDiscoveredSelection(new Set());
    setTopologyDeviceSelection(new Set());
    setDeviceRoleFilter('all');
    setHighlightedDeviceId(null);
    setEditingDevice(null);
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
    onSuccess: (created) => {
      setPendingLink(null);
      setSelectedPort(null);
      setEditingCable(created);
      setCableNo(created.cableNo || '');
      setLabel(created.label || '');
      setVlanId(created.vlanId ? String(created.vlanId) : '');
      setNotes(created.notes || '');
      setHighlightedCableId(created.id);
      setConnectMode(false);
      setActiveRailTool('inspector');
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      feedback.pushToast('线缆已添加', 'success');
    },
    onError: (error: Error, variables) => {
      if (!variables.replaceExisting && error.message.includes('already connected')) {
        void feedback
          .confirm({
            title: '替换已有线缆',
            message: '所选端口已有线缆记录，是否替换旧连接？',
            confirmText: '确认替换',
            danger: true,
          })
          .then((confirmed) => {
            if (confirmed) {
              createCable.mutate({ ...variables, replaceExisting: true });
            }
          });
        return;
      }
      feedback.pushToast(error.message, 'error');
    },
  });

  const runSync = useMutation({
    mutationFn: () => api.runSync(),
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
      queryClient.invalidateQueries({ queryKey: queryKeys.devicesAll() });
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
      queryClient.invalidateQueries({ queryKey: queryKeys.devicesAll() });
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
      setHasLayoutDirty(false);
      feedback.pushToast('布局已保存', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const updateCable = useMutation({
    mutationFn: (payload: { id: number; cableNo?: string | null; label?: string | null; vlanId?: number | null; notes?: string | null }) =>
      api.updateCable(payload.id, {
        cableNo: payload.cableNo,
        label: payload.label,
        vlanId: payload.vlanId,
        notes: payload.notes,
      }),
    onSuccess: (updated) => {
      clearCableForm();
      setHighlightedCableId(updated.id);
      setConnectMode(false);
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      feedback.pushToast('线缆信息已保存', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const deleteCable = useMutation({
    mutationFn: (linkId: number) => api.deleteCable(linkId),
    onSuccess: () => {
      clearCableForm();
      setConnectMode(false);
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      feedback.pushToast('线缆已删除', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const removeDeviceFromTopology = useMutation({
    mutationFn: (deviceId: number) => {
      if (!topologyId) throw new Error('当前拓扑无效');
      return api.removeDeviceFromTopology(topologyId, deviceId);
    },
    onSuccess: () => {
      setHighlightedDeviceId(null);
      setSelectedPort(null);
      setPendingLink(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.devicesAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      feedback.pushToast('设备已移出当前拓扑', 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error');
    },
  });

  const importIpAddr = useMutation({
    mutationFn: (payload: { device: Device; output: string; mgmtIp?: string | null; topologyId?: number | null }) =>
      api.syncIpAddr({
        displayName: payload.device.displayName,
        mgmtIp: payload.mgmtIp ?? payload.device.mgmtIp ?? null,
        topologyId: payload.topologyId ?? topologyId,
        output: payload.output,
        source: 'command',
        strictPhysicalPorts: true,
        physicalPortNamePatterns: ['eth', 'eno', 'ens', 'enp', 'enx', 'em', 'ib', 'bond', 'wan', 'lan', 'idrac', 'ipmi', 'bmc', 'ilo'],
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.devicesAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      feedback.pushToast(`已导入 ${result.ports} 个端口`, 'success');
    },
    onError: (error: Error) => {
      feedback.pushToast(error.message, 'error', 5000);
    },
  });

  const linkedPortIds = useMemo(() => {
    const ids = new Set<number>();
    for (const cable of topologyQuery.data?.cableLinks || []) {
      ids.add(cable.endpointAPortId);
      ids.add(cable.endpointBPortId);
    }
    return [...ids].sort((left, right) => left - right);
  }, [topologyQuery.data?.cableLinks]);

  const candidatePortId = connectMode && pendingLink ? pendingLink.a.id : null;

  const derivedNodes = useMemo<Node[]>(() => {
    const serverNodes = topologyQuery.data?.nodes || [];
    return serverNodes.map((node) => ({
      ...node,
      data: (() => {
        const device = node.data.device as Device;
        const layoutKey = devicePortLayouts[device.id] || (device.role === 'server' ? 'single-row' : switchPortLayoutKey);
        const layoutTemplate = getSwitchPortLayout(layoutKey);
        return {
          ...node.data,
          highlighted: highlightedDeviceId === device.id,
          selectedPortId: selectedPort?.id,
          candidatePortId,
          portLayoutColumns: layoutTemplate.columns,
          portLayoutRows: layoutTemplate.rows,
          portLayoutArrangement: layoutTemplate.arrangement,
          hideVirtualPorts: layoutTemplate.hideVirtual,
          compact: layoutTemplate.compact,
          linkedPortIds,
          onPortClick: (port: Port, event?: MouseEvent<HTMLButtonElement>) => {
            const quickConnect = Boolean(event?.ctrlKey || event?.metaKey);
            if (!connectMode && !quickConnect) {
              setSelectedPort(port);
              setEditingCable(null);
              setPendingLink(null);
              return;
            }

            if (quickConnect && !connectMode) {
              setConnectMode(true);
            }

            if (!pendingLink) {
              setPendingLink({ a: port });
              setSelectedPort(port);
              setCableNo('');
              setLabel('');
              setVlanId('');
              setNotes('');
              return;
            }

            if (!pendingLink.b) {
              if (pendingLink.a.id === port.id) {
                clearCableForm();
                setConnectMode(false);
                return;
              }
              const inferredVlan = inferCableVlan(pendingLink.a, port);
              setPendingLink({ ...pendingLink, b: port });
              setEditingCable(null);
              setCableNo('');
              setLabel(`${pendingLink.a.name} - ${port.name}`);
              setVlanId(inferredVlan ? String(inferredVlan) : '');
              setNotes('');
              setSelectedPort(port);
              setActiveRailTool('inspector');
              setRailWorkspace((current) => (current.activeTool === 'inspector' ? current : { ...current, activeTool: 'inspector' }));
              return;
            }
            clearCableForm();
          },
        };
      })(),
    }));
  }, [candidatePortId, connectMode, devicePortLayouts, highlightedDeviceId, linkedPortIds, pendingLink, selectedPort?.id, switchPortLayoutKey, topologyQuery.data?.nodes]);

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

  const edges = useMemo<Edge[]>(
    () => {
      const nodeById = new Map(nodes.map((node) => [node.id, node]));
      return (topologyQuery.data?.edges || []).map((edge) => {
        const linkId = edgeLinkId(edge);
        const highlighted = highlightedCableId !== null && linkId === highlightedCableId;
        const edgeVlan = edgeVlanId(edge);
        const baseStrokeWidth = edgeStrokeWidth(edge.style?.strokeWidth);
        const anchor = verticalPortAnchor(edge, nodeById);
        return {
          ...edge,
          sourceHandle: portHandleWithSide(edge.sourceHandle, anchor.source),
          targetHandle: portHandleWithSide(edge.targetHandle, anchor.target),
          label: edge.label || (edgeVlan ? `VLAN ${edgeVlan}` : undefined),
          animated: highlighted,
          selected: highlighted,
          interactionWidth: 8,
          zIndex: highlighted ? 40 : 30,
          style: {
            ...(edge.style || {}),
            strokeWidth: highlighted ? 4 : baseStrokeWidth,
          },
        };
      });
    },
    [highlightedCableId, nodes, topologyQuery.data?.edges],
  );
  const deviceById = useMemo(() => new Map((topologyQuery.data?.devices || []).map((device) => [device.id, device])), [topologyQuery.data?.devices]);
  const portById = useMemo(() => new Map((topologyQuery.data?.ports || []).map((port) => [port.id, port])), [topologyQuery.data?.ports]);
  const inspectCablePorts = useMemo(() => {
    if (!editingCable) return null;
    return {
      endpointAPort: portById.get(editingCable.endpointAPortId) || null,
      endpointBPort: portById.get(editingCable.endpointBPortId) || null,
    };
  }, [editingCable, portById]);

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
          setHasLayoutDirty(true);
        }
        return nextNodes;
      });
    },
    [],
  );

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
    if (connectMode) {
      setConnectMode(false);
    }
    setEditingCable(targetCable);
    setHighlightedCableId(targetCable.id);
    setSelectedPort(null);
    setPendingLink(null);
    setCableNo(targetCable.cableNo || '');
    setLabel(targetCable.label || '');
    setVlanId(targetCable.vlanId ? String(targetCable.vlanId) : '');
    setNotes(targetCable.notes || '');
    setActiveRailTool('inspector');
    setRailWorkspace((current) => (current.activeTool === 'inspector' ? current : { ...current, activeTool: 'inspector' }));
  }

  function handleNodeClick(_: unknown, node: Node) {
    const device = (node.data as { device?: Device }).device;
    if (!device?.id) return;
    setHighlightedDeviceId(device.id);
    setSelectedPort(null);
  }

  function handleNodeDoubleClick(_: unknown, node: Node) {
    const device = (node.data as { device?: Device }).device;
    if (!device?.id) return;
    openDeviceEditor(device);
  }

  useEffect(() => {
    applyLayoutViewport(topologyId);
  }, [applyLayoutViewport, topologyId, topologyQuery.data?.layout?.viewport, topologyQuery.data?.nodes, flowInstance]);

  useEffect(() => {
    if (!connectMode) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setConnectMode(false);
        clearCableForm();
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
  const highlightedDevice = highlightedDeviceId ? topologyDevices.find((device) => device.id === highlightedDeviceId) || null : null;
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
  const editingDevicePorts = useMemo(
    () => (editingDevice ? topologyPorts.filter((port) => port.deviceId === editingDevice.id) : []),
    [editingDevice, topologyPorts],
  );
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
        : editingCable
          ? `编辑线缆 ${editingCable.id}`
          : selectedPort
            ? `${deviceById.get(selectedPort.deviceId)?.displayName || '-'} · ${selectedPort.name}`
            : pendingLink
              ? '已选线缆'
              : '未选择';

  function submitCable(event: FormEvent) {
    event.preventDefault();
    const parsedVlan = parseVlanInput(vlanId);
    if (!parsedVlan.ok) {
      feedback.pushToast(parsedVlan.message, 'error');
      return;
    }
    if (editingCable) {
      updateCable.mutate({
        id: editingCable.id,
        cableNo: cableNo.trim() || null,
        label: label.trim() || null,
        vlanId: parsedVlan.value,
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
      vlanId: parsedVlan.value ?? undefined,
      notes: notes.trim() || undefined,
      color: '#3274d9',
    });
    setConnectMode(false);
  }

  function clearCableForm() {
    setPendingLink(null);
    setSelectedPort(null);
    setEditingCable(null);
    setCableNo('');
    setLabel('');
    setVlanId('');
    setNotes('');
    setHighlightedCableId(null);
  }

  function submitTopology(event: FormEvent) {
    event.preventDefault();
    createTopology.mutate();
  }

  function confirmDeleteCable() {
    if (!editingCable) return;
    void feedback
      .confirm({
        title: '删除线缆',
        message: `确认删除该线缆 ${editingCable.label || editingCable.cableNo || '' ? `（${editingCable.label || editingCable.cableNo}）` : ''}？`,
        confirmText: '确认删除',
        danger: true,
      })
      .then((confirmed) => {
        if (confirmed) {
          deleteCable.mutate(editingCable.id);
        }
      });
  }

  function toggleConnectMode() {
    clearCableForm();
    setConnectMode((current) => {
      return !current;
    });
  }

  function clearConnectMode() {
    clearCableForm();
    setConnectMode(false);
  }

  useEffect(() => {
    if (selectedPort || pendingLink || editingCable) {
      setRailWorkspace((current) => (current.activeTool === 'inspector' ? current : { ...current, activeTool: 'inspector' }));
    }
  }, [editingCable, pendingLink, selectedPort]);

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

  function openDeviceEditor(device: Device) {
    setHighlightedDeviceId(device.id);
    setSelectedPort(null);
    setEditingDevice(device);
  }

  function setDeviceLayout(deviceId: number, layoutKey: string) {
    setDevicePortLayouts((current) => ({ ...current, [deviceId]: layoutKey }));
  }

  function confirmRemoveDeviceFromTopology(device: Device) {
    void feedback
      .confirm({
        title: '移出拓扑',
        message: `将设备「${device.displayName}」从当前拓扑移出？设备台账和端口不会被删除。`,
        confirmText: '确认移出',
        danger: true,
      })
      .then((confirmed) => {
        if (confirmed) {
          removeDeviceFromTopology.mutate(device.id);
        }
      });
  }

  async function saveDeviceYaml(yamlText: string) {
    if (!editingDevice) return;
    try {
      const document = parseDeviceYaml(yamlText);
      if (!document.device.displayName?.trim()) {
        feedback.pushToast('displayName 不能为空', 'error');
        return;
      }
      setSavingDeviceConfig(true);
      const updated = await api.updateDevice(editingDevice.id, document.device);
      for (const port of document.ports) {
        const name = String(port.name || '').trim();
        if (!name) continue;
        const payload = {
          name,
          alias: port.alias ?? null,
          operStatus: port.operStatus || 'unknown',
          adminStatus: port.adminStatus || 'unknown',
          speedMbps: port.speedMbps ?? null,
          media: port.media ?? null,
          macAddress: port.macAddress ?? null,
          portRole: port.portRole ?? null,
          vlanSummary: port.vlanSummary ?? null,
        };
        if (port.id) {
          await api.updatePort(port.id, payload);
        } else {
          await api.createPort(editingDevice.id, payload);
        }
      }
      setEditingDevice(updated);
      queryClient.invalidateQueries({ queryKey: queryKeys.devicesAll() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topology(topologyId) });
      queryClient.invalidateQueries({ queryKey: queryKeys.topologies() });
      queryClient.invalidateQueries({ queryKey: queryKeys.portsAll() });
      feedback.pushToast('设备和端口配置已保存', 'success');
    } catch (error) {
      feedback.pushToast(error instanceof Error ? error.message : 'YAML 无法解析', 'error', 5000);
    } finally {
      setSavingDeviceConfig(false);
    }
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

  function autoLayoutCurrentTopology() {
    const switchNodes: Node[] = [];
    const endpointNodes: Node[] = [];
    for (const node of nodes) {
      const device = (node.data as { device?: Device }).device;
      if (device?.role === 'switch') {
        switchNodes.push(node);
      } else {
        endpointNodes.push(node);
      }
    }
    const nextPositions: Record<string, { x: number; y: number }> = {};
    switchNodes.forEach((node, index) => {
      nextPositions[node.id] = { x: 80, y: 80 + index * 260 };
    });
    endpointNodes.forEach((node, index) => {
      nextPositions[node.id] = { x: 720 + (index % 3) * 300, y: 80 + Math.floor(index / 3) * 150 };
    });
    setNodes((current) => current.map((node) => ({ ...node, position: nextPositions[node.id] || node.position })));
    setMovedNodes((current) => ({ ...current, ...nextPositions }));
    setHasLayoutDirty(true);
    if (flowInstance) {
      window.setTimeout(() => flowInstance.fitView({ padding: 0.18, maxZoom: 1 }), 0);
    }
  }

  const hasUnsavedLayout = hasLayoutDirty;

  useEffect(() => {
    if (!topologyId || !hasLayoutDirty) return;
    const timer = window.setTimeout(() => {
      saveCurrentLayout();
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [hasLayoutDirty, nodes, topologyId]);

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
      const preview = await api.dryRunImportTopologyJson(topologyId, payload);
      const warningText = preview.warnings.length ? `\n\n警告：${preview.warnings.join('；')}` : '';
      const confirmed = await feedback.confirm({
        title: '导入拓扑 JSON',
        message: `将导入 ${preview.devices} 台设备、${preview.ports} 个端口、${preview.cableLinks} 条线缆、${preview.layouts} 个布局节点。预计新增 ${preview.newDevices} 台设备，更新/复用 ${preview.existingDevices} 台设备。${warningText}`,
        confirmText: '确认导入',
      });
      if (confirmed) {
        importTopologyJson.mutate(payload);
      }
    } catch (error) {
      feedback.pushToast(
        error instanceof Error ? error.message : 'JSON 文件无法解析',
        'error',
      );
    }
  }

  return (
    <div className="page topology-page">
      <TopologyToolbar
        topologyId={topologyId}
        topologies={topologies.data || []}
        topologyName={topologyQuery.data?.topologyName || '加载中'}
        onTopologyChange={handleTopologyChange}
        zabbixUnavailable={zabbixUnavailable}
        zabbixConfigured={zabbixConfigured}
        runSyncPending={runSync.isPending}
        onRunSync={() => runSync.mutate()}
        connectMode={connectMode}
        onToggleConnectMode={toggleConnectMode}
        switchPortLayoutKey={switchPortLayoutKey}
        onSwitchPortLayoutChange={setSwitchPortLayoutKey}
        connectModeText={connectMode ? connectModeStatusText(pendingLink) : null}
        hasUnsavedLayout={hasUnsavedLayout}
        onSaveLayout={saveCurrentLayout}
        onAutoLayout={autoLayoutCurrentTopology}
        saveLayoutPending={saveLayout.isPending}
        canSaveLayout={nodes.length > 0}
        onExportJson={exportJson}
        importTopologyPending={importTopologyJson.isPending}
        jsonImportRef={jsonImportRef}
        onImportJsonFile={importJsonFile}
        newTopologyName={newTopologyName}
        onNewTopologyNameChange={setNewTopologyName}
        newTopologyDefault={newTopologyDefault}
        onNewTopologyDefaultChange={setNewTopologyDefault}
        onSubmitTopology={submitTopology}
        createTopologyPending={createTopology.isPending}
        stats={{
          deviceCount: topologyDevices.length,
          switchCount,
          upPortCount,
          portCount: topologyPorts.length,
          cableCount: cableLinks.length,
          availableDeviceCount: availableDevices.length,
          discoverySummaryText,
          syncStatusText,
          syncStatusValue,
        }}
      />

      <div className="topology-content">
        <div className="topology-primary">
          <section className="topology-canvas">
            {nodes.length ? (
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={nodeTypes}
                onInit={handleFlowInit}
                fitView
                fitViewOptions={{ padding: 0.18, maxZoom: 1 }}
                onNodesChange={handleNodesChange}
                onNodeClick={handleNodeClick}
                onNodeDoubleClick={handleNodeDoubleClick}
                onEdgeClick={handleEdgeClick}
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
            {pendingLink?.b ? (
              <form className="canvas-tag-panel" onSubmit={submitCable}>
                <strong>
                  {deviceById.get(pendingLink.a.deviceId)?.displayName || '-'} / {pendingLink.a.name}
                  <span> → </span>
                  {deviceById.get(pendingLink.b.deviceId)?.displayName || '-'} / {pendingLink.b.name}
                </strong>
                <input value={cableNo} onChange={(event) => setCableNo(event.target.value)} placeholder="线缆编号" />
                <input value={label} onChange={(event) => setLabel(event.target.value)} placeholder="显示标签" />
                <input
                  value={vlanId}
                  onChange={(event) => setVlanId(event.target.value)}
                  inputMode="numeric"
                  placeholder="VLAN"
                />
                <div className="form-actions">
                  <button type="button" className="ghost-button" onClick={clearConnectMode}>
                    取消
                  </button>
                  <button type="submit" className="text-button" disabled={createCable.isPending}>
                    {createCable.isPending ? '保存中...' : '保存线缆'}
                  </button>
                </div>
              </form>
            ) : null}
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
                title="交换机"
              >
                <RoleIcon role="switch" size={14} />
                <span className="sr-only">交换机</span>
                <strong>{switchCount}</strong>
              </button>
              <button
                type="button"
                className={`role-filter ${deviceRoleFilter === 'server' ? 'active' : ''}`}
                onClick={() => setDeviceRoleFilter(deviceRoleFilter === 'server' ? 'all' : 'server')}
                title="服务器"
              >
                <RoleIcon role="server" size={14} />
                <span className="sr-only">服务器</span>
                <strong>{serverCount}</strong>
              </button>
              <button
                type="button"
                className={`role-filter ${deviceRoleFilter === 'custom' ? 'active' : ''}`}
                onClick={() => setDeviceRoleFilter(deviceRoleFilter === 'custom' ? 'all' : 'custom')}
                title="其他设备"
              >
                <RoleIcon role="custom" size={14} />
                <span className="sr-only">其他</span>
                <strong>{customCount}</strong>
              </button>
            </div>
            {highlightedDevice ? (
              <div className="device-layout-editor">
                <div className="rail-meta compact">
                  <span>布局 <strong>{highlightedDevice.displayName}</strong></span>
                </div>
                <div className="layout-option-strip">
                  {switchPortLayoutTemplates.map((template) => (
                    <button
                      key={template.key}
                      type="button"
                      className={`layout-option ${getDeviceLayoutKey(highlightedDevice, devicePortLayouts, switchPortLayoutKey) === template.key ? 'active' : ''}`}
                      onClick={() => setDeviceLayout(highlightedDevice.id, template.key)}
                      title={template.description}
                    >
                      {template.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            <div className="rail-list">
              {filteredTopologyDevices.map((device) => (
                <div className="rail-device-action-row" key={device.id}>
                  <DeviceCompactCard
                    device={device}
                    active={highlightedDeviceId === device.id}
                    asButton
                    onClick={() => focusTopologyDevice(device.id)}
                  />
                  <button
                    type="button"
                    className="icon-button"
                    title="编辑设备"
                    aria-label={`编辑设备 ${device.displayName}`}
                    onClick={() => openDeviceEditor(device)}
                  >
                    <PencilLine size={14} />
                  </button>
                  <button
                    type="button"
                    className="danger-icon"
                    title="移出当前拓扑"
                    aria-label={`移出当前拓扑 ${device.displayName}`}
                    onClick={() => confirmRemoveDeviceFromTopology(device)}
                    disabled={removeDeviceFromTopology.isPending}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
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
                title="设备加入"
              >
                <Plus size={14} />
                <span className="sr-only">设备加入</span>
                <strong>{selectedTopologyDevices.length}</strong>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeRailTool === 'discovery'}
                className={`rail-tab ${activeRailTool === 'discovery' ? 'active' : ''}`}
                onClick={() => setActiveRailTool('discovery')}
                title="发现导入"
              >
                <Activity size={14} />
                <span className="sr-only">发现导入</span>
                <strong>{discoverySummaryText}</strong>
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={activeRailTool === 'inspector'}
                className={`rail-tab ${activeRailTool === 'inspector' ? 'active' : ''}`}
                onClick={() => setActiveRailTool('inspector')}
                title="端口线缆"
              >
                <Cable size={14} />
                <span className="sr-only">端口线缆</span>
                <strong>{selectedPort ? deviceById.get(selectedPort.deviceId)?.displayName || '已选' : '未选择'}</strong>
              </button>
            </div>

            <div className="rail-workspace-body">
              {activeRailTool === 'members' ? (
                <TopologyMembersPanel
                  availableDevices={availableDevices}
                  selectedTopologyDevices={selectedTopologyDevices}
                  selectedAvailableDevices={selectedAvailableDevices}
                  filteredAvailableDevicesCount={filteredAvailableDevices.length}
                  selectableAvailableDevices={selectableAvailableDevices}
                  noPortAvailableCount={noPortAvailableCount}
                  canAddTopologyDevices={canAddTopologyDevices}
                  attachDevicesPending={attachDevices.isPending}
                  deviceSearch={deviceSearch}
                  onDeviceSearchChange={setDeviceSearch}
                  onAddTopologyDeviceToSelection={addTopologyDeviceToSelection}
                  onRemoveTopologyDeviceSelection={removeTopologyDeviceSelection}
                  onAddSelectedTopologyDevices={addSelectedTopologyDevices}
                />
              ) : activeRailTool === 'discovery' ? (
                <TopologyDiscoveryPanel
                  zabbixChecking={zabbixChecking}
                  zabbixUnavailable={zabbixUnavailable}
                  zabbixConfigured={zabbixConfigured}
                  discoveryError={discoveryError}
                  discoveredLoading={discovered.isLoading}
                  discoveredFetching={discovered.isFetching}
                  discoveredDevices={discoveredDevices}
                  syncedCount={syncedDiscovered.length}
                  unsyncedCount={unsyncedDiscovered.length}
                  discoveredSelection={discoveredSelection}
                  importAllPending={importAll.isPending}
                  importSelectedPending={importSelected.isPending}
                  onRefresh={() => discovered.refetch()}
                  onImportAll={() => importAll.mutate()}
                  onImportSelected={applyHostSelection}
                  onToggleDiscovery={toggleDiscovery}
                />
              ) : (
                <CableInspector
                  editingCable={editingCable}
                  selectedPort={selectedPort}
                  pendingLink={pendingLink}
                  deviceById={deviceById}
                  inspectCablePorts={inspectCablePorts}
                  cableNo={cableNo}
                  label={label}
                  vlanId={vlanId}
                  notes={notes}
                  onCableNoChange={setCableNo}
                  onLabelChange={setLabel}
                  onVlanIdChange={setVlanId}
                  onNotesChange={setNotes}
                  onSubmitCable={submitCable}
                  onClearCableForm={clearCableForm}
                  onClearConnectMode={clearConnectMode}
                  onConfirmDeleteCable={confirmDeleteCable}
                  createCablePending={createCable.isPending}
                  updateCablePending={updateCable.isPending}
                  deleteCablePending={deleteCable.isPending}
                />
              )}
            </div>
          </section>
        </aside>
      </div>
      <DeviceEditDialog
        device={editingDevice}
        ports={editingDevicePorts}
        topologyId={topologyId}
        topologies={topologies.data || []}
        layoutKey={editingDevice ? getDeviceLayoutKey(editingDevice, devicePortLayouts, switchPortLayoutKey) : switchPortLayoutKey}
        layoutTemplates={switchPortLayoutTemplates}
        savingConfig={savingDeviceConfig}
        importingData={importIpAddr.isPending}
        onClose={() => setEditingDevice(null)}
        onSetLayout={setDeviceLayout}
        onSaveConfig={saveDeviceYaml}
        onImportIpAddr={(payload) => importIpAddr.mutate(payload)}
      />
    </div>
  );
}

function RoleIcon({ role, size = 16 }: { role: string; size?: number }) {
  const Icon = role === 'switch' ? Network : role === 'server' ? Server : Box;
  return <Icon size={size} />;
}

function getDeviceLayoutKey(device: Device, layouts: Record<number, string>, fallback: string) {
  return layouts[device.id] || (device.role === 'server' ? 'single-row' : fallback);
}

function connectModeStatusText(pendingLink: PendingLink | null) {
  if (!pendingLink) return '连线模式：点击起点端口';
  if (!pendingLink.b) return '已选起点，点击目标端口';
  return '已选两端，填写标签保存';
}

function edgeLinkId(edge: Edge) {
  const value = edge.data?.linkId;
  if (typeof value === 'number') return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function edgeVlanId(edge: Edge) {
  const value = edge.data?.vlan;
  if (typeof value === 'number') return value;
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value);
    return Number.isInteger(parsed) ? parsed : null;
  }
  return null;
}

function edgeStrokeWidth(value: unknown): number | string {
  if (typeof value === 'number' || typeof value === 'string') return value;
  return 3;
}

type VerticalPortSide = 'top' | 'bottom';

function verticalPortAnchor(edge: Edge, nodeById: Map<string, Node>): { source: VerticalPortSide; target: VerticalPortSide } {
  const source = nodeById.get(edge.source);
  const target = nodeById.get(edge.target);
  if (!source || !target) return fallbackAnchor(edge.id);

  const deltaY = nodeCenterY(target) - nodeCenterY(source);
  if (deltaY > 24) return { source: 'bottom', target: 'top' };
  if (deltaY < -24) return { source: 'top', target: 'bottom' };
  return fallbackAnchor(edge.id);
}

function nodeCenterY(node: Node) {
  const measuredHeight = typeof node.measured?.height === 'number' ? node.measured.height : null;
  const height = measuredHeight ?? (typeof node.height === 'number' ? node.height : 0);
  return node.position.y + height / 2;
}

function fallbackAnchor(edgeId: string): { source: VerticalPortSide; target: VerticalPortSide } {
  const source: VerticalPortSide = stableHash(edgeId) % 2 === 0 ? 'top' : 'bottom';
  return { source, target: source === 'top' ? 'bottom' : 'top' };
}

function stableHash(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function portHandleWithSide(handle: string | null | undefined, side: VerticalPortSide) {
  if (!handle) return handle;
  return `${handle.replace(/-(top|bottom)$/, '')}-${side}`;
}

function parseVlanInput(value: string): { ok: true; value: number | null } | { ok: false; message: string } {
  const trimmed = value.trim();
  if (!trimmed) return { ok: true, value: null };
  const parsed = Number(trimmed);
  if (!Number.isInteger(parsed) || parsed < 1 || parsed > 4094) {
    return { ok: false, message: 'VLAN 必须是 1-4094 之间的整数' };
  }
  return { ok: true, value: parsed };
}

function inferCableVlan(a: Port, b: Port) {
  const vlanA = vlanNumbers(a.vlanSummary);
  const vlanB = vlanNumbers(b.vlanSummary);
  const common = [...vlanA].filter((vlan) => vlanB.has(vlan)).sort((left, right) => left - right);
  if (common.length) return common[0];
  const fallback = [...vlanA, ...vlanB].sort((left, right) => left - right);
  return fallback[0] || null;
}

function vlanNumbers(value?: string | null) {
  if (!value) return new Set<number>();
  const numbers = new Set<number>();
  for (const rawToken of value.replace(/[,/;]/g, ' ').split(/\s+/)) {
    const token = rawToken.trim().toLowerCase().replace(/^vlan/, '').replace(/^pvid/, '');
    if (!token) continue;
    if (token.includes('-')) {
      const [firstText, lastText] = token.split('-', 2);
      const first = Number(firstText);
      const last = Number(lastText);
      if (Number.isInteger(first) && Number.isInteger(last) && first > 0 && first <= last && last <= 4094 && last - first <= 64) {
        for (let vlan = first; vlan <= last; vlan += 1) {
          numbers.add(vlan);
        }
      }
      continue;
    }
    const parsed = Number(token);
    if (Number.isInteger(parsed) && parsed > 0 && parsed <= 4094) {
      numbers.add(parsed);
    }
  }
  return numbers;
}
