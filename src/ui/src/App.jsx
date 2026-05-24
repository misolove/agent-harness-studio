import { useState, useEffect } from "react";
import "./App.css";

// Basic styling matches the "Agent Harness" vibe (dark theme, deep purples/blues)
function App() {
  const [summary, setSummary] = useState(null);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedSection, setSelectedSection] = useState(null);

  useEffect(() => {
    fetch("http://127.0.0.1:8765/api/scan")
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
  }, []);

  const sections = [
    { id: "memory", title: "Memory", icon: "🧠" },
    { id: "skills", title: "Skills", icon: "🛠️" },
    { id: "hooks", title: "Hooks", icon: "🪝" },
    { id: "mcp", title: "MCP", icon: "🔌" },
    { id: "context", title: "Context", icon: "📜" },
    { id: "config", title: "Config", icon: "⚙️" },
  ];

  const getFilteredItems = () => {
    if (!selectedSection) return [];
    
    // In a real app we'd fetch from /api/scan/{section} or filter client-side better.
    // For prototype, client-side filter is fine.
    const map = {
      skills: ["Skill"],
      memory: ["Memory Config", "Memory Manifest", "Memory Directory", "Memory State"],
      mcp: ["MCP Server"],
      context: ["Root Context"],
      hooks: ["Hook"],
      config: ["Memory Config", "Root Context", "MCP Server"],
    };
    
    const allowed = map[selectedSection] || [];
    return items.filter(i => allowed.includes(i.type));
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Agent Harness Studio</h1>
        <p className="subtitle">Hermes Local Workspace</p>
      </header>

      {error && <div className="error-banner">Connection Error: {error}</div>}
      {loading && <div className="loading">Scanning harness...</div>}

      {!loading && !error && (
        <main className="dashboard">
          <div className="cards-grid">
            {sections.map((sec) => {
              const count = summary?.[sec.id] || 0;
              // Determine status simply based on count for prototype
              const statusClass = count > 0 ? "status-ok" : "status-warn";
              
              return (
                <div 
                  key={sec.id} 
                  className={`card ${selectedSection === sec.id ? "active" : ""}`}
                  onClick={() => setSelectedSection(sec.id)}
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

          {selectedSection && (
            <div className="detail-panel">
              <div className="panel-header">
                <h3>{sections.find(s => s.id === selectedSection)?.title} Details</h3>
                <button onClick={() => setSelectedSection(null)}>Close</button>
              </div>
              <div className="panel-content">
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
                  </div>
                ))}
                {getFilteredItems().length === 0 && (
                  <p className="empty-state">No items found in this section.</p>
                )}
              </div>
            </div>
          )}
        </main>
      )}

      {/* Chat Molder UI (Mock) */}
      <footer className="chat-molder">
        <div className="chat-input-wrapper">
          <span className="chat-icon">✨</span>
          <input 
            type="text" 
            placeholder="Describe an agent skill or memory to generate..." 
            disabled 
          />
          <button disabled>Generate</button>
        </div>
      </footer>
    </div>
  );
}

export default App;
