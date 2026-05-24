import { useState, useEffect } from "react";
import "./App.css";

function App() {
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSection, setSelectedSection] = useState(null);
  const [editingItem, setEditingItem] = useState(null);
  const [editContent, setEditContent] = useState("");
  const [saveStatus, setSaveStatus] = useState("");

  const [prompt, setPrompt] = useState("");
  const [molderResponse, setMolderResponse] = useState(null);
  const [envInfo, setEnvInfo] = useState(null);

  const API_BASE = "http://127.0.0.1:8766";

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

  useEffect(() => {
    fetchEnv();
    fetchHarness();
  }, []);

  const sections = [
    { id: "memory", title: "Memory", icon: "🧠" },
    { id: "skills", title: "Skills", icon: "🛠️" },
    { id: "hooks", title: "Hooks", icon: "🪝" },
    { id: "mcp", title: "MCP", icon: "🔌" },
    { id: "context", title: "Context", icon: "📜" },
    { id: "config", title: "Config", icon: "⚙️" },
    { id: "web", title: "Web Context", icon: "🌐" },
  ];

  const getFilteredItems = () => {
    if (!selectedSection) return [];
    const map = {
      skills: ["Skill"],
      memory: ["Memory Config", "Memory Manifest", "Memory Directory", "Memory State"],
      mcp: ["MCP Server"],
      context: ["Root Context"],
      hooks: ["Hook"],
      config: ["Memory Config", "Root Context", "MCP Server"],
      web: [], // Placeholder for Web Sources
    };
    const allowed = map[selectedSection] || [];
    return items.filter(i => allowed.includes(i.type));
  };

  const handleEditClick = (item) => {
    setEditingItem(item);
    // In a real app we would GET the file content.
    // For this prototype, we just mock the initial content based on metadata.
    setEditContent(`---\nname: ${item.name}\ndescription: ${item.summary}\n---\n\n# Details\nEditing ${item.source_path}`);
    setSaveStatus("");
  };

  const handleSave = () => {
    setSaveStatus("Saving...");
    fetch(`${API_BASE}/api/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: editingItem.source_path, content: editContent })
    })
      .then(res => res.json())
      .then(data => {
        setSaveStatus("Saved successfully!");
        setTimeout(() => {
          setEditingItem(null);
          fetchHarness();
        }, 1000);
      })
      .catch(err => {
        console.error(err);
        setSaveStatus("Error saving.");
      });
  };

  const handleMold = () => {
    if (!prompt.trim()) return;
    setMolderResponse({ status: "loading" });
    fetch(`${API_BASE}/api/mold`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt })
    })
      .then(res => res.json())
      .then(data => {
        setMolderResponse(data);
        setPrompt("");
      })
      .catch(err => {
        setMolderResponse({ status: "error", message: err.message });
      });
  };

  const handleApply = () => {
    if (!molderResponse || !molderResponse.content) return;
    
    // Determine path based on action
    const home = envInfo?.hermes_home || "/Users/letitbe/.hermes";
    let path = "";
    if (molderResponse.action.includes("SKILL")) {
      path = `${home}/skills/${molderResponse.name}/SKILL.md`;
    } else {
      path = `${home}/temp_proposal.md`;
    }

    setSaveStatus("Applying...");
    fetch(`${API_BASE}/api/save`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: path, content: molderResponse.content })
    })
      .then(res => res.json())
      .then(data => {
        setSaveStatus("Applied successfully!");
        setMolderResponse(null);
        fetchHarness();
      })
      .catch(err => {
        console.error(err);
        setSaveStatus("Error applying.");
      });
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-left">
          <h1>Agent Harness Studio</h1>
          <p className="subtitle">Hermes Local Workspace Control Tower</p>
        </div>
        {envInfo && (
          <div className="header-right">
            <span className={`env-badge ${envInfo.is_sandbox ? 'sandbox' : 'real'}`}>
              {envInfo.is_sandbox ? '🛠️ SANDBOX MODE' : '⚠️ REAL HERMES MODE'}
            </span>
            <span className="env-path" title={envInfo.hermes_home}>
              {envInfo.hermes_home.length > 30 ? '...' + envInfo.hermes_home.slice(-30) : envInfo.hermes_home}
            </span>
          </div>
        )}
      </header>

      {/* Hero / Intro Section */}
      {!selectedSection && !editingItem && !molderResponse && (
        <section className="hero-section">
          <div className="hero-content">
            <h2>Harness over Model</h2>
            <p>Visualize and refine your AI agent's environment systematically.</p>
          </div>
          <div className="hero-visual">
             <img src="/docs/assets/architecture.svg" alt="Architecture Diagram" className="architecture-svg" />
          </div>
        </section>
      )}

      {error && <div className="error-banner">Connection Error: {error}</div>}
      {loading && <div className="loading">Scanning harness...</div>}

      {!loading && !error && (
        <main className="dashboard">
          <div className="cards-grid">
            {sections.map((sec) => {
              const count = summary?.[sec.id] || 0;
              const statusClass = count > 0 ? "status-ok" : "status-warn";
              return (
                <div 
                  key={sec.id} 
                  className={`card ${selectedSection === sec.id ? "active" : ""}`}
                  onClick={() => { setSelectedSection(sec.id); setEditingItem(null); }}
                >
                  <div className="card-header">
                    <span className="icon">{sec.icon}</span>
                    <h2>{sec.title}</h2>
                  </div>
                  <div className="card-body">
                    <div className="stat">{count}</div>
                    <div className="label">Items Detected</div>
                  </div>
                  <div className={`card-status ${statusClass}`}>
                    {count > 0 ? "● OK" : "○ Empty"}
                  </div>
                </div>
              );
            })}
          </div>

          {selectedSection && !editingItem && (
            <div className="detail-panel">
              <div className="panel-header">
                <h3>{sections.find(s => s.id === selectedSection)?.title} Details</h3>
                <button onClick={() => setSelectedSection(null)}>Close</button>
              </div>
              <div className="panel-content">
                {selectedSection === "web" && (
                  <div className="web-harness-placeholder">
                    <p>Web Context Harness powered by <strong>Firecrawl</strong></p>
                    <div className="web-input-mock">
                       <input type="text" placeholder="Enter URL to index..." disabled />
                       <button disabled>Index</button>
                    </div>
                    <p className="hint">This feature requires a Firecrawl API key. Integration is in progress.</p>
                  </div>
                )}
                {getFilteredItems().map((item, idx) => (
                  <div key={idx} className="item-row">
                    <div className="item-main">
                      <strong>{item.name}</strong>
                      <span className="item-type">{item.type}</span>
                    </div>
                    <div className="item-summary">{item.summary}</div>
                    <div className={`item-state state-${item.state.toLowerCase()}`}>
                      {item.state}
                    </div>
                    {item.type === "Skill" && (
                       <button className="edit-btn" onClick={() => handleEditClick(item)}>Edit</button>
                    )}
                  </div>
                ))}
                {getFilteredItems().length === 0 && (
                  <p className="empty-state">No items found in this section.</p>
                )}
              </div>
            </div>
          )}

          {editingItem && (
            <div className="editor-panel">
               <div className="panel-header">
                <h3>Editing: {editingItem.name}</h3>
                <div>
                   <span className="save-status">{saveStatus}</span>
                   <button onClick={handleSave} className="save-btn">Save</button>
                   <button onClick={() => setEditingItem(null)}>Cancel</button>
                </div>
              </div>
              <textarea 
                className="code-editor"
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
              />
            </div>
          )}

          {/* Molder Output Preview */}
          {molderResponse && (
            <div className="molder-preview">
              <div className="panel-header">
                <h3>Chat Molder Proposal</h3>
                <button onClick={() => setMolderResponse(null)}>Dismiss</button>
              </div>
              {molderResponse.status === "loading" ? (
                <p>Molding harness...</p>
              ) : (
                <div>
                  <p><strong>Action:</strong> {molderResponse.action} ({molderResponse.name})</p>
                  <p>{molderResponse.message}</p>
                  <pre className="diff-viewer">{molderResponse.diff}</pre>
                  <button className="apply-btn" onClick={handleApply}>Apply Changes</button>
                </div>
              )}
            </div>
          )}
        </main>
      )}

      {/* Chat Molder UI */}
      <footer className="chat-molder">
        <div className="chat-input-wrapper">
          <span className="chat-icon">✨</span>
          <input 
            type="text" 
            placeholder="Describe an agent skill or memory to generate..." 
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleMold()}
          />
          <button onClick={handleMold}>Mold</button>
        </div>
      </footer>
    </div>
  );
}

export default App;
