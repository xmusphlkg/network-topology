import type { FormEvent } from 'react';
import { Trash2 } from 'lucide-react';
import type { CableLink, Device, Port } from '../../types';

type PendingLink = { a: Port; b?: Port };

interface Props {
  editingCable: CableLink | null;
  selectedPort: Port | null;
  pendingLink: PendingLink | null;
  deviceById: Map<number, Device>;
  inspectCablePorts: { endpointAPort: Port | null; endpointBPort: Port | null } | null;
  cableNo: string;
  label: string;
  vlanId: string;
  notes: string;
  onCableNoChange: (value: string) => void;
  onLabelChange: (value: string) => void;
  onVlanIdChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onSubmitCable: (event: FormEvent) => void;
  onClearCableForm: () => void;
  onClearConnectMode: () => void;
  onConfirmDeleteCable: () => void;
  createCablePending: boolean;
  updateCablePending: boolean;
  deleteCablePending: boolean;
}

export function CableInspector({
  editingCable,
  selectedPort,
  pendingLink,
  deviceById,
  inspectCablePorts,
  cableNo,
  label,
  vlanId,
  notes,
  onCableNoChange,
  onLabelChange,
  onVlanIdChange,
  onNotesChange,
  onSubmitCable,
  onClearCableForm,
  onClearConnectMode,
  onConfirmDeleteCable,
  createCablePending,
  updateCablePending,
  deleteCablePending,
}: Props) {
  return (
    <div className="inspector-stack">
      <div className="inspector-hint">
        {editingCable
          ? `编辑线缆 #${editingCable.id}`
          : selectedPort
            ? `${deviceById.get(selectedPort.deviceId)?.displayName || '-'} · ${selectedPort.name}`
            : pendingLink
              ? '请选择目标端口以完成连线'
              : '选择一个端口开始打标'}
      </div>
      {editingCable ? (
        <form className="cable-form" onSubmit={onSubmitCable}>
          <strong>
            {inspectCablePorts?.endpointAPort ? `${deviceById.get(inspectCablePorts.endpointAPort.deviceId)?.displayName || '-'} / ${inspectCablePorts.endpointAPort.name}` : '线缆端点A'}
            <span> ↔ </span>
            {inspectCablePorts?.endpointBPort ? `${deviceById.get(inspectCablePorts.endpointBPort.deviceId)?.displayName || '-'} / ${inspectCablePorts.endpointBPort.name}` : '线缆端点B'}
          </strong>
          <input value={cableNo} onChange={(event) => onCableNoChange(event.target.value)} placeholder="线缆编号，例如 A-01" />
          <input value={label} onChange={(event) => onLabelChange(event.target.value)} placeholder="显示标签" />
          <input value={vlanId} onChange={(event) => onVlanIdChange(event.target.value)} inputMode="numeric" placeholder="VLAN，例如 10" />
          <textarea value={notes} onChange={(event) => onNotesChange(event.target.value)} placeholder="备注：机柜、配线架、确认人等" />
          <div className="form-actions">
            <button type="button" className="ghost-button" onClick={onClearCableForm}>
              取消
            </button>
            <button type="button" className="danger-button" onClick={onConfirmDeleteCable} disabled={deleteCablePending}>
              <Trash2 size={15} />
              删除
            </button>
            <button type="submit" className="text-button" disabled={updateCablePending}>
              {updateCablePending ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      ) : pendingLink?.b ? (
        <form className="cable-form" onSubmit={onSubmitCable}>
          <strong>
            {deviceById.get(pendingLink.a.deviceId)?.displayName || '-'} / {pendingLink.a.name}
            <span> → </span>
            {deviceById.get(pendingLink.b.deviceId)?.displayName || '-'} / {pendingLink.b.name}
          </strong>
          <input value={cableNo} onChange={(event) => onCableNoChange(event.target.value)} placeholder="线缆编号，例如 A-01" />
          <input value={label} onChange={(event) => onLabelChange(event.target.value)} placeholder="显示标签" />
          <input value={vlanId} onChange={(event) => onVlanIdChange(event.target.value)} inputMode="numeric" placeholder="VLAN，例如 10" />
          <textarea value={notes} onChange={(event) => onNotesChange(event.target.value)} placeholder="备注：机柜、配线架、确认人等" />
          <div className="form-actions">
            <button type="button" className="ghost-button" onClick={onClearConnectMode}>
              取消
            </button>
            <button type="submit" className="text-button" disabled={createCablePending}>
              {createCablePending ? '保存中...' : '保存线缆'}
            </button>
          </div>
        </form>
      ) : (
        <div className="muted-note tight">再次点击另一个端口即可创建人工确认线缆。</div>
      )}
    </div>
  );
}
