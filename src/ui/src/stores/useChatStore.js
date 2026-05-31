import { create } from 'zustand';
import { apiFetch } from './useHarnessStore';

const useChatStore = create((set, get) => ({
  prompt: '',
  chatHistory: [],
  molderResponse: null,
  llmProvider: null,
  showLlmSettings: false,
  llmDraft: { provider: '', base_url: '', model: '', api_key: '' },
  llmStatus: '',
  piMode: false,
  piMoldRunId: null,
  piMoldPolling: false,
  piMoldSessionFile: null,

  setPrompt: (p) => set({ prompt: p }),
  setPiMode: (m) => set({ piMode: m }),
  setShowLlmSettings: (s) => set({ showLlmSettings: s }),
  setChatHistory: (updater) => set((s) => ({
    chatHistory: typeof updater === 'function' ? updater(s.chatHistory) : updater,
  })),
  setMolderResponse: (r) => set({ molderResponse: r }),
  setLlmProvider: (p) => set({ llmProvider: p }),
  setLlmDraft: (d) => set({ llmDraft: d }),
  setLlmStatus: (s) => set({ llmStatus: s }),
  setPiMoldRunId: (id) => set({ piMoldRunId: id }),
  setPiMoldPolling: (p) => set({ piMoldPolling: p }),
  setPiMoldSessionFile: (f) => set({ piMoldSessionFile: f }),

  fetchLlmProvider: async () => {
    try {
      const data = await apiFetch('/api/llm/provider');
      set({
        llmProvider: data,
        llmDraft: {
          provider: data.provider || '',
          base_url: data.base_url || '',
          model: data.model || '',
          api_key: '',
        },
      });
    } catch (err) {
      set({ llmStatus: 'LLM provider unavailable' });
    }
  },

  saveLlmProvider: async () => {
    const { llmDraft } = get();
    set({ llmStatus: 'Saving...' });
    try {
      const data = await apiFetch('/api/llm/provider', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(llmDraft),
      });
      set({ llmProvider: data, llmStatus: 'Saved successfully!', showLlmSettings: false });
    } catch (err) {
      set({ llmStatus: 'Error: ' + err.message });
    }
  },

  handleLlmPresetChange: (presetName, presets) => {
    const preset = presets[presetName];
    if (!preset) return;
    set({
      llmDraft: {
        provider: presetName,
        base_url: preset.base_url,
        model: preset.model,
        api_key: '',
      },
    });
  },

  sendMold: async ({ prompt, context, editingItem, editContent, chatHistory, activeWorkspace }) => {
    const userMsg = { role: 'user', text: prompt };
    set((s) => ({
      chatHistory: [...s.chatHistory, userMsg],
      prompt: '',
      molderResponse: { status: 'loading' },
    }));

    try {
      const data = await apiFetch('/api/mold', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: userMsg.text,
          context,
          history: chatHistory?.slice(-10),
          editing_file_name: editingItem?.name || null,
          editing_file_content: editingItem ? editContent : null,
        }),
      });
      const message = data.message || '';
      set((s) => ({
        molderResponse: { ...data, message },
        chatHistory: [...s.chatHistory, { role: 'assistant', text: message, data }],
      }));
    } catch (err) {
      set((s) => ({
        molderResponse: { status: 'error', message: err.message },
        chatHistory: [...s.chatHistory, { role: 'assistant', text: 'Error: ' + err.message, error: true }],
      }));
    }
  },

  sendMoldWithPi: async ({ prompt, activeWorkspace, sessionFile, envInfo }) => {
    const userMsg = { role: 'user', text: `[Pi Agent] ${prompt}` };
    set((s) => ({
      chatHistory: [...s.chatHistory, userMsg],
      prompt: '',
      piMoldPolling: true,
      molderResponse: { status: 'loading' },
    }));

    try {
      const data = await apiFetch('/api/pi/mold', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt,
          workspace: activeWorkspace,
          session_file: sessionFile || null,
        }),
      });
      set({
        piMoldRunId: data.run_id,
        piMoldSessionFile: data.session_file,
      });
    } catch (err) {
      set((s) => ({
        chatHistory: [...s.chatHistory, { role: 'assistant', text: 'Pi Agent Error: ' + err.message, error: true }],
        piMoldPolling: false,
        molderResponse: null,
      }));
    }
  },

  addAssistantMessage: (msg) => {
    set((s) => ({ chatHistory: [...s.chatHistory, msg] }));
  },

  clearMolderResponse: () => set({ molderResponse: null }),

  resetPiSession: () => set({
    piMoldSessionFile: null,
    piMoldRunId: null,
    piMoldPolling: false,
  }),
}));

export default useChatStore;
