import { useEffect, useState } from 'react';
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { GitBranch, Search } from 'lucide-react';
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

export function App() {
  const navigate = useNavigate();
  const location = useLocation();
  const [commandOpen, setCommandOpen] = useState(false);
  const topologies = useQuery({
    queryKey: queryKeys.topologies(),
    queryFn: api.topologies,
    staleTime: 60000,
    enabled: commandOpen,
  });
  const commandDevices = useQuery({
    queryKey: queryKeys.devices({ includeDisabled: true }),
    queryFn: () => api.devices({ includeDisabled: true }),
    staleTime: 60000,
    enabled: commandOpen,
  });
  const commandPorts = useQuery({
    queryKey: queryKeys.ports({ includeStale: true }),
    queryFn: () => api.ports({ includeStale: true }),
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
              <strong>Switch Topology</strong>
            </div>
          </div>
          <nav className="top-nav-links" aria-label="主导航">
            <NavLink to="/topology">拓扑(T)</NavLink>
            <NavLink to="/ports">端口(P)</NavLink>
            <NavLink to="/devices">设备(D)</NavLink>
            <NavLink to="/sync">同步(S)</NavLink>
          </nav>
          <button className="icon-button command-trigger" type="button" title="快速命令" onClick={() => setCommandOpen(true)} aria-label="快速命令">
            <Search size={16} />
          </button>
          <div className="top-nav-foot">
            <span>SNMP 只读</span>
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
          onClose={() => setCommandOpen(false)}
          onNavigate={(to) => navigate(to)}
        />
      </div>
    </FeedbackProvider>
  );
}
