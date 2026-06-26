import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Save, Upload, X } from 'lucide-react';
import type { Device, Port, TopologySummary } from '../../types';
import type { SwitchPortLayoutTemplate } from '../../lib/switchPortLayouts';
import { deviceToYaml } from '../../lib/deviceConfigYaml';

interface Props {
  device: Device | null;
  ports: Port[];
  topologyId: number | null;
  topologies: TopologySummary[];
  layoutKey: string;
  layoutTemplates: SwitchPortLayoutTemplate[];
  savingConfig: boolean;
  importingData: boolean;
  onClose: () => void;
  onSetLayout: (deviceId: number, layoutKey: string) => void;
  onSaveConfig: (yamlText: string) => void;
  onImportIpAddr: (payload: { device: Device; output: string; mgmtIp?: string | null; topologyId?: number | null }) => void;
}

export function DeviceEditDialog({
  device,
  ports,
  topologyId,
  topologies,
  layoutKey,
  layoutTemplates,
  savingConfig,
  importingData,
  onClose,
  onSetLayout,
  onSaveConfig,
  onImportIpAddr,
}: Props) {
  const [yamlText, setYamlText] = useState('');
  const [ipAddrOutput, setIpAddrOutput] = useState('');
  const [mgmtIp, setMgmtIp] = useState('');
  const [targetTopologyId, setTargetTopologyId] = useState<number | ''>('');

  useEffect(() => {
    if (!device) return;
    setYamlText(deviceToYaml(device, ports));
    setMgmtIp(device.mgmtIp || '');
    setTargetTopologyId(topologyId || '');
    setIpAddrOutput('');
  }, [device, ports, topologyId]);

  if (!device || typeof document === 'undefined') return null;

  return createPortal(
    <div className="device-edit-overlay" role="presentation" onMouseDown={onClose}>
      <div
        className="device-edit-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={`编辑设备 ${device.displayName}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="device-edit-head">
          <div>
            <h2>{device.displayName}</h2>
            <p>{device.mgmtIp || device.model || device.role}</p>
          </div>
          <button className="icon-button" type="button" onClick={onClose} title="关闭" aria-label="关闭">
            <X size={16} />
          </button>
        </div>

        <section className="device-edit-section">
          <h3>样式修改</h3>
          <div className="layout-option-strip wide">
            {layoutTemplates.map((template) => (
              <button
                key={template.key}
                type="button"
                className={`layout-option ${layoutKey === template.key ? 'active' : ''}`}
                title={template.description}
                onClick={() => onSetLayout(device.id, template.key)}
              >
                {template.label}
              </button>
            ))}
          </div>
        </section>

        <section className="device-edit-section">
          <h3>数据导入</h3>
          <div className="port-form-grid compact-grid">
            <label>
              <span>管理 IP</span>
              <input value={mgmtIp} onChange={(event) => setMgmtIp(event.target.value)} placeholder="可选" />
            </label>
            <label>
              <span>目标拓扑</span>
              <select value={targetTopologyId} onChange={(event) => setTargetTopologyId(event.target.value ? Number(event.target.value) : '')}>
                <option value="">当前/默认拓扑</option>
                {topologies.map((topology) => (
                  <option key={topology.id} value={topology.id}>
                    {topology.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <textarea
            className="device-import-editor"
            value={ipAddrOutput}
            onChange={(event) => setIpAddrOutput(event.target.value)}
            placeholder="建议粘贴 ip -d addr 输出；普通 ip addr 也可用"
            spellCheck={false}
          />
          <div className="form-actions">
            <button
              className="text-button"
              type="button"
              disabled={!ipAddrOutput.trim() || importingData}
              onClick={() => onImportIpAddr({ device, output: ipAddrOutput, mgmtIp: mgmtIp.trim() || null, topologyId: targetTopologyId || topologyId })}
            >
              <Upload size={15} />
              {importingData ? '导入中...' : '导入'}
            </button>
          </div>
        </section>

        <section className="device-edit-section">
          <h3>配置修改</h3>
          <textarea
            className="device-yaml-editor"
            value={yamlText}
            onChange={(event) => setYamlText(event.target.value)}
            spellCheck={false}
          />
          <div className="form-actions">
            <button className="text-button" type="button" disabled={savingConfig} onClick={() => onSaveConfig(yamlText)}>
              <Save size={15} />
              {savingConfig ? '保存中...' : '保存配置'}
            </button>
          </div>
        </section>
      </div>
    </div>,
    document.body,
  );
}
