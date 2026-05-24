import { useState, useEffect, useRef } from "react";
import "./App.css";
import ScrapingPipeline from "./ScrapingPipeline.jsx";

function renderInlineMarkdown(text) {
  const parts = [];
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let lastIndex = 0;
  let match;

  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const token = match[0];
    if (token.startsWith("**")) {
      parts.push(<strong key={parts.length}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith("`")) {
      parts.push(<code key={parts.length}>{token.slice(1, -1)}</code>);
    }
    lastIndex = match.index + token.length;
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return parts;
}

function parseMarkdownTable(lines, startIndex) {
  const header = lines[startIndex];
  const divider = lines[startIndex + 1];
  if (!header?.includes("|") || !divider?.match(/^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/)) {
    return null;
  }

  const tableLines = [header, divider];
  let index = startIndex + 2;
  while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
    tableLines.push(lines[index]);
    index += 1;
  }

  const splitRow = (line) => line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());

  return {
    headers: splitRow(tableLines[0]),
    rows: tableLines.slice(2).map(splitRow),
    nextIndex: index,
  };
}

function MarkdownContent({ text }) {
  const lines = String(text || "").split(/\r?\n/);
  const blocks = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    const trimmed = line.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    const table = parseMarkdownTable(lines, index);
    if (table) {
      blocks.push(
        <div className="md-table-wrap" key={blocks.length}>
          <table className="md-table">
            <thead>
              <tr>{table.headers.map((cell, i) => <th key={i}>{renderInlineMarkdown(cell)}</th>)}</tr>
            </thead>
            <tbody>
              {table.rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {table.headers.map((_, cellIndex) => (
                    <td key={cellIndex}>{renderInlineMarkdown(row[cellIndex] || "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
      index = table.nextIndex;
      continue;
    }

    if (trimmed.startsWith("### ")) {
      blocks.push(<h4 key={blocks.length}>{renderInlineMarkdown(trimmed.slice(4))}</h4>);
      index += 1;
      continue;
    }

    if (trimmed.startsWith("## ")) {
      blocks.push(<h3 key={blocks.length}>{renderInlineMarkdown(trimmed.slice(3))}</h3>);
      index += 1;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      const items = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ul key={blocks.length}>
          {items.map((item, i) => <li key={i}>{renderInlineMarkdown(item)}</li>)}
        </ul>
      );
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index].trim())) {
        items.push(lines[index].trim().replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(
        <ol key={blocks.length}>
          {items.map((item, i) => <li key={i}>{renderInlineMarkdown(item)}</li>)}
        </ol>
      );
      continue;
    }

    if (trimmed === "---") {
      blocks.push(<hr key={blocks.length} />);
      index += 1;
      continue;
    }

    blocks.push(<p key={blocks.length}>{renderInlineMarkdown(trimmed)}</p>);
    index += 1;
  }

  return <div className="markdown-content">{blocks}</div>;
}

function extractJsonMessageFragment(text) {
  const source = String(text || "");
  const fieldIndex = source.indexOf('"message"');
  if (fieldIndex < 0) return null;

  const colonIndex = source.indexOf(":", fieldIndex + 9);
  if (colonIndex < 0) return null;

  const quoteIndex = source.indexOf('"', colonIndex + 1);
  if (quoteIndex < 0) return null;

  let output = "";
  for (let index = quoteIndex + 1; index < source.length; index += 1) {
    const char = source[index];
    if (char === '"') break;
    if (char === "\\" && index + 1 < source.length) {
      const escaped = source[index + 1];
      if (escaped === "n") {
        output += "\n";
        index += 1;
        continue;
      }
      if (escaped === "t") {
        output += "\t";
        index += 1;
        continue;
      }
      if (escaped === "r") {
        index += 1;
        continue;
      }
      if (escaped === '"' || escaped === "\\" || escaped === "/") {
        output += escaped;
        index += 1;
        continue;
      }
    }
    output += char;
  }

  return output.trim() || null;
}

function normalizeMolderMessage(data) {
  const message = String(data?.message || "");
  const trimmed = message.trim();
  if (!trimmed.startsWith("{") || !trimmed.includes('"message"')) {
    return message;
  }

  try {
    const parsed = JSON.parse(trimmed);
    if (parsed && typeof parsed.message === "string") {
      return parsed.message;
    }
  } catch {
    const recovered = extractJsonMessageFragment(trimmed);
    if (recovered) {
      return `${recovered}\n\n(응답이 길어 일부가 잘렸습니다. 더 좁은 범위로 다시 물어보면 이어서 정리할 수 있어요.)`;
    }
  }

  return "응답 형식을 정리하지 못했습니다. 질문 범위를 조금 좁혀서 다시 말씀해주세요.";
}

function App() {
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSection, setSelectedSection] = useState(null);
  const [editingItem, setEditingItem] = useState(null);
  const [editContent, setEditContent] = useState("");
  const [saveStatus, setSaveStatus] = useState("");
  const [editLoading, setEditLoading] = useState(false);
  const [lastBackup, setLastBackup] = useState(null);
  const [gitLog, setGitLog] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [commitMsg, setCommitMsg] = useState("");
  const [lastCommit, setLastCommit] = useState(null);

  const [prompt, setPrompt] = useState("");
  const [chatHistory, setChatHistory] = useState([]);
  const [molderResponse, setMolderResponse] = useState(null);
  const [envInfo, setEnvInfo] = useState(null);

  // Web scraping state
  const [webUrl, setWebUrl] = useState("");
  const [scrapeResult, setScrapeResult] = useState(null);
  const [scrapeLoading, setScrapeLoading] = useState(false);
  const [scrapeError, setScrapeError] = useState(null);

  // Audit Logs state
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const API_BASE = "http://127.0.0.1:8766";
  const chatMessagesRef = useRef(null);

  const MAX_CONTEXT_TOKENS = 128000;

  const SOUL_PRESETS = {
    developer: `# Persona: Developer / Coding Assistant

I am a highly skilled senior software development assistant. I prioritize clean, modular, and maintainable code.

## Guidelines
- **Code Quality**: Write TypeScript/Python with precise type hints. Keep files short and split code into logical modules.
- **Commit Rules**: Always write clear, semantic Git commits. Commit changes frequently.
- **Tone**: Professional, technical, concise. Avoid fluff.`,

    researcher: `# Persona: Scientific Researcher

I am a meticulous scientific researcher specializing in biomedical and chemical intelligence.

## Guidelines
- **Verification**: Always cross-reference literature using PubMed and arXiv search.
- **Formatting**: Summarize structural data in neat Markdown tables with citations.
- **Tone**: Factual, clinical, academic. Explain biological and chemical hypotheses clearly.`,

    writer: `# Persona: Creative Content Writer

I am a versatile creative copywriter and technical writer focusing on high-quality explanations.

## Guidelines
- **Clarity**: Simplify complex jargon into clear metaphors and progressive explanations.
- **Style**: Use elegant typography layouts, appropriate list items, and GitHub alerts for visual variety.
- **Tone**: Warm, engaging, supportive.`
  };

  const applySoulPreset = (presetKey) => {
    const template = SOUL_PRESETS[presetKey];
    if (template) {
      setEditContent(template);
      setSaveStatus(`Applied ${presetKey} preset! (Be sure to Save)`);
    }
  };

  const handleConvertSkill = (targetFormat) => {
    fetch(`${API_BASE}/api/convert/skill`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: editContent, target: targetFormat })
    })
      .then(res => {
        if (!res.ok) throw new Error("Conversion failed");
        return res.json();
      })
      .then(data => {
        setEditContent(data.content);
        setSaveStatus(`Converted to ${targetFormat} format!`);
      })
      .catch(err => setSaveStatus(`Conversion error: ${err.message}`));
  };

  const fetchAuditLogs = () => {
    setAuditLoading(true);
    fetch(`${API_BASE}/api/audit/logs`)
      .then(res => res.json())
      .then(data => {
        setAuditLogs(data.logs || []);
        setAuditLoading(false);
      })
      .catch(err => {
        console.error(err);
        setAuditLoading(false);
      });
  };

  const handleSectionClick = (sectionId) => {
    setSelectedSection(sectionId);
    setEditingItem(null);
    if (sectionId === "audit") {
      fetchAuditLogs();
    }
  };

  const isEditable = (item) => {
    if (!item || !item.source_path) return false;
    const ext = item.source_path.split('.').pop().toLowerCase();
    return ["md", "yaml", "yml", "json", "txt", "py", "sh"].includes(ext);
  };

  const scrollChatToBottom = () => {
    if (!chatMessagesRef.current) return;
    chatMessagesRef.current.scrollTop = chatMessagesRef.current.scrollHeight;
  };

  useEffect(() => {
    scrollChatToBottom();
  }, [chatHistory, molderResponse]);

  useEffect(() => {
    setTimeout(scrollChatToBottom, 0);
  }, []);

  const fetchEnv = () => {
    fetch(`${API_BASE}/api/env`)
      .then((res) => res.json())
      .then((data) => setEnvInfo(data))
      .catch((err) => console.error("Failed to fetch env info", err));
  };

  const fetchHarness = () => {
    setLoading(true);
    fetch(`${API_BASE}/api/scan`)
      .then((res) => {
        if (!res.ok) throw new Error("API error: " + res.status);
        return res.json();
      })
      .then((data) => {
        setSummary(data.summary);
        setItems(data.items);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setError(err.message);
        setLoading(false);
      });
  };

  const fetchGitLog = (filePath) => {
    const url = filePath
      ? `${API_BASE}/api/git/log?path=${encodeURIComponent(filePath)}&limit=20`
      : `${API_BASE}/api/git/log?limit=20`;
    fetch(url)
      .then(r => r.json())
      .then(data => setGitLog(data.commits || []))
      .catch(() => setGitLog([]));
  };

  const handleGitInit = () => {
    fetch(`${API_BASE}/api/git/init`, { method: "POST" })
      .then(r => r.json())
      .then(() => fetchEnv())
      .catch(err => console.error("Git init failed", err));
  };

  const handleGitRollback = (filePath, hash, shortHash) => {
    if (!window.confirm(`${shortHash} 커밋 상태로 되돌릴까요?\n파일: ${filePath}`)) return;
    fetch(`${API_BASE}/api/git/rollback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: filePath, commit_hash: hash }),
    })
      .then(r => {
        if (!r.ok) return r.json().then(e => { throw new Error(e.detail); });
        return r.json();
      })
      .then(() => {
        setShowHistory(false);
        handleEditClick(editingItem);
        fetchGitLog(filePath);
      })
      .catch(err => setSaveStatus(`Git rollback 실패: ${err.message}`));
  };

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchEnv();
      fetchHarness();
    }, 0);
    return () => clearTimeout(timer);
  }, []);

  const sections = [
    { id: "skills", title: "Skills", icon: "🛠️" },
    { id: "bundles", title: "Skill Bundles", icon: "📦" },
    { id: "mcp", title: "MCP", icon: "🔌" },
    { id: "hooks", title: "Hooks", icon: "🪝" },
    { id: "memory", title: "Memory Map", icon: "🧠" },
    { id: "cron", title: "Cron", icon: "⏰" },
    { id: "plugins", title: "Plugins", icon: "🧩" },
    { id: "context", title: "Context", icon: "📜" },
    { id: "config", title: "Config", icon: "⚙️" },
    { id: "audit", title: "Audit Log", icon: "📋" },
    { id: "web", title: "Web Context", icon: "🌐" },
  ];

  const getFilteredItems = () => {
    if (!selectedSection) return [];
    const map = {
      skills: ["Skill"],
      bundles: ["Skill Bundle"],
      memory: ["Memory Config", "Memory Manifest", "Memory Directory", "Memory State"],
      mcp: ["MCP Server"],
      context: ["Root Context"],
      hooks: ["Hook"],
      cron: ["Cron Job"],
      plugins: ["Plugin"],
      config: ["Memory Config", "Root Context", "MCP Server"],
      audit: [],
      web: [],
    };
    const allowed = map[selectedSection] || [];
    return items.filter(i => allowed.includes(i.type));
  };

  const handleEditClick = async (item) => {
    setEditingItem(item);
    setEditContent("");
    setSaveStatus("");
    setLastBackup(null);
    setLastCommit(null);
    setShowHistory(false);
    setCommitMsg("");
    setGitLog([]);
    setEditLoading(true);
    try {
      const allowMissing = item.metadata?.exists === false ? "&allow_missing=true" : "";
      const res = await fetch(`${API_BASE}/api/read?path=${encodeURIComponent(item.source_path)}${allowMissing}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEditContent(data.content);
      if (data.missing) {
        setSaveStatus("New file. Choose a preset or write content, then Save.");
      }
    } catch (err) {
      setEditContent(`# Error loading file\n# ${err.message}\n# Path: ${item.source_path}`);
      setSaveStatus("Failed to load file content.");
    } finally {
      setEditLoading(false);
    }
    if (envInfo?.is_git_repo) fetchGitLog(item.source_path);
  };

  const handleSave = () => {
    setSaveStatus("Saving...");
    fetch(`${API_BASE}/api/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        path: editingItem.source_path,
        content: editContent,
        commit_message: commitMsg.trim() || `harness-studio: edit ${editingItem.name}`,
      }),
    })
      .then(res => {
        if (!res.ok) return res.json().then(e => { throw new Error(e.detail || res.status); });
        return res.json();
      })
      .then(data => {
        setLastBackup(data.backup || null);
        const git = data.git;
        if (git?.committed) {
          setLastCommit(git);
          setSaveStatus(`Saved & committed (${git.hash})`);
        } else {
          setSaveStatus(data.backup ? "Saved. (backup created)" : "Saved successfully!");
        }
        fetchGitLog(editingItem.source_path);
        setCommitMsg("");
        setTimeout(() => {
          setEditingItem(null);
          setLastBackup(null);
          setLastCommit(null);
          fetchHarness();
        }, 1800);
      })
      .catch(err => {
        console.error(err);
        setSaveStatus(`Error: ${err.message}`);
      });
  };

  const handleRollback = (sourcePath) => {
    if (!window.confirm("마지막 백업으로 되돌릴까요?")) return;
    fetch(`${API_BASE}/api/rollback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: sourcePath })
    })
      .then(res => {
        if (!res.ok) return res.json().then(e => { throw new Error(e.detail || res.status); });
        return res.json();
      })
      .then(() => {
        setSaveStatus("Rolled back!");
        setEditingItem(null);
        setLastBackup(null);
        fetchHarness();
      })
      .catch(err => setSaveStatus(`Rollback failed: ${err.message}`));
  };

  const handleMold = () => {
    if (!prompt.trim()) return;
    if (molderResponse?.status === "loading") return;

    const userMsg = { role: "user", text: prompt };
    setChatHistory(prev => [...prev, userMsg]);
    setPrompt("");

    // Build context string from selected item
    const selectedTitle = selectedSection
      ? sections.find(s => s.id === selectedSection)?.title || ""
      : "";

    setMolderResponse({ status: "loading" });
    fetch(`${API_BASE}/api/mold`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prompt: userMsg.text,
        context: selectedTitle,
        history: chatHistory.slice(-10),
      })
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
      body: JSON.stringify({ path: path, content: response.content })
    })
      .then(res => {
        if (!res.ok) return res.json().then(e => { throw new Error(e.detail || res.status); });
        return res.json();
      })
      .then(() => {
        setSaveStatus("Applied successfully!");
        setMolderResponse(null);
        fetchHarness();
      })
      .catch(err => {
        console.error(err);
        setSaveStatus("Error applying.");
      });
  };

  const handleScrape = () => {
    const url = webUrl.trim();
    if (!url) return;

    setScrapeLoading(true);
    setScrapeError(null);
    setScrapeResult(null);

    fetch(`${API_BASE}/api/web/scrape`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url })
    })
      .then(res => {
        if (!res.ok) throw new Error("Scrape API error: " + res.status);
        return res.json();
      })
      .then(data => {
        setScrapeResult(data);
        if (data.status === "error" && !data.attempts?.length) {
          setScrapeError(data.error || "Scrape failed.");
        }
      })
      .catch(err => {
        console.error(err);
        setScrapeError(err.message);
      })
      .finally(() => setScrapeLoading(false));
  };

  const getMemoryConflicts = () => {
    const conflicts = [];
    const memoryDir = items.find(i => i.type === "Memory Directory");
    const memoryFiles = memoryDir?.metadata?.md_files || [];
    const configMemory = items.find(i => i.type === "Memory Config")?.metadata || {};

    Object.keys(configMemory).forEach(key => {
      const matchedFile = memoryFiles.find(f => f.toLowerCase() === `${key.toLowerCase()}.md`);
      if (matchedFile) {
        conflicts.push({
          type: "Overlap",
          message: `Config key "${key}" overlaps with memory file "${matchedFile}". This might lead to duplicate memory references during runtime.`
        });
      }
    });

    return conflicts;
  };
  const memoryConflicts = getMemoryConflicts();

  const estimatedTotalTokens = items.reduce((sum, item) => sum + (item.token_estimate || 0), 0);
  const tokenPercentage = (estimatedTotalTokens / MAX_CONTEXT_TOKENS) * 100;
  let tokenStatusColor = "safe";
  if (tokenPercentage > 75) tokenStatusColor = "danger";
  else if (tokenPercentage > 40) tokenStatusColor = "warning";

  return (
    <div className="app-layout">
      {/* Left Sidebar: Controls & Dashboard */}
      <aside className="sidebar-container">
        <header className="app-header">
          <div className="header-brand">
            <h1>Agent Harness Studio</h1>
            <p className="subtitle">Hermes Local Workspace</p>

            {/* Token Estimator Gauge */}
            <div className="token-estimator-compact">
              <div className="token-gauge-header">
                <span className="token-label">Harness Payload</span>
                <span className={`token-percentage-badge ${tokenStatusColor}`}>
                  {estimatedTotalTokens.toLocaleString()} / {MAX_CONTEXT_TOKENS.toLocaleString()} tokens ({tokenPercentage.toFixed(1)}%)
                </span>
              </div>
              <div className="token-progress-track">
                <div className={`token-progress-bar ${tokenStatusColor}`} style={{ width: `${Math.min(100, tokenPercentage)}%` }} />
              </div>
            </div>
          </div>
          {envInfo && (
            <div className="env-info">
              {envInfo.is_readonly && (
                <span className="env-badge readonly" title="HARNESS_READONLY=1: 쓰기 비활성화">🔒 READ-ONLY</span>
              )}
              <span className={`env-badge ${envInfo.is_sandbox ? 'sandbox' : 'real'}`}>
                {envInfo.is_sandbox ? '🛠️ SANDBOX' : '⚠️ REAL'}
              </span>
              {envInfo.is_git_repo ? (
                <span className="env-badge git" title={`${envInfo.git_commit_count}개 커밋`}>
                  git:{envInfo.git_branch} ({envInfo.git_commit_count})
                </span>
              ) : !envInfo.is_readonly && (
                <button className="git-init-btn" onClick={handleGitInit} title="HERMES_HOME을 git repo로 초기화">
                  + Git 연동
                </button>
              )}
              <span className="env-path" title={envInfo.hermes_home}>
                {envInfo.hermes_home.slice(-20)}
              </span>
            </div>
          )}
        </header>

        <section className="harness-overview">
          <div className="hero-compact">
            <h2>Harness over Model</h2>
          </div>

          <div className="cards-grid">
            {sections.map((sec) => {
              const configTypes = ["Memory Config", "Root Context", "MCP Server"];
              const count = sec.id === 'config'
                ? items.filter(i => configTypes.includes(i.type)).length
                : sec.id === 'audit'
                ? auditLogs.length
                : summary?.[sec.id] || 0;
              return (
                <div
                  key={sec.id}
                  className={`card ${selectedSection === sec.id ? "active" : ""}`}
                  onClick={() => handleSectionClick(sec.id)}
                >
                  <span className="card-icon">{sec.icon}</span>
                  <span className="card-title">{sec.title}</span>
                  <span className="card-count">{count}</span>
                </div>
              );
            })}
          </div>
        </section>

        <main className="content-area">
          {loading && <div className="panel-loading-strip">Refreshing harness inventory...</div>}
          {error && <div className="error-banner">{error}</div>}

          {selectedSection && !editingItem && (
            <div className="detail-panel">
              <div className="panel-header">
                <h3>{sections.find(s => s.id === selectedSection)?.title} Details</h3>
                <button onClick={() => setSelectedSection(null)}>×</button>
              </div>
              <div className="panel-content">
                {selectedSection === "web" && (
                  <div className="web-harness">
                    <div className="web-input-active">
                       <input
                         type="url"
                         placeholder="URL to scrape..."
                         value={webUrl}
                         onChange={(e) => setWebUrl(e.target.value)}
                         onKeyDown={(e) => e.key === 'Enter' && handleScrape()}
                         disabled={scrapeLoading}
                       />
                       <button onClick={handleScrape} disabled={scrapeLoading || !webUrl.trim()}>
                         {scrapeLoading ? "Scraping…" : "Scrape"}
                       </button>
                    </div>
                    {scrapeError && <p className="web-error">{scrapeError}</p>}
                    <ScrapingPipeline result={scrapeResult} />
                  </div>
                )}

                {/* Memory Map Custom Layout */}
                {selectedSection === "memory" && (
                  <div className="memory-map-container">
                    {memoryConflicts.length > 0 && (
                      <div className="conflict-warnings-container">
                        {memoryConflicts.map((c, idx) => (
                          <div key={idx} className="conflict-card">
                            <span className="conflict-icon">⚠️</span>
                            <div>
                              <strong>Memory Conflict Detected:</strong> {c.message}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="memory-map-grid">
                      <div className="memory-section-card">
                        <div className="memory-card-title-bar">
                          <span>⚙️</span>
                          <span className="memory-card-title">Core Config Memories</span>
                        </div>
                        <p className="memory-card-desc">Active key-value characteristics defined in config.yaml:</p>
                        <div className="memory-chips-container">
                          {(() => {
                            const configMem = items.find(i => i.type === "Memory Config")?.metadata || {};
                            const keys = Object.keys(configMem);
                            return keys.length === 0 ? (
                              <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>No keys defined</span>
                            ) : (
                              keys.map(k => (
                                <span key={k} className="memory-chip-item" title={`${k}: ${JSON.stringify(configMem[k])}`}>
                                  {k}
                                </span>
                              ))
                            );
                          })()}
                        </div>
                        <div style={{ marginTop: '12px' }}>
                          <button
                            className="edit-btn"
                            onClick={() => {
                              const configItem = items.find(i => i.type === "Memory Config");
                              if (configItem) handleEditClick(configItem);
                            }}
                          >
                            Edit Config
                          </button>
                        </div>
                      </div>

                      <div className="memory-section-card">
                        <div className="memory-card-title-bar">
                          <span>📖</span>
                          <span className="memory-card-title">Memory Manifest</span>
                        </div>
                        <p className="memory-card-desc">Pointer index describing global memory locations (memory_manifest.md):</p>
                        {(() => {
                          const manifest = items.find(i => i.type === "Memory Manifest");
                          return manifest ? (
                            <div>
                              <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                                File: memory_manifest.md ({manifest.metadata?.size_bytes} bytes)
                              </div>
                              <button className="edit-btn" onClick={() => handleEditClick(manifest)}>Edit Manifest</button>
                            </div>
                          ) : (
                            <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>Not initialized</span>
                          );
                        })()}
                      </div>

                      <div className="memory-section-card" style={{ gridColumn: 'span 2' }}>
                        <div className="memory-card-title-bar">
                          <span>📂</span>
                          <span className="memory-card-title">Agent Memories Directory</span>
                        </div>
                        <p className="memory-card-desc">Scanned Markdown memory files under memories/ directory:</p>
                        {(() => {
                          const memDir = items.find(i => i.type === "Memory Directory");
                          const files = memDir?.metadata?.md_files || [];
                          return files.length === 0 ? (
                            <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>No memory files found</span>
                          ) : (
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                              {files.map((fname) => (
                                <div key={fname} className="memory-file-row" style={{ background: 'rgba(255,255,255,0.02)', padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <span className="memory-file-name" style={{ flex: 1 }}>{fname}</span>
                                  <button
                                    className="edit-btn"
                                    style={{ margin: 0 }}
                                    onClick={() => handleEditClick({
                                      name: fname.replace(/\.md$/, ''),
                                      source_path: `${memDir.source_path}/${fname}`,
                                      type: "Memory File",
                                      state: "ACTIVE",
                                      summary: "",
                                    })}
                                  >
                                    Edit File
                                  </button>
                                </div>
                              ))}
                            </div>
                          );
                        })()}
                      </div>

                      <div className="memory-section-card" style={{ gridColumn: 'span 2' }}>
                        <div className="memory-card-title-bar">
                          <span>🧠</span>
                          <span className="memory-card-title">Runtime State Persistence</span>
                        </div>
                        <p className="memory-card-desc">Active session memory and state files under state/ directory:</p>
                        {(() => {
                          const stateItem = items.find(i => i.type === "Memory State");
                          const files = stateItem?.metadata?.files || [];
                          return files.length === 0 ? (
                            <span style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>No persistent state files</span>
                          ) : (
                            <div className="memory-chips-container">
                              {files.map(f => (
                                <span key={f} className="memory-chip-item" style={{ background: 'rgba(100,100,255,0.05)', borderColor: 'rgba(100,100,255,0.15)' }}>
                                  {f}
                                </span>
                              ))}
                            </div>
                          );
                        })()}
                      </div>
                    </div>
                  </div>
                )}

                {/* SQLite Audit Logs Custom Layout */}
                {selectedSection === "audit" && (
                  <div className="audit-timeline-container">
                    <div className="audit-timeline-header">
                      <h4>System Change Log (SQLite)</h4>
                      <button onClick={fetchAuditLogs} className="refresh-btn">🔄 Refresh</button>
                    </div>
                    {auditLoading ? (
                      <div className="editor-loading">Loading audit records...</div>
                    ) : auditLogs.length === 0 ? (
                      <div className="chat-empty">No edits recorded yet in harness_studio.db.</div>
                    ) : (
                      <div className="audit-timeline">
                        {auditLogs.map((log) => (
                          <div key={log.id} className="timeline-node">
                            <div className="node-marker" />
                            <div className="node-content">
                              <div className="node-header">
                                <span className={`action-badge ${log.action.toLowerCase()}`}>{log.action}</span>
                                <span className="node-date">{new Date(log.created_at).toLocaleString()}</span>
                              </div>
                              <div className="node-path">{log.target_path}</div>
                              {log.details && <div className="node-details">{log.details}</div>}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {selectedSection !== "memory" && selectedSection !== "audit" && getFilteredItems().map((item, idx) => (
                  <div key={idx} className="item-row">
                    <div className="item-main">
                      <strong>{item.name}</strong>
                      <span className="item-type">{item.type}</span>
                    </div>
                    <div className="item-summary">{item.summary}</div>
                    <div className={`item-state state-${item.state.toLowerCase()}`}>
                      {item.state}
                    </div>
                    {isEditable(item) ? (
                      <button className="edit-btn" onClick={() => handleEditClick(item)}>
                        {envInfo?.is_readonly ? "View" : "Edit"}
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          )}

          {editingItem && (
            <div className="editor-panel">
              <div className="panel-header">
                <h3>{editingItem.name}</h3>
                <div className="panel-actions">
                  <span className="save-status">{saveStatus}</span>
                  {lastCommit?.hash && (
                    <span className="commit-pill">Commit {lastCommit.hash}</span>
                  )}
                  {envInfo?.is_git_repo && (
                    <button
                      className={`history-btn ${showHistory ? "active" : ""}`}
                      onClick={() => { setShowHistory(v => !v); if (!showHistory) fetchGitLog(editingItem.source_path); }}
                    >
                      History {gitLog.length > 0 ? `(${gitLog.length})` : ""}
                    </button>
                  )}
                  {lastBackup && !envInfo?.is_git_repo && (
                    <button className="rollback-btn" onClick={() => handleRollback(editingItem.source_path)} title={`백업: ${lastBackup}`}>
                      Rollback
                    </button>
                  )}
                  <button onClick={handleSave} className="save-btn" disabled={editLoading || envInfo?.is_readonly}>
                    {envInfo?.is_readonly ? "Read-Only" : "Save"}
                  </button>
                  <button onClick={() => { setEditingItem(null); setLastBackup(null); setLastCommit(null); setShowHistory(false); }}>Cancel</button>
                </div>
              </div>

              {!envInfo?.is_readonly && (
                <div className="commit-msg-row">
                  <input
                    type="text"
                    className="commit-msg-input"
                    placeholder={`커밋 메시지 (비우면 자동: "harness-studio: edit ${editingItem.name}")`}
                    value={commitMsg}
                    onChange={e => setCommitMsg(e.target.value)}
                    disabled={editLoading}
                  />
                </div>
              )}

              {/* SOUL.md Presets Bar and Skill converter */}
              {(editingItem.name === "SOUL.md" || editingItem.type === "Skill") && (
                <div className="presets-container">
                  {editingItem.name === "SOUL.md" && (
                    <>
                      <span className="presets-label">Persona Presets:</span>
                      <div className="presets-buttons">
                        <button className="preset-badge-btn" onClick={() => applySoulPreset("developer")}>💻 Developer</button>
                        <button className="preset-badge-btn" onClick={() => applySoulPreset("researcher")}>🔬 Researcher</button>
                        <button className="preset-badge-btn" onClick={() => applySoulPreset("writer")}>✍️ Creative Writer</button>
                      </div>
                    </>
                  )}
                  {editingItem.type === "Skill" && (
                    <>
                      <span className="presets-label">Metadata Schema Converter:</span>
                      <div className="presets-buttons">
                        <button className="preset-badge-btn" onClick={() => handleConvertSkill("hermes")} title="Convert frontmatter to Hermes metadata format">To Hermes format</button>
                        <button className="preset-badge-btn" onClick={() => handleConvertSkill("claude")} title="Convert frontmatter to Claude Code format">To Claude format</button>
                      </div>
                    </>
                  )}
                </div>
              )}

              <div className="editor-body">
                {editLoading
                  ? <div className="editor-loading">Loading file content...</div>
                  : <textarea
                      className="code-editor"
                      value={editContent}
                      onChange={(e) => setEditContent(e.target.value)}
                      readOnly={envInfo?.is_readonly}
                    />
                }

                {showHistory && gitLog.length > 0 && (
                  <div className="git-history-panel">
                    <div className="git-history-header">변경 이력</div>
                    {gitLog.map(c => (
                      <div key={c.hash} className="git-commit-row">
                        <span className="git-hash">{c.short_hash}</span>
                        <span className="git-msg">{c.message}</span>
                        <span className="git-date">{c.date.slice(0, 10)}</span>
                        {!envInfo?.is_readonly && (
                          <button
                            className="git-restore-btn"
                            onClick={() => handleGitRollback(editingItem.source_path, c.hash, c.short_hash)}
                          >
                            복원
                          </button>
                        )}
                      </div>
                    ))}
                    {gitLog.length === 0 && <div className="git-empty">커밋 이력 없음</div>}
                  </div>
                )}
              </div>
            </div>
          )}

          {!selectedSection && !editingItem && (
            <div className="welcome-placeholder">
              <p>Select a category to inspect or edit your agent harness.</p>
            </div>
          )}
        </main>
      </aside>

      {/* Right Column: Chat Molder Interface */}
      <section className="chat-container">
        <header className="chat-header">
          <h3>✨ Chat Molder</h3>
          <p>Skill & Memory Generation</p>
        </header>

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
                  <MarkdownContent text={msg.text} />
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
               <div className="bubble-content loading-dots">Thinking...</div>
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
            <button onClick={handleMold} disabled={!prompt.trim() || molderResponse?.status === "loading"}>Send</button>
          </div>
        </footer>
      </section>
    </div>
  );
}

export default App;
