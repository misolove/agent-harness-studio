import { create } from 'zustand';

const API_BASE = '';

async function apiFetch(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

const useHarnessStore = create((set, get) => ({
  summary: null,
  items: [],
  loading: false,
  error: null,
  selectedSection: null,
  workspaces: [],
  activeWorkspace: '',
  envInfo: null,

  fetchWorkspaces: async () => {
    try {
      const data = await apiFetch('/api/workspaces');
      set({ workspaces: data });
      if (data.length > 0 && !get().activeWorkspace) {
        const defaultWs = data[0].path;
        set({ activeWorkspace: defaultWs });
        get().fetchEnv(defaultWs);
        get().fetchHarness(defaultWs);
        get().fetchAgentRunners(defaultWs);
      }
    } catch (err) {
      console.error('Failed to load workspaces', err);
    }
  },

  setWorkspace: (ws) => {
    set({ activeWorkspace: ws, selectedSection: null });
    get().fetchEnv(ws);
    get().fetchHarness(ws);
    get().fetchAgentRunners(ws);
  },

  fetchHarness: async (ws) => {
    set({ loading: true, error: null });
    const wsPath = ws || get().activeWorkspace;
    try {
      const data = await apiFetch(`/api/scan${wsPath ? '?workspace=' + encodeURIComponent(wsPath) : ''}`);
      set({ summary: data.summary, items: data.items, loading: false });
    } catch (err) {
      set({ error: err.message, loading: false });
    }
  },

  fetchEnv: async (ws) => {
    const wsPath = ws || get().activeWorkspace;
    try {
      const data = await apiFetch(`/api/env${wsPath ? '?workspace=' + encodeURIComponent(wsPath) : ''}`);
      set({ envInfo: data });
    } catch (err) {
      console.error('Failed to fetch env info', err);
    }
  },

  setSelectedSection: (section) => set({ selectedSection: section }),

  getFilteredItems: () => {
    const { selectedSection, items } = get();
    if (!selectedSection) return [];
    const map = {
      skills: ['Skill'],
      bundles: ['Skill Bundle', 'Subagent'],
      memory: ['Memory Config', 'Memory Manifest', 'Memory Directory', 'Memory State'],
      mcp: ['MCP Server'],
      context: ['Root Context'],
      hooks: ['Hook'],
      cron: ['Cron Job'],
      plugins: ['Plugin', 'Command'],
      config: ['Config', 'Memory Config', 'Root Context', 'MCP Server'],
      logs: ['Log File'],
      sessions: ['Session Summary'],
      statedb: ['State DB'],
      checkpoints: ['Checkpoint'],
      'agent-runners': ['Agent Runner'],
    };
    const allowed = map[selectedSection] || [];
    return items.filter(i => allowed.includes(i.type));
  },

  refresh: () => {
    get().fetchHarness();
  },
}));

export default useHarnessStore;
export { API_BASE, apiFetch };
