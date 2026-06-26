import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

export type Locale = 'zh' | 'en';

type MessageMap = Record<string, string>;

const messages: Record<Locale, MessageMap> = {
  zh: {
    appName: 'Switch Topology',
    appNameShort: '拓扑',
    homePage: '首页',
    topology: '拓扑',
    ports: '端口',
    devices: '设备',
    sync: '同步',
    searchHint: '搜索页面、拓扑、设备、端口',
    quickCommand: '快速命令',
    save: '保存',
    close: '关闭',
    cancel: '取消',
    delete: '删除',
    clear: '清空',
    add: '新增',
    createEntity: '创建',
    create: '创建',
    importLabel: '导入',
    exportLabel: '导出',
    apply: '应用',
    refresh: '刷新',
    ok: '确认',
    switchType: '交换机',
    serverType: '服务器',
    otherType: '其他',
    topologyManagement: '拓扑管理',
    deviceManagement: '设备管理',
    deviceList: '设备列表',
    portList: '端口列表',
    deviceDetail: '设备详情',
    syncPage: '同步诊断',
    refreshTopology: '刷新拓扑',
    saveLayout: '保存布局',
    connectMode: '连线模式',
    removeFromTopology: '移除并加入',
    importFromZabbix: '从Zabbix导入',
    deviceProfiles: '端口模板',
    applyTemplate: '应用模板',
    replaceTemplatePorts: '替换原模板端口',
    editDisplayName: '编辑显示名',
    rename: '改名',
    displayName: '显示名',
    layoutHint: '支持物理口和逻辑口展示。',
    pushSync: '推送更新',
    push: '提交推送',
    commandPush: '命令推送',
    syncPushSuccess: '推送更新成功',
    commandPushSuccess: '命令推送成功',
    syncSource: '来源',
    dataSource: '数据源',
    pushPayloadHint: '支持 JSON 中提交端口与设备属性，用于从运维脚本推送。',
    strictPhysical: '严格物理口模式',
    copy: '复制',
    copyLink: '复制链接',
    copyLinkSuccess: '链接已复制',
    copyLinkFailed: '复制链接失败',
    saveSuccess: '保存成功',
    savePending: '保存中',
    deleteSuccess: '删除成功',
    renamed: '已改名',
    unknown: '未知',
    includeVirtualPorts: '包含虚拟口',
    includeStalePorts: '包含 stale',
    stale: 'stale',
    all: '全部',
    noData: '无数据',
    noMatch: '无匹配',
    scopeAllTopology: '全部拓扑',
    edit: '编辑',
    remove: '移除',
    switch: '交换机',
    server: '服务器',
    other: '其他',
    status: '状态',
    up: 'up',
    down: 'down',
    select: '选择',
    imported: '已导入',
    allDevices: '全部设备',
    saving: '保存中',
    savingDot: '保存中...',
    deleted: '已删除',
  },
  en: {
    appName: 'Switch Topology',
    appNameShort: 'Topology',
    homePage: 'Home',
    topology: 'Topology',
    ports: 'Ports',
    devices: 'Devices',
    sync: 'Sync',
    searchHint: 'Search page, topology, device, port',
    quickCommand: 'Quick command',
    save: 'Save',
    close: 'Close',
    cancel: 'Cancel',
    delete: 'Delete',
    clear: 'Clear',
    add: 'Add',
    createEntity: 'Create',
    create: 'Create',
    importLabel: 'Import',
    exportLabel: 'Export',
    apply: 'Apply',
    refresh: 'Refresh',
    ok: 'OK',
    switchType: 'Switch',
    serverType: 'Server',
    otherType: 'Other',
    topologyManagement: 'Topology',
    deviceManagement: 'Devices',
    deviceList: 'Devices',
    portList: 'Ports',
    deviceDetail: 'Device detail',
    syncPage: 'Sync',
    refreshTopology: 'Refresh topology',
    saveLayout: 'Save layout',
    connectMode: 'Connect mode',
    removeFromTopology: 'Manage topology',
    importFromZabbix: 'Import from Zabbix',
    deviceProfiles: 'Port templates',
    applyTemplate: 'Apply template',
    replaceTemplatePorts: 'Replace template ports',
    editDisplayName: 'Display name',
    rename: 'Rename',
    displayName: 'Display name',
    layoutHint: 'Physical and logical interfaces are shown.',
    pushSync: 'Push sync',
    push: 'Submit',
    commandPush: 'Command push',
    syncPushSuccess: 'Push succeeded',
    commandPushSuccess: 'Command push done',
    syncSource: 'Source',
    dataSource: 'Data source',
    pushPayloadHint: 'Submit device and port attributes in JSON from agent/command jobs.',
    strictPhysical: 'Strict physical ports',
    copy: 'Copy',
    copyLink: 'Copy link',
    copyLinkSuccess: 'Link copied',
    copyLinkFailed: 'Failed to copy link',
    saveSuccess: 'Saved',
    savePending: 'Saving',
    deleteSuccess: 'Deleted',
    renamed: 'Renamed',
    unknown: 'Unknown',
    includeVirtualPorts: 'Include virtual',
    includeStalePorts: 'Include stale',
    stale: 'stale',
    all: 'All',
    noData: 'No data',
    noMatch: 'No match',
    scopeAllTopology: 'All topologies',
    edit: 'Edit',
    remove: 'Remove',
    switch: 'Switch',
    server: 'Server',
    other: 'Other',
    status: 'Status',
    up: 'up',
    down: 'down',
    select: 'Select',
    imported: 'Imported',
    allDevices: 'All devices',
    saving: 'Saving',
    savingDot: 'Saving...',
    deleted: 'Deleted',
  },
};

const STORAGE_KEY = 'switch-topology:locale';

interface I18nContextValue {
  locale: Locale;
  t: (key: keyof MessageMap, vars?: Record<string, string | number>) => string;
  localeOptions: { value: Locale; label: string }[];
  setLocale: (locale: Locale) => void;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function formatMessage(message: string, vars?: Record<string, string | number>) {
  if (!vars) return message;
  return Object.entries(vars).reduce(
    (output, [key, value]) => output.replace(new RegExp(`{{${key}}}`, 'g'), String(value)),
    message,
  );
}

function resolveLocale(): Locale {
  if (typeof localStorage === 'undefined') return 'zh';
  const raw = localStorage.getItem(STORAGE_KEY);
  return raw === 'en' ? 'en' : 'zh';
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => resolveLocale());

  const setLocale = useCallback((nextLocale: Locale) => {
    setLocaleState(nextLocale);
    if (typeof localStorage !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, nextLocale);
    }
  }, []);

  const t = useCallback(
    (key: keyof MessageMap, vars?: Record<string, string | number>) => formatMessage(messages[locale][key] ?? messages.zh[key] ?? String(key), vars),
    [locale],
  );

  const value = useMemo(
    () => ({
      locale,
      t,
      setLocale,
      localeOptions: [
        { value: 'zh' as const, label: '中文' },
        { value: 'en' as const, label: 'English' },
      ],
    }),
    [locale, t, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within I18nProvider');
  }
  return context;
}
