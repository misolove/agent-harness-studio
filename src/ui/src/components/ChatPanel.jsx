import React, { useRef, useEffect, useCallback } from 'react';
import useChatStore from '../stores/useChatStore';
import useHarnessStore from '../stores/useHarnessStore';
import useEditorStore from '../stores/useEditorStore';
import { API_BASE, apiFetch } from '../stores/useHarnessStore';
import MarkdownContent from './MarkdownContent';
import normalizeMolderMessage from './MolderMessage';

const LLM_PROVIDER_PRESETS = [
  { provider: "llm-proxy", base_url: "http://localhost:20128/v1", model: "harness-model" },
  { provider: "OpenAI", base_url: "", model: "gpt-4o" },
  { provider: "OpenAI Compatible", base_url: "http://127.0.0.1:11434/v1", model: "llama3.1" },
  { provider: "Custom", base_url: "", model: "" },
];

export default function ChatPanel({ chatWidth, sections, onEditFile }) {
  const {
    prompt, setPrompt,
    chatHistory, setChatHistory,
    molderResponse, setMolderResponse,
    llmProvider, setLlmProvider,
    showLlmSettings, setShowLlmSettings,
    llmDraft, setLlmDraft,
    llmStatus, setLlmStatus,
    piMode, setPiMode,
    piMoldRunId, setPiMoldRunId,
    piMoldPolling, setPiMoldPolling,
    piMoldSessionFile, setPiMoldSessionFile,
  } = useChatStore();

  const {
    activeWorkspace, envInfo,
  } = useHarnessStore();

  const {
    editingItem, editContent, setSaveStatus,
  } = useEditorStore();

  const chatMessagesRef = useRef(null);

  const scrollChatToBottom = () => {
    if (!chatMessagesRef.current) return;
    chatMessagesRef.current.scrollTop = chatMessagesRef.current.scrollHeight;
  };

  useEffect(() => { scrollChatToBottom(); }, [chatHistory, molderResponse]);
  useEffect(() => { setTimeout(scrollChatToBottom, 0); }, []);

  const fetchLlmProvider = () => {
    fetch(`${API_BASE}/api/llm/provider`)
      .then(res => res.json())
      .then(data => {
        setLlmProvider(data);
        setLlmDraft({
          provider: data.provider || "",
          base_url: data.base_url || "",
          model: data.model || "",
          api_key: "",
        });
      })
      .catch(() => setLlmStatus("LLM provider unavailable"));
  };

  useEffect(() => { fetchLlmProvider(); }, []);

  const saveLlmProvider = () => {
    setLlmStatus("Saving...");
    fetch(`${API_BASE}/api/llm/provider`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(llmDraft),
    })
      .then(res => {
        if (!res.ok) return res.json().then(e => { throw new Error(e.detail || res.status); });
        return res.json();
      })
      .then(data => {
        setLlmProvider(data);
        setLlmDraft({
          provider: data.provider || "",
          base_url: data.base_url || "",
          model: data.model || "",
          api_key: "",
        });
        setLlmStatus("Saved");
        setShowLlmSettings(false);
        setTimeout(() => setLlmStatus(""), 1800);
      })
      .catch(err => setLlmStatus(`Error: ${err.message}`));
  };

  const handleLlmPresetChange = (provider) => {
    const preset = LLM_PROVIDER_PRESETS.find(p => p.provider === provider);
    if (!preset) return;
    setLlmDraft(v => ({
      ...v,
      provider: preset.provider,
      base_url: preset.base_url || v.base_url,
      model: preset.model || v.model,
    }));
  };

  const handleApply = (response) => {
    if (!response || !response.content) return;
    const home = envInfo?.hermes_home;
    if (!home) {
      setSaveStatus("Error: environment info not loaded yet.");
      return;
    }
    if (!response.action.includes("SKILL")) {
      setSaveStatus(`Action ${response.action} needs a structured apply flow before it can be saved safely.`);
      return;
    }
    const path = `${home}/skills/${response.name}/SKILL.md`;
    setSaveStatus("Applying...");
    fetch(`${API_BASE}/api/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, content: response.content }),
    })
      .then(res => {
        if (!res.ok) return res.json().then(e => { throw new Error(e.detail || res.status); });
        return res.json();
      })
      .then(() => {
        setSaveStatus("Applied successfully!");
        setMolderResponse(null);
        useHarnessStore.getState().fetchHarness();
      })
      .catch(() => setSaveStatus("Error applying."));
  };

  const handleMoldWithPi = () => {
    const currentPrompt = prompt;
    if (!currentPrompt.trim() || piMoldPolling) return;
    const userMsg = { role: "user", text: currentPrompt };
    setChatHistory(prev => [...prev, userMsg]);
    setPrompt("");
    setMolderResponse({ status: "loading", piMode: true });

    const selectedTitle = useHarnessStore.getState().selectedSection
      ? sections?.find(s => s.id === useHarnessStore.getState().selectedSection)?.title || ""
      : "";

    fetch(`${API_BASE}/api/pi/mold`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: userMsg.text,
        context: selectedTitle,
        editing_file_name: editingItem?.name || null,
        editing_file_content: editingItem ? editContent : null,
        workspace: activeWorkspace,
        session_file: piMoldSessionFile,
      }),
    })
      .then(r => {
        if (!r.ok) return r.json().then(e => { throw new Error(e.detail || r.status); });
        return r.json();
      })
      .then(data => {
        setPiMoldRunId(data.run_id);
        setPiMoldPolling(true);
        if (data.session_file) setPiMoldSessionFile(data.session_file);
      })
      .catch(err => {
        setMolderResponse({ status: "error", message: err.message });
        setChatHistory(prev => [...prev, { role: "assistant", text: "Pi error: " + err.message, error: true }]);
      });
  };

  const handleMold = () => {
    if (!prompt.trim()) return;
    if (molderResponse?.status === "loading" || piMoldPolling) return;
    if (piMode) { handleMoldWithPi(); return; }

    const userMsg = { role: "user", text: prompt };
    setChatHistory(prev => [...prev, userMsg]);
    setPrompt("");

    const selectedTitle = useHarnessStore.getState().selectedSection
      ? sections?.find(s => s.id === useHarnessStore.getState().selectedSection)?.title || ""
      : "";

    setMolderResponse({ status: "loading" });
    fetch(`${API_BASE}/api/mold`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: userMsg.text,
        context: selectedTitle,
        history: chatHistory.slice(-10),
        editing_file_name: editingItem?.name || null,
        editing_file_content: editingItem ? editContent : null,
      }),
    })
      .then(res => res.json())
      .then(data => {
        const message = normalizeMolderMessage(data);
        const normalizedData = { ...data, message };
        setMolderResponse(normalizedData);
        setChatHistory(prev => [...prev, { role: "assistant", text: message, data: normalizedData }]);
      })
      .catch(err => {
        setMolderResponse({ status: "error", message: err.message });
        setChatHistory(prev => [...prev, { role: "assistant", text: "Error: " + err.message, error: true }]);
      });
  };

  const piMoldRef = React.useRef(null);
  React.useEffect(() => {
    if (!piMoldPolling || !piMoldRunId) {
      clearInterval(piMoldRef.current);
      return;
    }
    piMoldRef.current = setInterval(() => {
      Promise.all([
        fetch(`${API_BASE}/api/pi/runs/${piMoldRunId}`).then(r => r.json()),
        fetch(`${API_BASE}/api/pi/runs/${piMoldRunId}/log?lines=500`).then(r => r.json()),
      ]).then(([meta, log]) => {
        const status = meta.status || "";
        if (["done", "error", "timeout", "stopped"].includes(status)) {
          setPiMoldPolling(false);
          clearInterval(piMoldRef.current);
          const answer = (log.stdout || "").trim() || (log.stderr || "").trim() || "(Pi 응답 없음)";
          const filePathRe = /(?:파일|File|file|경로|path)[\s:：]+([~/][^\s\n`'"()]+\.[a-zA-Z]+)/gi;
          const absPathRe = /`([/~][^\s\n`'"()]+\.[a-zA-Z]+)`/g;
          const mentionedFiles = new Set();
          let _m;
          while ((_m = filePathRe.exec(answer)) !== null) mentionedFiles.add(_m[1]);
          while ((_m = absPathRe.exec(answer)) !== null) mentionedFiles.add(_m[1]);
          setMolderResponse(null);
          setChatHistory(prev => [...prev, {
            role: "assistant",
            text: answer,
            piRun: true,
            error: status !== "done",
            mentionedFiles: [...mentionedFiles],
          }]);
        }
      }).catch(() => {});
    }, 2000);
    return () => clearInterval(piMoldRef.current);
  }, [piMoldPolling, piMoldRunId]);

  const handleFileClick = (fp) => {
    if (onEditFile) {
      onEditFile({ source_path: fp, name: fp.split("/").pop() });
    }
  };

  return (
    <section className="chat-container" style={chatWidth ? { flex: `0 0 ${chatWidth}px` } : undefined}>
      <header className="chat-header">
        <div className="chat-title-block">
          <h3>✨ Chat Molder</h3>
          <div className="pi-mode-toggle">
            <button
              className={`pi-toggle-btn${!piMode ? " active" : ""}`}
              onClick={() => setPiMode(false)}
              title="Direct LLM call — fast, no tool access"
            >LLM</button>
            <button
              className={`pi-toggle-btn${piMode ? " active" : ""}`}
              onClick={() => setPiMode(true)}
              title="Pi Coding Agent — can read files, search code"
            >Pi Agent</button>
          </div>
          {piMode && piMoldSessionFile && (
            <button
              className="pi-toggle-btn"
              style={{fontSize:"11px", padding:"3px 8px", opacity:0.7}}
              onClick={() => {
                setPiMoldSessionFile(null);
                setChatHistory([]);
                setMolderResponse(null);
              }}
              title="Pi 세션을 초기화하고 새 대화 시작"
            >새 대화</button>
          )}
        </div>
        <div className="llm-provider-card">
          <div className="llm-provider-main">
            <span className="llm-provider-label">LLM</span>
            <strong>{llmProvider?.provider || "Unknown"}</strong>
            <span className="llm-provider-model">{llmProvider?.model || "model?"}</span>
          </div>
          <button
            className="llm-edit-btn"
            onClick={() => setShowLlmSettings(v => !v)}
            title="Edit LLM provider"
          >
            Edit
          </button>
        </div>
      </header>

      {showLlmSettings && (
        <div className="llm-settings-panel">
          <label>
            Provider
            <select
              value={LLM_PROVIDER_PRESETS.some(p => p.provider === llmDraft.provider) ? llmDraft.provider : "Custom"}
              onChange={e => handleLlmPresetChange(e.target.value)}
            >
              {LLM_PROVIDER_PRESETS.map(preset => (
                <option key={preset.provider} value={preset.provider}>{preset.provider}</option>
              ))}
            </select>
          </label>
          <label>
            Endpoint
            <input
              value={llmDraft.base_url}
              onChange={e => setLlmDraft(v => ({ ...v, base_url: e.target.value }))}
              placeholder="http://localhost:20128/v1"
            />
          </label>
          <label>
            Model
            <input
              value={llmDraft.model}
              onChange={e => setLlmDraft(v => ({ ...v, model: e.target.value }))}
              placeholder="harness-model"
            />
          </label>
          <label>
            API Key
            <input
              type="password"
              value={llmDraft.api_key}
              onChange={e => setLlmDraft(v => ({ ...v, api_key: e.target.value }))}
              placeholder={llmProvider?.api_key_set ? "Configured - leave blank to keep" : "optional"}
            />
          </label>
          <div className="llm-settings-actions">
            <span>{llmStatus}</span>
            <button onClick={() => setShowLlmSettings(false)}>Cancel</button>
            <button className="save-btn" onClick={saveLlmProvider}>Save</button>
          </div>
        </div>
      )}

      <div className="chat-messages" ref={chatMessagesRef}>
        {chatHistory.length === 0 && (
          <div className="chat-empty">
            <p>Harness molding is a dialogue. Describe a skill, memory, or logic you want to add to your agent.</p>
          </div>
        )}
        {chatHistory.map((msg, i) => (
          <div key={i} className={`chat-bubble ${msg.role}`}>
            <div className="bubble-content">
              {msg.role === "assistant" ? (
                <>
                  {msg.data?.web_search && <div className="web-search-used">Auto web search used</div>}
                  {msg.piRun && <div className="web-search-used" style={{background:"#6366f1",color:"#fff"}}>Pi Agent (read · grep · find · ls · web_search)</div>}
                  <MarkdownContent text={msg.text} />
                  {msg.mentionedFiles?.length > 0 && (
                    <div style={{marginTop:"8px", display:"flex", flexWrap:"wrap", gap:"6px"}}>
                      {msg.mentionedFiles.map(fp => (
                        <button
                          key={fp}
                          className="sessions-more-btn"
                          style={{fontSize:"11px", padding:"3px 8px"}}
                          onClick={() => handleFileClick(fp)}
                          title={fp}
                        >
                          📄 {fp.split("/").pop()}
                        </button>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                msg.text
              )}
              {msg.data && msg.data.diff && (
                <div className="chat-proposal">
                  <pre className="diff-viewer">{msg.data.diff}</pre>
                  <button className="apply-btn" onClick={() => handleApply(msg.data)}>Apply Changes</button>
                </div>
              )}
            </div>
          </div>
        ))}
        {molderResponse?.status === "loading" && (
           <div className="chat-bubble assistant">
             <div className="bubble-content loading-dots">
               {piMoldPolling ? "Pi Agent 실행 중 (read · grep · find · ls)…" : "Thinking..."}
             </div>
           </div>
        )}
      </div>

      <footer className="chat-footer">
        <div className="chat-input-box">
          <input
            type="text"
            placeholder="Suggest a skill or memory..."
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== 'Enter' || e.nativeEvent.isComposing) return;
              e.preventDefault();
              handleMold();
            }}
          />
          <button onClick={handleMold} disabled={!prompt.trim() || molderResponse?.status === "loading" || piMoldPolling}>
            {piMoldPolling ? "Pi 실행 중…" : piMode ? "Pi로 보내기" : "Send"}
          </button>
        </div>
      </footer>
    </section>
  );
}
