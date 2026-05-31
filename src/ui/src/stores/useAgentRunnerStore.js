import { create } from 'zustand';
import { apiFetch } from './useHarnessStore';

const useAgentRunnerStore = create((set, get) => ({
  agentRunners: [],
  agentRunnersLoading: false,
  piPreview: null,
  piPreviewPrompt: 'Summarize this repository and list the safest verification commands.',
  piRunPrompt: 'List all Python files in src/ and summarize their purpose.',
  piRunId: null,
  piRunMeta: null,
  piRunLog: '',
  piRunPolling: false,

  setAgentRunners: (r) => set({ agentRunners: r }),
  setAgentRunnersLoading: (l) => set({ agentRunnersLoading: l }),
  setPiPreview: (p) => set({ piPreview: p }),
  setPiPreviewPrompt: (p) => set({ piPreviewPrompt: p }),
  setPiRunPrompt: (p) => set({ piRunPrompt: p }),
  setPiRunId: (id) => set({ piRunId: id }),
  setPiRunMeta: (m) => set({ piRunMeta: m }),
  setPiRunLog: (l) => set({ piRunLog: l }),
  setPiRunPolling: (p) => set({ piRunPolling: p }),

  fetchAgentRunners: async (ws) => {
    set({ agentRunnersLoading: true });
    try {
      const data = await apiFetch(`/api/agent-runners${ws ? '?workspace=' + encodeURIComponent(ws) : ''}`);
      set({ agentRunners: data.runners || [], agentRunnersLoading: false });
    } catch (err) {
      set({ agentRunners: [{ id: 'error', name: 'Agent Runner', state: 'ERROR', error: err.message }], agentRunnersLoading: false });
    }
  },

  previewPiRun: async (activeWorkspace) => {
    const { piPreviewPrompt } = get();
    try {
      const data = await apiFetch('/api/pi/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: piPreviewPrompt, workspace: activeWorkspace }),
      });
      set({ piPreview: data });
    } catch (err) {
      set({ piPreview: { error: err.message } });
    }
  },

  submitPiRun: async (activeWorkspace) => {
    const { piRunPrompt } = get();
    set({ piRunLog: '', piRunMeta: null });
    try {
      const data = await apiFetch('/api/pi/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace: activeWorkspace,
          mode: 'read_only',
          prompt: piRunPrompt,
        }),
      });
      set({ piRunId: data.run_id, piRunPolling: true });
    } catch (err) {
      set({ piRunLog: 'Error: ' + err.message });
    }
  },

  fetchPiRunLog: async (runId) => {
    if (!runId) return;
    try {
      const [metaRes, logRes] = await Promise.all([
        apiFetch(`/api/pi/runs/${runId}`),
        fetch(`/api/pi/runs/${runId}/log`).then(r => r.json()),
      ]);
      set({
        piRunMeta: metaRes,
        piRunLog: logRes.stdout || '',
      });
      if (metaRes.state === 'completed' || metaRes.state === 'error' || metaRes.state === 'stopped') {
        set({ piRunPolling: false });
      }
    } catch (err) {
      set({ piRunPolling: false });
    }
  },
}));

export default useAgentRunnerStore;
