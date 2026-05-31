import { create } from 'zustand';
import { apiFetch } from './useHarnessStore';

const useEditorStore = create((set, get) => ({
  editingItem: null,
  editContent: '',
  saveStatus: '',
  editLoading: false,
  lastBackup: null,
  lastCommit: null,
  commitMsg: '',
  showHistory: false,
  gitLog: [],

  openEditor: async (item) => {
    set({
      editingItem: item,
      editContent: '',
      saveStatus: '',
      lastBackup: null,
      lastCommit: null,
      showHistory: false,
      commitMsg: '',
      gitLog: [],
      editLoading: true,
    });
    try {
      const allowMissing = item.metadata?.exists === false ? '&allow_missing=true' : '';
      const logLimit = item.type === 'Log File' ? '&max_bytes=200000&tail=true' : '';
      const data = await apiFetch(
        `/api/read?path=${encodeURIComponent(item.source_path)}${allowMissing}${logLimit}`
      );
      let status = '';
      if (data.missing) status = 'New file. Choose a preset or write content, then Save.';
      else if (data.truncated) status = `Showing tail: ${data.bytes_read?.toLocaleString()} / ${data.size_bytes?.toLocaleString()} bytes`;
      set({ editContent: data.content, saveStatus: status, editLoading: false });
    } catch (err) {
      set({
        editContent: `# Error loading file\n# ${err.message}\n# Path: ${item.source_path}`,
        saveStatus: 'Failed to load file content.',
        editLoading: false,
      });
    }
    get().fetchGitLog(item.source_path);
  },

  save: async () => {
    const { editingItem, editContent, commitMsg } = get();
    if (!editingItem) return false;
    set({ saveStatus: 'Saving...' });
    try {
      const data = await apiFetch('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: editingItem.source_path,
          content: editContent,
          commit_message: commitMsg.trim() || `harness-studio: edit ${editingItem.name}`,
        }),
      });
      const git = data.git;
      if (git?.committed) {
        set({ lastCommit: git, saveStatus: `Saved & committed (${git.hash})` });
      } else {
        set({ saveStatus: data.backup ? 'Saved. (backup created)' : 'Saved successfully!' });
      }
      set({ lastBackup: data.backup || null, commitMsg: '' });
      get().fetchGitLog(editingItem.source_path);
      return true;
    } catch (err) {
      set({ saveStatus: `Error: ${err.message}` });
      return false;
    }
  },

  rollback: async () => {
    const { editingItem } = get();
    if (!editingItem) return;
    try {
      const data = await apiFetch('/api/rollback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: editingItem.source_path }),
      });
      set({ saveStatus: `Rolled back from ${data.from_backup}` });
      get().openEditor(editingItem);
    } catch (err) {
      set({ saveStatus: `Rollback error: ${err.message}` });
    }
  },

  fetchGitLog: async (filePath) => {
    if (!filePath) return;
    try {
      const data = await apiFetch(`/api/git/log?path=${encodeURIComponent(filePath)}&limit=20`);
      set({ gitLog: data.commits || [] });
    } catch (err) {
      set({ gitLog: [] });
    }
  },

  gitRollback: async (filePath, commitHash) => {
    set({ saveStatus: 'Restoring...' });
    try {
      const data = await apiFetch('/api/git/rollback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filePath, commit_hash: commitHash }),
      });
      set({ saveStatus: `Restored to ${data.to_commit}. Backup: ${data.backup || 'none'}` });
      const { editingItem } = get();
      if (editingItem) get().openEditor(editingItem);
    } catch (err) {
      set({ saveStatus: `Restore error: ${err.message}` });
    }
  },

  setEditContent: (content) => set({ editContent: content }),
  setCommitMsg: (msg) => set({ commitMsg: msg }),
  setSaveStatus: (status) => set({ saveStatus: status }),
  closeEditor: () => set({ editingItem: null, lastBackup: null, lastCommit: null }),
  toggleHistory: () => set((s) => ({ showHistory: !s.showHistory })),
  setGitLog: (log) => set({ gitLog: log }),
}));

export default useEditorStore;
