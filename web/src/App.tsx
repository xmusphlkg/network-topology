import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Cable, GitBranch, Network, RefreshCw, Search, Server } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { api } from './lib/api';
import { queryKeys } from './lib/queryKeys';
import { TopologyPage } from './pages/TopologyPage';
import { DeviceDetailPage } from './pages/DeviceDetailPage';
import { PortsPage } from './pages/PortsPage';
import { DevicesPage } from './pages/DevicesPage';
import { SyncPage } from './pages/SyncPage';
import { CommandPalette } from './components/CommandPalette';
import { FeedbackProvider } from './components/FeedbackCenter';
import { I18nProvider, useI18n } from './i18n/I18nProvider';

function AppShell() {
  const { t, setLocale, locale, localeOptions } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const [commandOpen, setCommandOpen] = useState(false);
  const currentTopologyId = (() => {
    const topologyId = Number(new URLSearchParams(location.search).get('topologyId'));
    return Number.isFinite(topologyId) && topologyId > 0 ? topologyId : undefined;
  })();
  const topologies = useQuery({
    queryKey: queryKeys.topologies(),
    queryFn: api.topologies,
    staleTime: 60000,
    enabled: commandOpen,
  });
  const commandDevices = useQuery({
    queryKey: queryKeys.devices({
      includeDisabled: true,
      topologyId: currentTopologyId,
    }),
    queryFn: () => api.devices({ includeDisabled: true, topologyId: currentTopologyId }),
    staleTime: 60000,
    enabled: commandOpen,
  });
  const commandPorts = useQuery({
    queryKey: queryKeys.ports({
      includeStale: true,
      topologyId: currentTopologyId,
      includeVirtual: false,
    }),
    queryFn: () => api.ports({ includeStale: true, topologyId: currentTopologyId, includeVirtual: false }),
    staleTime: 60000,
    enabled: commandOpen,
  });

  useEffect(() => {
    setCommandOpen(false);
  }, [location.pathname, location.search]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setCommandOpen((current) => !current);
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <FeedbackProvider>
      <div className="switch-shell">
        <header className="top-nav">
          <div className="brand">
            <GitBranch size={18} />
            <div className="brand-text">
              <strong>{t('appName')}</strong>
            </div>
          </div>
          <nav className="top-nav-links" aria-label="主导航">
            <NavLink to="/topology" title={t('topologyManagement')}>
              <Network size={16} />
              <span className="sr-only">{t('topology')}</span>
            </NavLink>
            <NavLink to="/ports" title={t('portList')}>
              <Cable size={16} />
              <span className="sr-only">{t('ports')}</span>
            </NavLink>
            <NavLink to="/devices" title={t('deviceList')}>
              <Server size={16} />
              <span className="sr-only">{t('devices')}</span>
            </NavLink>
            <NavLink to="/sync" title={t('syncPage')}>
              <RefreshCw size={16} />
              <span className="sr-only">{t('sync')}</span>
            </NavLink>
          </nav>
          <button className="icon-button command-trigger" type="button" title={t('quickCommand')} onClick={() => setCommandOpen(true)} aria-label={t('quickCommand')}>
            <Search size={16} />
          </button>
          <div className="top-nav-foot">
            <span>SNMP 只读</span>
            <select
              value={locale}
              onChange={(event) => setLocale(event.target.value as 'zh' | 'en')}
              title="语言 / Language"
              aria-label="语言切换"
            >
              {localeOptions.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </div>
        </header>
        <main className="top-main">
          <Routes>
            <Route path="/" element={<Navigate to="/topology" replace />} />
            <Route path="/topology" element={<TopologyPage />} />
            <Route path="/devices/:id" element={<DeviceDetailPage />} />
            <Route path="/ports" element={<PortsPage />} />
            <Route path="/devices" element={<DevicesPage />} />
            <Route path="/sync" element={<SyncPage />} />
          </Routes>
        </main>
        <footer className="app-statusbar">
          <span>就绪</span>
          <span>手工拓扑 · Zabbix 同步 · JSON 导入导出</span>
        </footer>
        <CommandPalette
          open={commandOpen}
          topologies={topologies.data || []}
          devices={commandDevices.data || []}
          ports={commandPorts.data || []}
          currentTopologyId={currentTopologyId}
          onClose={() => setCommandOpen(false)}
          onNavigate={(to) => navigate(to)}
        />
      </div>
    </FeedbackProvider>
  );
}

export function App() {
  return (
    <I18nProvider>
      <AppShell />
    </I18nProvider>
  );
}
