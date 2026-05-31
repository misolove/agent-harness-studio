import React, { useEffect, useRef } from 'react';
import useAgentRunnerStore from '../stores/useAgentRunnerStore';
import useHarnessStore from '../stores/useHarnessStore';
import { API_BASE } from '../stores/useHarnessStore';

export default function AgentRunnerPanel() {
  const {
    agentRunners, agentRunnersLoading,
    piPreview, piPreviewPrompt, setPiPreviewPrompt,
    piRunPrompt, setPiRunPrompt,
    piRunId, piRunMeta, piRunLog, piRunPolling,
    fetchAgentRunners,
  } = useAgentRunnerStore();

  const { activeWorkspace, workspaces } = useHarnessStore();
  const activeWorkspaceName = workspaces.find(ws => ws.path === activeWorkspace)?.name || "Agent";

  const setPiPreview = (val) => useAgentRunnerStore.setState({ piPreview: val });
  const setPiRunId = (val) => useAgentRunnerStore.setState({ piRunId: val });
  const setPiRunMeta = (val) => useAgentRunnerStore.setState({ piRunMeta: val });
  const setPiRunLog = (val) => useAgentRunnerStore.setState({ piRunLog: val });
  const setPiRunPolling = (val) => useAgentRunnerStore.setState({ piRunPolling: val });

  const previewPiRun = () => {
    setPiPreview({ loading: true });
    fetch(`${API_BASE}/api/pi/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workspace: activeWorkspace,
        mode: "rpc",
        prompt: piPreviewPrompt,
      }),
    })
      .then(r => {
        if (!r.ok) return r.json().then(e => { throw new Error(e.detail || r.status); });
        return r.json();
      })
      .then(data => setPiPreview(data))
      .catch(err => setPiPreview({ error: err.message }));
  };

  const submitPiRun = () => {
    if (!piRunPrompt.trim()) return;
    setPiRunMeta({ state: "STARTING" });
    setPiRunLog("");
    setPiRunId(null);
    setPiRunPolling(false);
    fetch(`${API_BASE}/api/pi/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workspace: activeWorkspace,
        mode: "read_only",
        prompt: piRunPrompt,
      }),
    })
      .then(r => {
        if (!r.ok) return r.json().then(e => { throw new Error(e.detail || r.status); });
        return r.json();
      })
      .then(data => {
        setPiRunId(data.run_id);
        setPiRunMeta(data);
        setPiRunPolling(true);
      })
      .catch(err => setPiRunMeta({ state: "ERROR", error: err.message }));
  };

  const fetchPiRunLog = (runId) => {
    if (!runId) return;
    Promise.all([
      fetch(`${API_BASE}/api/pi/runs/${runId}`).then(r => r.json()),
      fetch(`${API_BASE}/api/pi/runs/${runId}/log?lines=300`).then(r => r.json()),
    ])
      .then(([meta, log]) => {
        setPiRunMeta(meta);
        const combined = [
          log.stdout ? "=== stdout ===\n" + log.stdout : "",
          log.stderr ? "=== stderr ===\n" + log.stderr : "",
        ].filter(Boolean).join("\n\n");
        setPiRunLog(combined);
        if (meta.state === "DONE" || meta.state === "ERROR" || meta.state === "TIMEOUT") {
          setPiRunPolling(false);
        }
      })
      .catch(() => {});
  };

  const piRunPollingRef = useRef(null);
  useEffect(() => {
    if (piRunPolling && piRunId) {
      piRunPollingRef.current = setInterval(() => fetchPiRunLog(piRunId), 2000);
    } else {
      clearInterval(piRunPollingRef.current);
    }
    return () => clearInterval(piRunPollingRef.current);
  }, [piRunPolling, piRunId]);

  return (
    <div className="agent-runner-container">
      <div className="audit-timeline-header">
        <h4>Agent Runner — {activeWorkspaceName}</h4>
        <button onClick={() => fetchAgentRunners()} className="refresh-btn" disabled={agentRunnersLoading}>
          {agentRunnersLoading ? "Detecting…" : "Re-detect"}
        </button>
      </div>

      {agentRunnersLoading && <div className="editor-loading">Detecting local agent runtimes…</div>}
      {!agentRunnersLoading && agentRunners.map((runner) => (
        <div key={runner.id} className="agent-runner-card">
          <div className="agent-runner-head">
            <div>
              <div className="agent-runner-name">{runner.name}</div>
              <div className="agent-runner-path">{runner.executable || "pi CLI not found"}</div>
            </div>
            <span className={`item-state state-${(runner.state || "missing").toLowerCase()}`}>
              {runner.state}
            </span>
          </div>

          {runner.error ? (
            <div className="session-msg-error">{runner.error}</div>
          ) : (
            <>
              <div className="agent-runner-grid">
                <div className="agent-runner-stat">
                  <span>Version</span>
                  <strong>{runner.version || "-"}</strong>
                </div>
                <div className="agent-runner-stat">
                  <span>Mode</span>
                  <strong>{runner.safety?.current_stage || "detect-only"}</strong>
                </div>
                <div className="agent-runner-stat">
                  <span>Sessions</span>
                  <strong>{runner.config?.session_count ?? 0}</strong>
                </div>
                <div className="agent-runner-stat">
                  <span>Auth</span>
                  <strong>{runner.config?.auth_configured ? "configured" : "missing"}</strong>
                </div>
                <div className="agent-runner-stat">
                  <span>Provider</span>
                  <strong>{runner.provider_info?.defaultProvider || "-"}</strong>
                </div>
                <div className="agent-runner-stat">
                  <span>Model</span>
                  <strong>{runner.provider_info?.defaultModel || "-"}</strong>
                </div>
              </div>

              <div className="agent-runner-detail">
                <span className="plugin-detail-label">Capabilities</span>
                <div className="plugin-chips">
                  {Object.entries(runner.capabilities || {})
                    .filter(([, value]) => value === true)
                    .map(([key]) => <span key={key} className="plugin-chip plugin-chip-tool">{key}</span>)}
                </div>
              </div>

              <div className="agent-runner-detail">
                <span className="plugin-detail-label">Detected config</span>
                <div className="agent-runner-kv">
                  <span>Agent dir</span><code>{runner.config?.agent_dir}</code>
                  <span>Settings</span><code>{runner.config?.settings?.exists ? "present" : "missing"}</code>
                  <span>Auth file</span><code>{runner.config?.auth?.exists ? "present" : "missing"}</code>
                  <span>Env keys</span><code>{runner.config?.env_keys_present?.length ? runner.config.env_keys_present.join(", ") : "none"}</code>
                </div>
              </div>

              <div className="agent-runner-safe-box">
                <strong>Safe execution path</strong>
                {(runner.safety?.recommended_next || []).map((step, idx) => (
                  <div key={idx} className="agent-runner-step">{idx + 1}. {step}</div>
                ))}
              </div>

              <div className="agent-runner-preview">
                <textarea
                  value={piPreviewPrompt}
                  onChange={(e) => setPiPreviewPrompt(e.target.value)}
                  rows={3}
                  placeholder="Prompt to preview for a future Pi run"
                />
                <button className="sessions-more-btn" onClick={previewPiRun} disabled={!runner.installed}>
                  Preview RPC Command
                </button>
              </div>

              {piPreview?.loading && <div className="session-msg-loading">Preparing preview…</div>}
              {piPreview?.error && <div className="session-msg-error">{piPreview.error}</div>}
              {piPreview?.command && (
                <pre className="diff-stat-block">{piPreview.command.join(" ")}</pre>
              )}

              {/* ── Run (read-only) ── */}
              <div className="agent-runner-safe-box" style={{marginTop:"12px"}}>
                <strong>Run (read-only) — tools: read, grep, find, ls</strong>
                <div className="agent-runner-preview" style={{marginTop:"8px"}}>
                  <textarea
                    value={piRunPrompt}
                    onChange={(e) => setPiRunPrompt(e.target.value)}
                    rows={3}
                    placeholder="Enter a read-only prompt for Pi…"
                  />
                  <div style={{display:"flex", gap:"8px", alignItems:"center", marginTop:"6px"}}>
                    <button
                      className="sessions-more-btn"
                      onClick={submitPiRun}
                      disabled={!runner.installed || piRunPolling || !piRunPrompt.trim()}
                    >
                      {piRunPolling ? "Running…" : "Run (read-only)"}
                    </button>
                    {piRunId && (
                      <span style={{fontSize:"11px", color:"var(--text-muted)", fontFamily:"monospace"}}>
                        {piRunId.slice(0, 8)}
                      </span>
                    )}
                    {piRunMeta?.state && (
                      <span className={`item-state state-${piRunMeta.state.toLowerCase()}`}>
                        {piRunMeta.state}
                      </span>
                    )}
                  </div>
                </div>
                {piRunMeta?.error && (
                  <div className="session-msg-error" style={{marginTop:"6px"}}>{piRunMeta.error}</div>
                )}
                {piRunLog && (
                  <pre className="diff-stat-block" style={{marginTop:"8px", maxHeight:"320px", overflowY:"auto", whiteSpace:"pre-wrap", wordBreak:"break-all"}}>
                    {piRunLog}
                  </pre>
                )}
                {piRunMeta?.post_audit && (
                  <div style={{marginTop:"8px", fontSize:"12px", color:"var(--text-muted)"}}>
                    Post-audit: {piRunMeta.post_audit.file_count} files changed
                    {piRunMeta.post_audit.stat && (
                      <pre className="diff-stat-block" style={{marginTop:"4px"}}>{piRunMeta.post_audit.stat}</pre>
                    )}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
