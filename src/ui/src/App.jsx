import React, { useState, useEffect, useRef, useCallback } from "react";
import EditorModule from 'react-simple-code-editor';
const Editor = EditorModule.default || EditorModule;
import Prism from 'prismjs';
import 'prismjs/components/prism-markup';
import 'prismjs/components/prism-yaml';
import 'prismjs/components/prism-markdown';
import 'prismjs/components/prism-json';
import 'prismjs/components/prism-toml';
import 'prismjs/components/prism-javascript';
import 'prismjs/components/prism-typescript';
import 'prismjs/components/prism-bash';
import 'prismjs/themes/prism-tomorrow.css';
import "./App.css";
import ScrapingPipeline from "./ScrapingPipeline.jsx";

const LLM_PROVIDER_PRESETS = [
  { provider: "9router", base_url: "http://127.0.0.1:20128/v1", model: "letitbe" },
  { provider: "OpenAI", base_url: "", model: "gpt-4o" },
  { provider: "OpenAI Compatible", base_url: "http://127.0.0.1:11434/v1", model: "llama3.1" },
  { provider: "Custom", base_url: "", model: "" },
];

class EditorErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error("Editor Error:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: "20px", background: "#fee", color: "#c00", borderRadius: "8px" }}>
          <h4>Editor crashed!</h4>
          <pre style={{ whiteSpace: "pre-wrap", fontSize: "12px" }}>{this.state.error?.toString()}</pre>
          <button onClick={() => this.setState({ hasError: false })} style={{ marginTop: "10px" }}>Retry</button>
        </div>
      );
    }
    return this.props.children;
  }
}



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

function formatSessionDate(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number") {
    const millis = value > 1000000000000 ? value : value * 1000;
    const date = new Date(millis);
    return Number.isNaN(date.getTime()) ? String(value) : date.toISOString().slice(0, 10);
  }
  const text = String(value);
  const numeric = Number(text);
  if (!Number.isNaN(numeric) && text.trim() !== "") {
    return formatSessionDate(numeric);
  }
  return text.slice(0, 10);
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
  const [llmProvider, setLlmProvider] = useState(null);
  const [showLlmSettings, setShowLlmSettings] = useState(false);
  const [llmDraft, setLlmDraft] = useState({ provider: "", base_url: "", model: "", api_key: "" });
  const [llmStatus, setLlmStatus] = useState("");

  // Web scraping state
  const [webUrl, setWebUrl] = useState("");
  const [scrapeResult, setScrapeResult] = useState(null);
  const [scrapeLoading, setScrapeLoading] = useState(false);
  const [scrapeError, setScrapeError] = useState(null);

  // Audit Logs state
  const [auditLogs, setAuditLogs] = useState([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [diffAudit, setDiffAudit] = useState(null);
  const [diffAuditLoading, setDiffAuditLoading] = useState(false);
  const [workspaces, setWorkspaces] = useState([]);
  const [activeWorkspace, setActiveWorkspace] = useState("");
  const [expandedRows, setExpandedRows] = useState(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [sortKey, setSortKey] = useState("name-asc");
  const [selectedSessionId, setSelectedSessionId] = useState(null);
  const [sessionMessages, setSessionMessages] = useState(null);
  const [sessionMsgLoading, setSessionMsgLoading] = useState(false);
  const [isDarkMode, setIsDarkMode] = useState(() => localStorage.getItem('theme') !== 'light');
  const [collapsedCategories, setCollapsedCategories] = useState(new Set());
  const [allSessions, setAllSessions] = useState(null);
  const [allSessionsLoading, setAllSessionsLoading] = useState(false);
  const [agentRunners, setAgentRunners] = useState([]);
  const [agentRunnersLoading, setAgentRunnersLoading] = useState(false);
  const [piPreview, setPiPreview] = useState(null);
  const [piPreviewPrompt, setPiPreviewPrompt] = useState("Summarize this repository and list the safest verification commands.");
  const [piRunPrompt, setPiRunPrompt] = useState("List all Python files in src/ and summarize their purpose.");
  const [piRunId, setPiRunId] = useState(null);
  const [piRunMeta, setPiRunMeta] = useState(null);
  const [piRunLog, setPiRunLog] = useState("");
  const [piRunPolling, setPiRunPolling] = useState(false);
  const [piMode, setPiMode] = useState(false);
  const [piMoldRunId, setPiMoldRunId] = useState(null);
  const [piMoldPolling, setPiMoldPolling] = useState(false);
  const [piMoldSessionFile, setPiMoldSessionFile] = useState(null);
  const [showPayloadDetail, setShowPayloadDetail] = useState(false);
  const [showDietModal, setShowDietModal] = useState(false);
  const [dietTab, setDietTab] = useState('all');
  const [recommendations, setRecommendations] = useState([]);
  const [recLoading, setRecLoading] = useState(false);
  const [recError, setRecError] = useState('');
  const [archiveConfirm, setArchiveConfirm] = useState(null);
  const [copyModal, setCopyModal] = useState(null);
  const [copyTargetWorkspace, setCopyTargetWorkspace] = useState('');
  const [copyTargetSubdir, setCopyTargetSubdir] = useState('');
  const [actionStatus, setActionStatus] = useState(null);
  const [workspaceList, setWorkspaceList] = useState([]);

  const API_BASE = "";
  const chatMessagesRef = useRef(null);
  const [chatWidth, setChatWidth] = useState(null); // null = CSS default (45%)
  const resizingRef = useRef(false);
  const resizeStartXRef = useRef(0);
  const resizeStartWidthRef = useRef(0);

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

  const canInjectToHermes = (item) => (
    item?.type === "Skill" &&
    Boolean(item?.source_path) &&
    (activeWorkspace?.endsWith("/.claude") || item.source_path.includes("/.claude/") || item.source_path.includes("/.agents/skills/"))
  );

  const handleInjectSkillToHermes = (item, overwrite = false) => {
    if (!item?.source_path) return;
    const hermesWorkspace = workspaces.find(ws => ws.id === "hermes")?.path || envInfo?.hermes_home;
    if (!hermesWorkspace) {
      setActionStatus({ type: "error", msg: "Hermes workspace를 찾지 못했습니다." });
      return;
    }
    setActionStatus({ type: "success", msg: `Hermes 주입 준비 중: ${item.name}` });
    fetch(`${API_BASE}/api/convert/skill/inject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source_path: item.source_path,
        source_workspace: activeWorkspace,
        target_workspace: hermesWorkspace,
        source_agent: "claude-code",
        overwrite,
      })
    })
      .then(async res => {
        const data = await res.json();
        if (res.status === 409 && !overwrite) {
          const detail = data.detail || {};
          const ok = window.confirm(`${detail.skill_name || item.name} Hermes skill이 이미 있습니다.\n덮어쓸까요?\n${detail.path || ""}`);
          if (ok) return handleInjectSkillToHermes(item, true);
          throw new Error("사용자가 overwrite를 취소했습니다.");
        }
        if (!res.ok) throw new Error(data.detail?.message || data.detail || `HTTP ${res.status}`);
        return data;
      })
      .then(data => {
        if (!data) return;
        setActionStatus({ type: "success", msg: `Hermes 주입 완료: ${data.skill_name}` });
        if (activeWorkspace === hermesWorkspace) fetchHarness();
      })
      .catch(err => {
        setActionStatus({ type: "error", msg: `Hermes 주입 실패: ${err.message}` });
      })
      .finally(() => setTimeout(() => setActionStatus(null), 5000));
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

  const fetchDiffAudit = (wsPath = activeWorkspace) => {
    setDiffAuditLoading(true);
    setDiffAudit(null);
    const url = `${API_BASE}/api/git/audit${wsPath ? '?workspace=' + encodeURIComponent(wsPath) : ''}`;
    fetch(url)
      .then(r => r.json())
      .then(data => { setDiffAudit(data); setDiffAuditLoading(false); })
      .catch(err => { setDiffAudit({ error: err.message }); setDiffAuditLoading(false); });
  };

  const fetchAgentRunners = (wsPath = activeWorkspace) => {
    setAgentRunnersLoading(true);
    const url = `${API_BASE}/api/agent-runners${wsPath ? '?workspace=' + encodeURIComponent(wsPath) : ''}`;
    fetch(url)
      .then(r => r.json())
      .then(data => {
        setAgentRunners(data.runners || []);
        setAgentRunnersLoading(false);
      })
      .catch(err => {
        setAgentRunners([{ id: "error", name: "Agent Runner", state: "ERROR", error: err.message }]);
        setAgentRunnersLoading(false);
      });
  };

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

  const handleMoldWithPi = () => {
    if (!prompt.trim() || piMoldPolling) return;
    const userMsg = { role: "user", text: prompt };
    setChatHistory(prev => [...prev, userMsg]);
    setPrompt("");
    setMolderResponse({ status: "loading", piMode: true });

    const selectedTitle = selectedSection
      ? sections.find(s => s.id === selectedSection)?.title || ""
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

  // ─── Resize Chat Panel ───
  const handleResizeStart = useCallback((e) => {
    e.preventDefault();
    resizingRef.current = true;
    resizeStartXRef.current = e.clientX;
    const chatEl = document.querySelector('.chat-container');
    resizeStartWidthRef.current = chatEl
      ? chatEl.getBoundingClientRect().width
      : window.innerWidth * 0.45;

    const onMouseMove = (ev) => {
      if (!resizingRef.current) return;
      const dx = resizeStartXRef.current - ev.clientX; // drag left → wider
      const newWidth = Math.max(240, Math.min(window.innerWidth * 0.75,
        resizeStartWidthRef.current + dx));
      setChatWidth(newWidth);
    };
    const onMouseUp = () => {
      resizingRef.current = false;
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
    };
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
  }, []);

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
          // Extract file paths Pi mentioned (for "Studio에서 열기" links)
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [piMoldPolling, piMoldRunId]);

  // polling effect for Pi runs
  const piRunPollingRef = React.useRef(null);
  React.useEffect(() => {
    if (piRunPolling && piRunId) {
      piRunPollingRef.current = setInterval(() => fetchPiRunLog(piRunId), 2000);
    } else {
      clearInterval(piRunPollingRef.current);
    }
    return () => clearInterval(piRunPollingRef.current);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [piRunPolling, piRunId]);

  const handleSectionClick = (sectionId) => {
    setSelectedSection(sectionId);
    setEditingItem(null);
    setSearchQuery("");
    setSortKey(sectionId === "logs" ? "modified-desc" : "name-asc");
    setSelectedSessionId(null);
    setSessionMessages(null);
    setExpandedRows(new Set());
    setAllSessions(null);
    setCollapsedCategories(new Set());
    if (sectionId === "audit") fetchAuditLogs();
    if (sectionId === "diff-audit") fetchDiffAudit();
    if (sectionId === "agent-runners") fetchAgentRunners();
  };

  const fetchSessionMessages = async (sessionId) => {
    setSelectedSessionId(sessionId);
    setSessionMsgLoading(true);
    setSessionMessages(null);
    try {
      const res = await fetch(`${API_BASE}/api/sessions/messages?session_id=${encodeURIComponent(sessionId)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSessionMessages(data);
    } catch (err) {
      setSessionMessages({ error: err.message });
    } finally {
      setSessionMsgLoading(false);
    }
  };

  const fetchAllSessions = async () => {
    setAllSessionsLoading(true);
    try {
      const ws = activeWorkspace ? `&workspace=${encodeURIComponent(activeWorkspace)}` : '';
      const res = await fetch(`${API_BASE}/api/sessions/list?limit=50${ws}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setAllSessions(data.sessions || []);
    } catch {
      setAllSessions([]);
    } finally {
      setAllSessionsLoading(false);
    }
  };

  const getSearchFiltered = (items) => {
    if (!searchQuery.trim()) return items;
    const q = searchQuery.toLowerCase();
    return items.filter(item =>
      item.name?.toLowerCase().includes(q) ||
      item.summary?.toLowerCase().includes(q) ||
      item.type?.toLowerCase().includes(q)
    );
  };

  const getItemModifiedAt = (item) => {
    const value = item?.metadata?.modified_at ?? item?.metadata?.mtime ?? item?.metadata?.updated_at;
    if (typeof value === "number") return value;
    if (typeof value === "string") {
      const parsed = Date.parse(value);
      return Number.isNaN(parsed) ? 0 : parsed / 1000;
    }
    return 0;
  };

  const compareText = (a = "", b = "") => String(a).localeCompare(String(b), undefined, { sensitivity: "base", numeric: true });
  const compareState = (a = "", b = "") => {
    const order = { ERROR: 0, ACTIVE: 1, READY: 1, INACTIVE: 2, PAUSED: 3, MISSING: 4 };
    const av = order[String(a).toUpperCase()] ?? 9;
    const bv = order[String(b).toUpperCase()] ?? 9;
    return av - bv || compareText(a, b);
  };

  const compareItems = (a, b, key = sortKey) => {
    if (key === "name-desc") return compareText(b.name, a.name);
    if (key === "modified-desc") return (getItemModifiedAt(b) - getItemModifiedAt(a)) || compareText(a.name, b.name);
    if (key === "modified-asc") return (getItemModifiedAt(a) - getItemModifiedAt(b)) || compareText(a.name, b.name);
    if (key === "state") return compareState(a.state, b.state) || compareText(a.name, b.name);
    if (key === "type") return compareText(a.type, b.type) || compareText(a.name, b.name);
    return compareText(a.name, b.name);
  };

  const sortItems = (list, key = sortKey) => {
    const sorted = [...list];
    sorted.sort((a, b) => compareItems(a, b, key));
    return sorted;
  };

  const getFilteredSortedItems = () => sortItems(getSearchFiltered(getFilteredItems()));

  const sortSkillCategories = (categories, groupedItems) => {
    const sorted = [...categories];
    if (sortKey === "name-desc") return sorted.sort((a, b) => compareText(b, a));
    if (sortKey === "modified-desc") {
      return sorted.sort((a, b) => Math.max(...groupedItems[b].map(getItemModifiedAt)) - Math.max(...groupedItems[a].map(getItemModifiedAt)) || compareText(a, b));
    }
    if (sortKey === "modified-asc") {
      return sorted.sort((a, b) => Math.min(...groupedItems[a].map(getItemModifiedAt)) - Math.min(...groupedItems[b].map(getItemModifiedAt)) || compareText(a, b));
    }
    if (sortKey === "state") {
      return sorted.sort((a, b) => compareState(groupedItems[a][0]?.state, groupedItems[b][0]?.state) || compareText(a, b));
    }
    return sorted.sort((a, b) => compareText(a, b));
  };

  const isEditable = (item) => {
    if (!item || !item.source_path) return false;
    if (item.metadata?.is_directory) return false;
    if (item.metadata?.is_binary) return false;
    const filename = item.source_path.split('/').pop() || "";
    const ext = filename.includes('.') ? filename.split('.').pop().toLowerCase() : "";
    return [
      "md",
      "mdc",
      "yaml",
      "yml",
      "json",
      "jsonl",
      "ndjson",
      "log",
      "out",
      "err",
      "toml",
      "txt",
      "rules",
      "pbtxt",
      "py",
      "sh",
      "js",
      "mjs",
      "ts",
      "tsx",
      "jsx",
      "css",
      "html",
      "",
    ].includes(ext);
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

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', isDarkMode ? 'dark' : 'light');
    localStorage.setItem('theme', isDarkMode ? 'dark' : 'light');
  }, [isDarkMode]);

  useEffect(() => {
    if (!showDietModal || dietTab !== 'smart' || !activeWorkspace) return;

    setRecLoading(true);
    setRecError('');
    fetch(`${API_BASE}/api/recommendations?workspace=${encodeURIComponent(activeWorkspace)}&days=30`)
      .then((res) => {
        if (!res.ok) return res.json().then(e => { throw new Error(e.detail || `HTTP ${res.status}`); });
        return res.json();
      })
      .then((data) => {
        setRecommendations(data.recommendations || []);
        if (data.usage?.unsupported) {
          setRecError('이 워크스페이스는 아직 사용량 로그 파싱을 지원하지 않습니다.');
        }
      })
      .catch((err) => {
        setRecommendations([]);
        setRecError(err.message || '추천을 불러오지 못했습니다.');
      })
      .finally(() => setRecLoading(false));
  }, [showDietModal, dietTab, activeWorkspace]);

  const fetchEnv = (wsPath = activeWorkspace) => {
    fetch(`${API_BASE}/api/env${wsPath ? '?workspace=' + encodeURIComponent(wsPath) : ''}`)
      .then((res) => res.json())
      .then((data) => setEnvInfo(data))
      .catch((err) => {
        console.error("Failed to fetch env info", err);
        setError("Failed to connect to backend: " + err.message);
      });
  };

  const fetchLlmProvider = () => {
    fetch(`${API_BASE}/api/llm/provider`)
      .then((res) => res.json())
      .then((data) => {
        setLlmProvider(data);
        setLlmDraft({
          provider: data.provider || "",
          base_url: data.base_url || "",
          model: data.model || "",
          api_key: "",
        });
      })
      .catch((err) => {
        console.error("Failed to fetch LLM provider", err);
        setLlmStatus("LLM provider unavailable");
      });
  };

  const saveLlmProvider = () => {
    setLlmStatus("Saving...");
    fetch(`${API_BASE}/api/llm/provider`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(llmDraft),
    })
      .then((res) => {
        if (!res.ok) return res.json().then(e => { throw new Error(e.detail || res.status); });
        return res.json();
      })
      .then((data) => {
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
      .catch((err) => setLlmStatus(`Error: ${err.message}`));
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

  const fetchHarness = (wsPath = activeWorkspace) => {
    setLoading(true);
    fetch(`${API_BASE}/api/scan${wsPath ? '?workspace=' + encodeURIComponent(wsPath) : ''}`)
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
    fetch(`${API_BASE}/api/git/init`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: activeWorkspace })
    })
      .then(r => r.json())
      .then(() => fetchEnv())
      .catch(err => {
        console.error("Git init failed", err);
        setError("Git init failed: " + err.message);
      });
  };

  const handleWorkspaceChange = (e) => {
    const ws = e.target.value;
    setActiveWorkspace(ws);
    setEditingItem(null);
    setSelectedSection(null);
    fetchEnv(ws);
    fetchHarness(ws);
    fetchAgentRunners(ws);
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
    fetch(`${API_BASE}/api/workspaces`)
      .then(res => res.json())
      .then(data => {
        setWorkspaces(data);
        if (data.length > 0) {
          const defaultWs = data[0].path;
          setActiveWorkspace(defaultWs);
          fetchEnv(defaultWs);
          fetchHarness(defaultWs);
          fetchLlmProvider();
          fetchAgentRunners(defaultWs);
        }
      })
      .catch(err => console.error("Failed to load workspaces", err));
  }, []);

  // 탭 포커스 시 하네스 갱신 (자동 폴링 제거 — 수동 새로고침 버튼으로 대체)
  useEffect(() => {
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        fetchHarness();
        fetchAgentRunners();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => { document.removeEventListener("visibilitychange", onVisibility); };
  }, [activeWorkspace]);

  const handleManualRefresh = () => {
    fetchHarness();
    fetchAgentRunners();
  };

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
    { id: "logs", title: "Logs", icon: "🧾" },
    { id: "sessions", title: "Sessions", icon: "🗂️" },
    { id: "statedb", title: "State DB", icon: "🗄️" },
    { id: "checkpoints", title: "Checkpoints", icon: "🔖" },
    { id: "agent-runners", title: "Agent Runner", icon: "▶" },
    { id: "diff-audit", title: "Diff Audit", icon: "🔍" },
    { id: "audit", title: "Audit Log", icon: "📋" },
    { id: "web", title: "Web Context", icon: "🌐" },
  ];

  const getFilteredItems = () => {
    if (!selectedSection) return [];
    const map = {
      skills: ["Skill"],
      bundles: ["Skill Bundle", "Subagent"],
      memory: ["Memory Config", "Memory Manifest", "Memory Directory", "Memory State"],
      mcp: ["MCP Server"],
      context: ["Root Context"],
      hooks: ["Hook"],
      cron: ["Cron Job"],
      plugins: ["Plugin", "Command"],
      config: ["Config", "Memory Config", "Root Context", "MCP Server"],
      logs: ["Log File"],
      sessions: ["Session Summary"],
      statedb: ["State DB"],
      checkpoints: ["Checkpoint"],
      "agent-runners": ["Agent Runner"],
      "diff-audit": [],
      audit: [],
      web: [],
    };
    const allowed = map[selectedSection] || [];
    return items.filter(i => allowed.includes(i.type));
  };

  const fetchWorkspaceList = () => {
    fetch('/api/workspaces').then(r => r.json()).then(list => setWorkspaceList(list || [])).catch(() => {});
  };

  const handleArchiveItem = async (item) => {
    const res = await fetch('/api/actions/archive', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_path: item.source_path, workspace: activeWorkspace }),
    });
    const data = await res.json();
    if (res.ok) {
      setActionStatus({ type: 'success', msg: `아카이브 완료 → ${data.archived_to}` });
      setArchiveConfirm(null);
      fetchHarness();
    } else {
      setActionStatus({ type: 'error', msg: data.detail || '아카이브 실패' });
    }
    setTimeout(() => setActionStatus(null), 5000);
  };

  const handleArchiveRecommendations = async (recs) => {
    const targets = recs.filter(r => r.category !== 'HIGH_VALUE' && r.item?.source_path);
    if (targets.length === 0) return;
    const ok = window.confirm(`${targets.length}개 추천 항목을 아카이브 폴더로 이동할까요?`);
    if (!ok) return;

    setRecLoading(true);
    let moved = 0;
    let failed = 0;
    for (const rec of targets) {
      try {
        const res = await fetch(`${API_BASE}/api/actions/archive`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ source_path: rec.item.source_path, workspace: activeWorkspace }),
        });
        if (res.ok) moved += 1;
        else failed += 1;
      } catch {
        failed += 1;
      }
    }

    setActionStatus({
      type: failed ? 'error' : 'success',
      msg: failed ? `아카이브 ${moved}개 완료, ${failed}개 실패` : `아카이브 ${moved}개 완료`,
    });
    setRecommendations(prev => prev.filter(r => !targets.some(t => t.item?.source_path === r.item?.source_path)));
    fetchHarness();
    setRecLoading(false);
    setTimeout(() => setActionStatus(null), 5000);
  };

  const handleCopyItem = async () => {
    if (!copyModal || !copyTargetWorkspace) return;
    const res = await fetch('/api/actions/copy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_path: copyModal.source_path,
        target_workspace: copyTargetWorkspace,
        target_subdir: copyTargetSubdir,
      }),
    });
    const data = await res.json();
    if (res.ok) {
      setActionStatus({ type: 'success', msg: `복사 완료 → ${data.copied_to}` });
      setCopyModal(null);
      setCopyTargetWorkspace('');
      setCopyTargetSubdir('');
    } else {
      setActionStatus({ type: 'error', msg: data.detail || '복사 실패' });
    }
    setTimeout(() => setActionStatus(null), 5000);
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
      const logLimit = item.type === "Log File" ? "&max_bytes=200000&tail=true" : "";
      const res = await fetch(`${API_BASE}/api/read?path=${encodeURIComponent(item.source_path)}${allowMissing}${logLimit}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setEditContent(data.content);
      if (data.missing) {
        setSaveStatus("New file. Choose a preset or write content, then Save.");
      } else if (data.truncated) {
        setSaveStatus(`Showing tail: ${data.bytes_read?.toLocaleString()} / ${data.size_bytes?.toLocaleString()} bytes`);
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
    if (molderResponse?.status === "loading" || piMoldPolling) return;
    if (piMode) { handleMoldWithPi(); return; }

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
        editing_file_name: editingItem?.name || null,
        editing_file_content: editingItem ? editContent : null,
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

  // on_demand 항목(Subagent 등 호출 시에만 로드)은 baseline 컨텍스트에 포함하지 않음
  const estimatedTotalTokens = items.reduce((sum, item) =>
    item.metadata?.on_demand ? sum : sum + (item.token_estimate || 0), 0);
  const tokenPercentage = (estimatedTotalTokens / MAX_CONTEXT_TOKENS) * 100;
  let tokenStatusColor = "safe";
  if (tokenPercentage > 75) tokenStatusColor = "danger";
  else if (tokenPercentage > 40) tokenStatusColor = "warning";

  const getFileExtension = (path = "") => {
    const filename = path.split("/").pop() || "";
    return filename.includes(".") ? filename.split(".").pop().toLowerCase() : "text";
  };

  const getEditorKind = (item) => {
    const ext = getFileExtension(item?.source_path || item?.name || "");
    if (["md", "mdc", "markdown", "rules"].includes(ext)) return "markdown";
    if (["yaml", "yml"].includes(ext)) return "yaml";
    if (["json", "jsonl", "pbtxt"].includes(ext)) return "json";
    if (ext === "toml") return "toml";
    if (["py", "sh", "bash", "js", "mjs", "ts", "tsx", "jsx"].includes(ext)) return "script";
    return "text";
  };

  const getPrismLanguage = (item) => {
    const ext = getFileExtension(item?.source_path || item?.name || "");
    if (["yaml", "yml"].includes(ext)) return { key: "yaml", lang: Prism.languages.yaml };
    if (["json", "jsonl"].includes(ext)) return { key: "json", lang: Prism.languages.json };
    if (ext === "toml") return { key: "toml", lang: Prism.languages.toml };
    if (["js", "mjs", "jsx"].includes(ext)) return { key: "javascript", lang: Prism.languages.javascript };
    if (["ts", "tsx"].includes(ext)) return { key: "typescript", lang: Prism.languages.typescript };
    if (["py", "sh", "bash"].includes(ext)) return { key: "bash", lang: Prism.languages.bash };
    return { key: "markdown", lang: Prism.languages.markdown };
  };

  const activeWorkspaceName = workspaces.find(ws => ws.path === activeWorkspace)?.name || "Agent";
  const editorKind = getEditorKind(editingItem);
  const editorPath = editingItem?.source_path || "";
  const editorFileName = editorPath.split("/").pop() || editingItem?.name || "";
  const editorLineCount = editContent ? editContent.split(/\r?\n/).length : 0;
  const editorCharCount = editContent?.length || 0;

  return (
    <div className="app-layout">
      {/* Left Sidebar: Controls & Dashboard */}
      <aside className="sidebar-container">
        <header className="app-header">
          <div className="header-brand">
            <h1>Agent Harness Studio</h1>
            <button
              className="dark-mode-toggle"
              onClick={() => setIsDarkMode(v => !v)}
              title={isDarkMode ? '컴포트 모드로 전환' : '다크 모드로 전환'}
            >
              {isDarkMode ? '◐' : '●'}
            </button>
          </div>

          <div className="workspace-selector">
            <span className="workspace-label">Agent</span>
            <select value={activeWorkspace} onChange={handleWorkspaceChange} className="agent-dropdown">
              {workspaces.map(ws => (
                <option key={ws.id} value={ws.path}>{ws.name}</option>
              ))}
            </select>
            <button
              className="manual-refresh-btn"
              onClick={handleManualRefresh}
              title="새로고침"
            >🔄</button>
          </div>

          {envInfo && (
            <div className="env-info">
              {envInfo.is_readonly && (
                <span className="env-badge readonly" title="HARNESS_READONLY=1: 쓰기 비활성화">READ-ONLY</span>
              )}
              <span className={`env-badge ${envInfo.is_sandbox ? 'sandbox' : 'real'}`}>
                {envInfo.is_sandbox ? 'SANDBOX' : 'REAL'}
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
                ...{envInfo.hermes_home.split("/").slice(-2).join("/")}
              </span>
            </div>
          )}

          <div className="token-estimator-compact" onClick={() => setShowPayloadDetail(true)} title="클릭하여 컨텍스트 구성 상세 보기" style={{cursor:"pointer"}}>
            <div className="token-gauge-header">
              <span className="token-label">Payload</span>
              <span className={`token-percentage-badge ${tokenStatusColor}`}>
                {estimatedTotalTokens.toLocaleString()} / 128k ({tokenPercentage.toFixed(1)}%)
              </span>
            </div>
            <div className="token-progress-track">
              <div className={`token-progress-bar ${tokenStatusColor}`} style={{ width: `${Math.min(100, tokenPercentage)}%` }} />
            </div>
          </div>
          <button
            className="diet-btn"
            title="컨텍스트 다이어트 — 대용량/오래된 항목 정리"
            onClick={() => { setShowDietModal(true); fetchWorkspaceList(); }}
          >🥗</button>
        </header>

        <section className="harness-overview">
          <div className="hero-compact">
            <h2>Harness over Model</h2>
          </div>

          {/* Gemini CLI 지원 종료 배너 */}
          {activeWorkspace && activeWorkspace.endsWith("/.gemini") && (
            <div className="workspace-notice warning">
              ⚠️ <strong>Gemini CLI → Antigravity CLI 전환 예정</strong>
              &nbsp;— Google은 2026년 6월 18일 Gemini CLI를 Antigravity CLI(<code>agy</code>)로 전환합니다.
              이후 이 워크스페이스는 <strong>Antigravity</strong>로 관리하세요.
            </div>
          )}

          {/* Cursor 커스텀 구조 안내 배너 */}
          {activeWorkspace && activeWorkspace.endsWith("/.cursor") && (
            <div className="workspace-notice info">
              ℹ️ <strong>Cursor 커스텀 구조</strong>
              &nbsp;— Cursor에는 공식 글로벌 하네스 규격이 없습니다.
              여기서 표시되는 항목은 <code>~/.cursor/</code>에 직접 추가된 커스텀 스킬/플러그인입니다.
            </div>
          )}

          <div className="cards-grid">
            {sections.map((sec) => {
              const configTypes = ["Config", "Memory Config", "Root Context", "MCP Server"];
              const count = sec.id === 'config'
                ? items.filter(i => configTypes.includes(i.type)).length
                : sec.id === 'audit'
                ? auditLogs.length
                : sec.id === 'sessions'
                ? (items.find(i => i.type === "Session Summary")?.metadata?.total_sessions || 0)
                : sec.id === 'statedb'
                ? items.filter(i => i.type === "State DB").length
                : sec.id === 'checkpoints'
                ? items.filter(i => i.type === "Checkpoint").length
                : sec.id === 'agent-runners'
                ? agentRunners.filter(r => r.installed || r.state === "READY").length
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
                {!["web", "memory", "audit", "diff-audit", "sessions", "statedb", "checkpoints", "agent-runners"].includes(selectedSection) && (
                  <div className="panel-controls">
                    <input
                      className="panel-search-input"
                      type="text"
                      placeholder="검색..."
                      value={searchQuery}
                      onChange={e => setSearchQuery(e.target.value)}
                    />
                    <select
                      className="panel-sort-select"
                      value={sortKey}
                      onChange={e => setSortKey(e.target.value)}
                      title="Sort items"
                    >
                      <option value="name-asc">Name A-Z</option>
                      <option value="name-desc">Name Z-A</option>
                      <option value="modified-desc">Newest</option>
                      <option value="modified-asc">Oldest</option>
                      <option value="state">State</option>
                      <option value="type">Type</option>
                    </select>
                  </div>
                )}
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

                {/* Diff Audit Panel */}
                {selectedSection === "diff-audit" && (
                  <div className="diff-audit-container">
                    <div className="audit-timeline-header">
                      <h4>Git Diff Audit — {activeWorkspace ? activeWorkspace.split('/').pop() : 'workspace'}</h4>
                      <button onClick={() => fetchDiffAudit()} className="refresh-btn" disabled={diffAuditLoading}>
                        {diffAuditLoading ? "Scanning…" : "🔄 Re-scan"}
                      </button>
                    </div>
                    {diffAuditLoading && <div className="editor-loading">Running git audit…</div>}
                    {diffAudit?.error && <div className="chat-empty" style={{color:"#f87171"}}>Error: {diffAudit.error}</div>}
                    {diffAudit && !diffAudit.error && !diffAuditLoading && (
                      <>
                        {!diffAudit.is_git_repo ? (
                          <div className="chat-empty">Not a git repository.</div>
                        ) : (
                          <>
                            <div className="diff-audit-summary">
                              <span className={`risk-badge risk-${diffAudit.risk}`}>{diffAudit.risk.toUpperCase()}</span>
                              <span className="diff-file-count">{diffAudit.file_count} file{diffAudit.file_count !== 1 ? 's' : ''} changed</span>
                            </div>
                            {diffAudit.warnings.length > 0 && (
                              <div className="diff-warnings">
                                {diffAudit.warnings.map((w, i) => (
                                  <div key={i} className="diff-warning-row">⚠️ {w}</div>
                                ))}
                              </div>
                            )}
                            {diffAudit.changed_files.length === 0 ? (
                              <div className="chat-empty" style={{color:"#4ade80"}}>✅ Working tree clean — no uncommitted changes.</div>
                            ) : (
                              <div className="diff-file-list">
                                {diffAudit.changed_files.map((f, i) => (
                                  <div key={i} className={`diff-file-row ${f.protected ? 'protected' : ''}`}>
                                    <span className={`diff-status diff-status-${f.status}`}>{f.status}</span>
                                    <span className="diff-path">{f.path}</span>
                                    {f.protected && <span className="diff-protected-badge">protected</span>}
                                  </div>
                                ))}
                              </div>
                            )}
                            {diffAudit.stat && (
                              <pre className="diff-stat-block">{diffAudit.stat}</pre>
                            )}
                          </>
                        )}
                      </>
                    )}
                    {!diffAudit && !diffAuditLoading && (
                      <div className="chat-empty">Click Re-scan to audit current working tree changes.</div>
                    )}
                  </div>
                )}

                {/* Agent Runner Panel */}
                {selectedSection === "agent-runners" && (
                  <div className="agent-runner-container">
                    {/* TODO(agent-runner): evolve this from status/preview into a live
                        transcript fed by Pi RPC/SSE run events. */}
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
                )}

                {/* ── Sessions Dashboard ── */}
                {selectedSection === "sessions" && (() => {
                  const sessItems = getFilteredItems();
                  if (!sessItems.length) return <div className="chat-empty">세션 데이터 없음 (state.db 없음)</div>;
                  const item = sessItems[0];
                  const m = item.metadata || {};
                  const maxModel = m.models?.[0]?.count || 1;
                  return (
                    <div className="sessions-dashboard">
                      <div className="sessions-stats-grid">
                        <div className="sessions-stat"><span className="sessions-stat-val">{(m.total_sessions||0).toLocaleString()}</span><span className="sessions-stat-label">세션</span></div>
                        <div className="sessions-stat"><span className="sessions-stat-val">{(m.total_messages||0).toLocaleString()}</span><span className="sessions-stat-label">메시지</span></div>
                        <div className="sessions-stat"><span className="sessions-stat-val">{(m.total_tool_calls||0).toLocaleString()}</span><span className="sessions-stat-label">툴 호출</span></div>
                        <div className="sessions-stat"><span className="sessions-stat-val">${(m.total_cost_usd||0).toFixed(2)}</span><span className="sessions-stat-label">추정 비용</span></div>
                        <div className="sessions-stat"><span className="sessions-stat-val">{((m.total_input_tokens||0)/1000).toFixed(0)}k</span><span className="sessions-stat-label">입력 토큰</span></div>
                        <div className="sessions-stat"><span className="sessions-stat-val">{((m.total_output_tokens||0)/1000).toFixed(0)}k</span><span className="sessions-stat-label">출력 토큰</span></div>
                      </div>
                      {m.first_session && (
                        <div className="sessions-date-range">{formatSessionDate(m.first_session)} ~ {formatSessionDate(m.last_session)}</div>
                      )}
                      {m.models?.length > 0 && (
                        <div className="sessions-models-section">
                          <div className="sessions-section-title">모델 분포</div>
                          {m.models.map(({ model, count }) => (
                            <div key={model} className="sessions-model-row">
                              <span className="sessions-model-name">{model}</span>
                              <div className="sessions-model-bar-track">
                                <div className="sessions-model-bar-fill" style={{ width: `${Math.round(count/maxModel*100)}%` }} />
                              </div>
                              <span className="sessions-model-count">{count}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {m.recent_sessions?.length > 0 && (
                        <div className="sessions-recent-section">
                          <div className="sessions-section-title">최근 세션 <span className="sessions-hint">(클릭하여 메시지 보기)</span></div>
                          {m.recent_sessions.map((s, i) => (
                            <div
                              key={i}
                              className={`sessions-recent-row${selectedSessionId === s.id ? " sessions-recent-active" : ""}`}
                              onClick={() => s.id && fetchSessionMessages(s.id)}
                              style={{ cursor: s.id ? "pointer" : "default" }}
                            >
                              <span className="sessions-recent-title">{s.title || '(제목 없음)'}</span>
                              <span className="sessions-recent-meta">{s.model} · {s.message_count}msg</span>
                              <span className="sessions-recent-date">{formatSessionDate(s.started_at)}</span>
                            </div>
                          ))}
                        </div>
                      )}
                      {/* 더 보기 — 전체 세션 목록 */}
                      {!allSessions && !allSessionsLoading && (
                        <div className="sessions-more-row">
                          <button className="sessions-more-btn" onClick={fetchAllSessions}>
                            더 보기 (전체 목록)
                          </button>
                        </div>
                      )}
                      {allSessionsLoading && <div className="session-msg-loading">전체 목록 로딩 중...</div>}
                      {allSessions && (
                        <div className="sessions-all-list">
                          <div className="sessions-section-title">
                            전체 세션 ({allSessions.length})
                            <button className="sessions-collapse-btn" onClick={() => setAllSessions(null)}>접기</button>
                          </div>
                          {allSessions.map((s, i) => (
                            <div
                              key={i}
                              className={`sessions-recent-row${selectedSessionId === s.id ? " sessions-recent-active" : ""}`}
                              onClick={() => s.id && fetchSessionMessages(s.id)}
                              style={{ cursor: s.id ? "pointer" : "default" }}
                            >
                              <span className="sessions-recent-title">{s.title || '(제목 없음)'}</span>
                              <span className="sessions-recent-meta">{s.model} · {s.message_count}msg</span>
                              <span className="sessions-recent-date">{formatSessionDate(s.started_at)}</span>
                            </div>
                          ))}
                        </div>
                      )}

                      {selectedSessionId && (
                        <div className="session-messages-panel">
                          <div className="session-messages-header">
                            <span>메시지 스레드</span>
                            <button className="session-msg-close" onClick={() => { setSelectedSessionId(null); setSessionMessages(null); }}>×</button>
                          </div>
                          {sessionMsgLoading && <div className="session-msg-loading">로딩 중...</div>}
                          {sessionMessages?.error && <div className="session-msg-error">{sessionMessages.error}</div>}
                          {sessionMessages?.messages?.map((msg, i) => (
                            <div key={i} className={`session-msg session-msg-${msg.role}`}>
                              <span className="session-msg-role">{msg.role}</span>
                              <div className="session-msg-content">
                                {typeof msg.content === 'string'
                                  ? (msg.content.length > 600 ? msg.content.slice(0, 600) + '…' : msg.content)
                                  : JSON.stringify(msg.content)?.slice(0, 300)}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })()}

                {/* ── State DB Viewer ── */}
                {selectedSection === "statedb" && (
                  <div className="statedb-list">
                    {getFilteredItems().map((item, idx) => (
                      <div key={idx} className="statedb-card">
                        <div className="statedb-card-header">
                          <strong className="statedb-name">{item.name}</strong>
                          <span className="statedb-desc">{item.summary}</span>
                          <span className={`item-state state-${item.state.toLowerCase()}`}>{item.state}</span>
                        </div>
                        {item.metadata?.tables && (
                          <div className="statedb-meta">
                            <span className="statedb-size">{((item.metadata.size_bytes||0)/1024).toFixed(1)} KB</span>
                            <span className="statedb-rows">{(item.metadata.total_rows||0).toLocaleString()}행</span>
                          </div>
                        )}
                        {item.metadata?.tables?.length > 0 && (
                          <table className="statedb-table">
                            <thead><tr><th>테이블</th><th>행 수</th><th>주요 컬럼</th></tr></thead>
                            <tbody>
                              {item.metadata.tables.map((t) => (
                                <tr key={t.name}>
                                  <td className="statedb-tname">{t.name}</td>
                                  <td className="statedb-trows">{t.rows.toLocaleString()}</td>
                                  <td className="statedb-tcols">{t.columns.join(', ')}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* ── Skills 카테고리 트리 ── */}
                {selectedSection === "skills" && (() => {
                  const skillItems = getFilteredSortedItems();
                  if (!skillItems.length && searchQuery.trim()) {
                    return <div className="search-empty">"{searchQuery}"에 해당하는 스킬 없음</div>;
                  }
                  if (!skillItems.length) return <div className="chat-empty">스킬 없음</div>;
                  const catMap = {};
                  skillItems.forEach(item => {
                    const cat = item.metadata?.category || 'uncategorized';
                    if (!catMap[cat]) catMap[cat] = [];
                    catMap[cat].push(item);
                  });
                  const cats = sortSkillCategories(Object.keys(catMap), catMap);
                  return cats.map(cat => {
                    const isCollapsed = !searchQuery.trim() && collapsedCategories.has(cat);
                    const catSkills = sortItems(catMap[cat]);
                    return (
                      <div key={cat} className="skills-cat">
                        <div className="skills-cat-header" onClick={() => setCollapsedCategories(prev => {
                          const next = new Set(prev);
                          isCollapsed ? next.delete(cat) : next.add(cat);
                          return next;
                        })}>
                          <span className="skills-cat-arrow">{isCollapsed ? '▶' : '▼'}</span>
                          <span className="skills-cat-name">{cat}</span>
                          <span className="skills-cat-count">{catSkills.length}</span>
                        </div>
                        {!isCollapsed && catSkills.map((item, idx) => (
                          <div key={idx} className="item-row">
                            <div className="item-main">
                              <strong>{item.name}</strong>
                              <span className="item-type">{item.type}</span>
                            </div>
                            <div className="item-summary">{item.summary}</div>
                            <div className={`item-state state-${item.state.toLowerCase()}`}>{item.state}</div>
                            {isEditable(item) && (
                              <button className="edit-btn" onClick={() => handleEditClick(item)}>Edit</button>
                            )}
                            {canInjectToHermes(item) && (
                              <button className="converter-action-btn" onClick={() => handleInjectSkillToHermes(item)} title="Convert and inject into Hermes skills">
                                To Hermes
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    );
                  });
                })()}

                {/* ── Checkpoints 섹션 ── */}
                {selectedSection === "checkpoints" && (() => {
                  const cpItems = getFilteredItems();
                  if (!cpItems.length) return <div className="chat-empty">체크포인트 없음</div>;
                  return (
                    <div className="checkpoints-list">
                      {cpItems.map((item, idx) => (
                        <div key={idx} className="checkpoint-row">
                          <div className="checkpoint-main">
                            <code className="checkpoint-id">{item.metadata?.project_id}</code>
                            <span className={`item-state state-${item.state.toLowerCase()}`}>{item.state}</span>
                          </div>
                          <div className="checkpoint-workdir">{item.metadata?.workdir || item.summary}</div>
                          <div className="checkpoint-times">
                            <span>생성: {item.metadata?.created_at || '-'}</span>
                            <span>최근 접근: {item.metadata?.last_touch || '-'}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  );
                })()}

                {/* ── Generic items — MCP: ERROR 상단 정렬, Cron/Plugin: 확장 상세, 검색 필터 ── */}
                {selectedSection !== "memory" && selectedSection !== "audit" && selectedSection !== "diff-audit" && selectedSection !== "sessions" && selectedSection !== "statedb" && selectedSection !== "skills" && selectedSection !== "checkpoints" && selectedSection !== "agent-runners" && (() => {
                  let displayItems = getFilteredSortedItems();
                  if (selectedSection === "mcp") {
                    displayItems = [...displayItems].sort((a, b) => {
                      if (a.state === "ERROR" && b.state !== "ERROR") return -1;
                      if (a.state !== "ERROR" && b.state === "ERROR") return 1;
                      return compareItems(a, b);
                    });
                  }
                  if (!displayItems.length && searchQuery.trim()) {
                    return <div className="search-empty">"{searchQuery}"에 해당하는 항목 없음</div>;
                  }
                  return displayItems.map((item, idx) => {
                    const rowKey = `${selectedSection}-${idx}`;
                    const isExpanded = expandedRows.has(rowKey);
                    const toggleExpand = () => setExpandedRows(prev => {
                      const next = new Set(prev);
                      isExpanded ? next.delete(rowKey) : next.add(rowKey);
                      return next;
                    });
                    const isCron = item.type === "Cron Job";
                    const isMcp = item.type === "MCP Server";
                    const isPlugin = item.type === "Plugin" || item.type === "Command";
                    const hasExpand = isCron || isPlugin;
                    return (
                      <div key={idx} className={`item-row${isMcp && item.state === "ERROR" ? " item-row-error" : ""}`}>
                        <div className="item-main">
                          <strong>{item.name}</strong>
                          <span className="item-type">{item.type}</span>
                          {isMcp && item.metadata?.state_reason && (
                            <span className="mcp-error-badge" title={item.metadata.state_reason}>⚠ {item.metadata.state_reason}</span>
                          )}
                          {hasExpand && (
                            <button className="expand-btn" onClick={toggleExpand}>{isExpanded ? "▲" : "▼"}</button>
                          )}
                        </div>
                        <div className="item-summary">{item.summary}</div>
                        <div className={`item-state state-${item.state.toLowerCase()}`}>{item.state}</div>
                        {isCron && isExpanded && (
                          <div className="cron-detail-panel">
                            <div className="cron-detail-grid">
                              <span className="cron-detail-label">완료</span><span className="cron-detail-val">{item.metadata?.completed_count ?? 0}회</span>
                              <span className="cron-detail-label">다음 실행</span><span className="cron-detail-val">{item.metadata?.next_run_at ? new Date(item.metadata.next_run_at).toLocaleString('ko-KR') : '-'}</span>
                              <span className="cron-detail-label">최근 실행</span><span className="cron-detail-val">{item.metadata?.last_run_at ? new Date(item.metadata.last_run_at).toLocaleString('ko-KR') : '-'}</span>
                              <span className="cron-detail-label">최근 상태</span><span className="cron-detail-val">{item.metadata?.last_status || '-'}</span>
                            </div>
                            {item.metadata?.last_error && (
                              <div className="cron-error-msg">{item.metadata.last_error}</div>
                            )}
                          </div>
                        )}
                        {isPlugin && isExpanded && (
                          <div className="plugin-detail-panel">
                            {item.metadata?.provides_tools?.length > 0 && (
                              <div className="plugin-detail-section">
                                <span className="plugin-detail-label">Tools ({item.metadata.provides_tools.length})</span>
                                <div className="plugin-chips">
                                  {item.metadata.provides_tools.map(t => <span key={t} className="plugin-chip plugin-chip-tool">{t}</span>)}
                                </div>
                              </div>
                            )}
                            {(item.metadata?.provides_hooks?.length > 0 || item.metadata?.hooks?.length > 0) && (
                              <div className="plugin-detail-section">
                                <span className="plugin-detail-label">Hooks</span>
                                <div className="plugin-chips">
                                  {[...(item.metadata.provides_hooks || []), ...(item.metadata.hooks || [])].map((h, hi) => (
                                    <span key={hi} className="plugin-chip plugin-chip-hook">{typeof h === 'string' ? h : JSON.stringify(h)}</span>
                                  ))}
                                </div>
                              </div>
                            )}
                            {item.metadata?.author && <div className="plugin-detail-meta">by {item.metadata.author} · v{item.metadata.version}</div>}
                          </div>
                        )}
                        {isEditable(item) ? (
                          <button className="edit-btn" onClick={() => handleEditClick(item)}>
                            {selectedSection === "logs" || envInfo?.is_readonly ? "View" : "Edit"}
                          </button>
                        ) : null}
                      </div>
                    );
                  });
                })()}
              </div>
            </div>
          )}

          {editingItem && (
            <div className={`editor-panel editor-kind-${editorKind}`}>
              <div className="panel-header">
                <div className="editor-title-block">
                  <div className="editor-title-row">
                    <span className="editor-kind-dot" />
                    <h3>{editingItem.name}</h3>
                  </div>
                  <div className="editor-subtitle">{editorFileName}</div>
                </div>
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

              <div className="editor-context-bar">
                <span className={`editor-chip chip-${editorKind}`}>{editorKind.toUpperCase()}</span>
                <span className="editor-chip">{editingItem.type}</span>
                <span className={`editor-chip state-chip state-${editingItem.state.toLowerCase()}`}>{editingItem.state}</span>
                <span className="editor-chip">{activeWorkspaceName}</span>
                {envInfo?.is_readonly && <span className="editor-chip chip-readonly">VIEW ONLY</span>}
                <span className="editor-stat">{editorLineCount.toLocaleString()} lines</span>
                <span className="editor-stat">{editorCharCount.toLocaleString()} chars</span>
                <span className="editor-path" title={editorPath}>{editorPath}</span>
              </div>

              {editingItem.metadata?.original_source_path && (
                <div className="editor-origin-note">
                  Directory item opened via representative file: {editingItem.metadata.representative_file}
                </div>
              )}

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
                        {canInjectToHermes(editingItem) && (
                          <button className="preset-badge-btn" onClick={() => handleInjectSkillToHermes(editingItem)} title="Convert this skill and inject it into ~/.hermes/skills">
                            Inject to Hermes
                          </button>
                        )}
                      </div>
                    </>
                  )}
                </div>
              )}

              <div className="editor-body">
                {editLoading
                  ? <div className="editor-loading">Loading file content...</div>
                  : <div className={`code-editor-wrapper editor-kind-${editorKind}`}>
                      <EditorErrorBoundary>
                      <Editor
                        value={editContent || ""}
                        onValueChange={code => setEditContent(code)}
                        highlight={code => {
                          try {
                            const prism = getPrismLanguage(editingItem);
                            return Prism.highlight(code || "", prism.lang || Prism.languages.markdown || {}, prism.key);
                          } catch {
                            return code || "";
                          }
                        }}
                        padding={15}
                        style={{
                          fontFamily: '"Fira Code", "Consolas", monospace',
                          fontSize: 14,
                          minHeight: '100%',
                          color: '#d8def8',
                          backgroundColor: 'transparent',
                        }}
                        disabled={envInfo?.is_readonly}
                        className="editor-textarea-prism"
                      />
                      </EditorErrorBoundary>
                    </div>
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

      {/* Resize Handle */}
      <div className="resize-handle" onMouseDown={handleResizeStart} />

      {/* Right Column: Chat Molder Interface */}
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
                placeholder="http://127.0.0.1:20128/v1"
              />
            </label>
            <label>
              Model
              <input
                value={llmDraft.model}
                onChange={e => setLlmDraft(v => ({ ...v, model: e.target.value }))}
                placeholder="letitbe"
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
                            onClick={() => {
                              fetchFileContent({source_path: fp, name: fp.split("/").pop()});
                              setSelectedSection(null);
                            }}
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

      {/* Payload Detail Modal */}
      {showPayloadDetail && (() => {
        // baseline: on_demand 아닌 항목 / onDemand: 호출 시에만 로드
        const byType = {};
        const onDemandByType = {};
        items.forEach(item => {
          const t = item.type || "기타";
          const isOD = item.metadata?.on_demand;
          const bucket = isOD ? onDemandByType : byType;
          if (!bucket[t]) bucket[t] = { count: 0, tokens: 0, items: [] };
          bucket[t].count++;
          bucket[t].tokens += item.token_estimate || 0;
          bucket[t].items.push(item);
        });
        const sorted = Object.entries(byType).sort((a, b) => b[1].tokens - a[1].tokens);
        const onDemandSorted = Object.entries(onDemandByType).sort((a, b) => b[1].tokens - a[1].tokens);
        const onDemandTotal = onDemandSorted.reduce((s, [, v]) => s + v.tokens, 0);
        const topItems = [...items]
          .filter(i => i.token_estimate > 0 && !i.metadata?.on_demand)
          .sort((a, b) => (b.token_estimate || 0) - (a.token_estimate || 0))
          .slice(0, 10);
        return (
          <div className="payload-modal-overlay" onClick={() => setShowPayloadDetail(false)}>
            <div className="payload-modal" onClick={e => e.stopPropagation()}>
              <div className="payload-modal-header">
                <span className="payload-modal-title">컨텍스트 구성 상세</span>
                <span className={`token-percentage-badge ${tokenStatusColor}`} style={{fontSize:"13px"}}>
                  {estimatedTotalTokens.toLocaleString()} / 128k ({tokenPercentage.toFixed(1)}%)
                </span>
                <button className="payload-modal-close" onClick={() => setShowPayloadDetail(false)}>✕</button>
              </div>

              <div className="payload-modal-bar-wrap">
                <div className="payload-modal-bar-track">
                  {sorted.map(([type, info]) => {
                    const pct = (info.tokens / MAX_CONTEXT_TOKENS) * 100;
                    const colors = {
                      "Skill": "#6366f1", "Memory File": "#10b981", "Log File": "#f59e0b",
                      "Root Context": "#3b82f6", "MCP Server": "#8b5cf6", "Config": "#64748b",
                      "Memory Config": "#06b6d4", "Memory Directory": "#84cc16",
                      "Session Summary": "#f97316", "State DB": "#ec4899",
                    };
                    const color = colors[type] || "#94a3b8";
                    return (
                      <div key={type} className="payload-modal-bar-seg"
                        style={{ width: `${Math.min(pct, 100)}%`, background: color }}
                        title={`${type}: ${info.tokens.toLocaleString()} tokens`} />
                    );
                  })}
                </div>
              </div>

              <div className="payload-modal-body">
                <div className="payload-modal-col">
                  <div className="payload-modal-section-title">타입별 분포</div>
                  <table className="payload-table">
                    <thead><tr><th>타입</th><th>개수</th><th>토큰</th><th>비율</th></tr></thead>
                    <tbody>
                      {sorted.map(([type, info]) => (
                        <tr key={type}>
                          <td>{type}</td>
                          <td style={{textAlign:"right"}}>{info.count}</td>
                          <td style={{textAlign:"right"}}>{info.tokens.toLocaleString()}</td>
                          <td style={{textAlign:"right"}}>{((info.tokens / MAX_CONTEXT_TOKENS) * 100).toFixed(1)}%</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="payload-modal-col">
                  <div className="payload-modal-section-title">토큰 상위 10개 항목</div>
                  <table className="payload-table">
                    <thead><tr><th>이름</th><th>타입</th><th>토큰</th></tr></thead>
                    <tbody>
                      {topItems.map((item, i) => (
                        <tr key={i} style={{cursor:"pointer"}} onClick={() => { handleEditClick(item); setShowPayloadDetail(false); }}>
                          <td style={{maxWidth:"160px", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap"}} title={item.name}>{item.name}</td>
                          <td style={{color:"#94a3b8", fontSize:"11px"}}>{item.type}</td>
                          <td style={{textAlign:"right"}}>{(item.token_estimate||0).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* On-demand 항목 (baseline 계산에서 제외) */}
              {onDemandSorted.length > 0 && (
                <div className="payload-modal-ondemand">
                  <div className="payload-modal-ondemand-header">
                    <span>On-Demand 항목 — 호출 시에만 로드 (baseline 계산 제외)</span>
                    <span className="payload-od-total">{onDemandTotal.toLocaleString()} tokens 잠재</span>
                  </div>
                  <table className="payload-table" style={{margin:"0 20px", width:"calc(100% - 40px)"}}>
                    <thead><tr><th>타입</th><th>개수</th><th>잠재 토큰</th></tr></thead>
                    <tbody>
                      {onDemandSorted.map(([type, info]) => (
                        <tr key={type}>
                          <td>{type}</td>
                          <td style={{textAlign:"right"}}>{info.count}</td>
                          <td style={{textAlign:"right", color:"#94a3b8"}}>{info.tokens.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        );
      })()}

      {/* ─── Action Status Toast ─── */}
      {actionStatus && (
        <div className={`action-toast ${actionStatus.type}`}>
          {actionStatus.type === 'success' ? '✓ ' : '✗ '}{actionStatus.msg}
        </div>
      )}

      {/* ─── Archive Confirm Dialog ─── */}
      {archiveConfirm && (
        <div className="diet-overlay" onClick={() => setArchiveConfirm(null)}>
          <div className="diet-confirm" onClick={e => e.stopPropagation()}>
            <div className="diet-confirm-title">🗄️ 아카이브 확인</div>
            <div className="diet-confirm-body">
              <strong>{archiveConfirm.name}</strong> 을 아카이브 폴더로 이동합니다.<br/>
              <span style={{color:'#94a3b8',fontSize:'12px'}}>{archiveConfirm.source_path}</span>
            </div>
            <div className="diet-confirm-actions">
              <button className="diet-btn-cancel" onClick={() => setArchiveConfirm(null)}>취소</button>
              <button className="diet-btn-ok" onClick={() => handleArchiveItem(archiveConfirm)}>이동</button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Copy To Modal ─── */}
      {copyModal && (
        <div className="diet-overlay" onClick={() => setCopyModal(null)}>
          <div className="diet-confirm" onClick={e => e.stopPropagation()}>
            <div className="diet-confirm-title">📋 다른 워크스페이스로 복사</div>
            <div className="diet-confirm-body">
              <strong>{copyModal.name}</strong><br/>
              <span style={{color:'#94a3b8',fontSize:'12px'}}>{copyModal.source_path}</span>
              <div style={{marginTop:'12px'}}>
                <label className="diet-label">대상 워크스페이스</label>
                <select className="diet-select" value={copyTargetWorkspace} onChange={e => setCopyTargetWorkspace(e.target.value)}>
                  <option value="">-- 선택 --</option>
                  {workspaceList.filter(w => w.path !== activeWorkspace).map(w => (
                    <option key={w.id} value={w.path}>{w.name}</option>
                  ))}
                </select>
              </div>
              <div style={{marginTop:'8px'}}>
                <label className="diet-label">하위 디렉토리 (선택)</label>
                <input className="diet-input" type="text" placeholder="예: skills, rules, agents" value={copyTargetSubdir} onChange={e => setCopyTargetSubdir(e.target.value)} />
              </div>
            </div>
            <div className="diet-confirm-actions">
              <button className="diet-btn-cancel" onClick={() => setCopyModal(null)}>취소</button>
              <button className="diet-btn-ok" disabled={!copyTargetWorkspace} onClick={handleCopyItem}>복사</button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Context Diet Modal ─── */}
      {showDietModal && (() => {
        const now = Date.now() / 1000;
        const STALE_DAYS = 90;
        const LARGE_TOKENS = 5000;
        const enriched = items
          .filter(i => i.source_path && !i.source_path.endsWith('/'))
          .map(i => ({
            ...i,
            days_old: i.metadata?.modified_at ? Math.floor((now - i.metadata.modified_at) / 86400) : null,
            is_stale: i.metadata?.modified_at ? (now - i.metadata.modified_at) > STALE_DAYS * 86400 : false,
            is_large: (i.token_estimate || 0) >= LARGE_TOKENS,
          }));

        const filtered = dietTab === 'all'
          ? enriched.filter(i => i.is_large || i.is_stale)
          : dietTab === 'large'
            ? enriched.filter(i => i.is_large)
            : dietTab === 'stale'
              ? enriched.filter(i => i.is_stale)
              : [];

        const sorted = [...filtered].sort((a, b) => (b.token_estimate || 0) - (a.token_estimate || 0));
        const smartArchiveable = recommendations.filter(r => r.category !== 'HIGH_VALUE' && r.item?.source_path);
        const totalSaveable = dietTab === 'smart'
          ? smartArchiveable.reduce((s, r) => s + (r.potential_savings || 0), 0)
          : sorted.reduce((s, i) => s + (i.token_estimate || 0), 0);
        const recLabels = {
          HIGH_VALUE: '보존',
          STALE_UNUSED: '정리',
          ARCHIVE: '아카이브',
          HEAVY_UNUSED: '검토',
        };

        return (
          <div className="diet-overlay" onClick={() => setShowDietModal(false)}>
            <div className="diet-modal" onClick={e => e.stopPropagation()}>
              <div className="diet-modal-header">
                <span className="diet-modal-title">🥗 컨텍스트 다이어트</span>
                <span className="diet-saveable">{totalSaveable.toLocaleString()} tokens 정리 가능</span>
                <button className="payload-modal-close" onClick={() => setShowDietModal(false)}>✕</button>
              </div>
              <div className="diet-tabs">
                {[['smart','Smart'],['all','전체 후보'],['large','대용량 (5K+)'],['stale',`오래된 (${STALE_DAYS}일+)`]].map(([id, label]) => (
                  <button key={id} className={`diet-tab ${dietTab === id ? 'active' : ''}`} onClick={() => setDietTab(id)}>{label}</button>
                ))}
              </div>
              {dietTab === 'smart' ? (
                recLoading ? (
                  <div className="diet-empty">사용량을 분석하는 중입니다...</div>
                ) : recError ? (
                  <div className="diet-empty diet-empty-muted">{recError}</div>
                ) : recommendations.length === 0 ? (
                  <div className="diet-empty">추천할 항목이 없습니다 ✓</div>
                ) : (
                  <>
                    <div className="diet-smart-toolbar">
                      <span>{recommendations.length}개 추천 · {smartArchiveable.length}개 정리 후보</span>
                      {smartArchiveable.length > 0 && (
                        <button className="diet-btn-archive" onClick={() => handleArchiveRecommendations(smartArchiveable)}>
                          정리 후보 일괄 아카이브
                        </button>
                      )}
                    </div>
                    <table className="diet-table">
                      <thead>
                        <tr><th>이름</th><th>추천</th><th>호출</th><th>토큰</th><th>근거</th><th>액션</th></tr>
                      </thead>
                      <tbody>
                        {recommendations.map((rec, idx) => (
                          <tr key={`${rec.item?.source_path || rec.item?.name || idx}-${rec.category}`} className={`diet-row-${String(rec.category || '').toLowerCase()}`}>
                            <td className="diet-name" title={rec.item?.source_path}>{rec.item?.name || 'Unknown'}</td>
                            <td>
                              <span className={`rec-badge rec-${String(rec.category || '').toLowerCase()}`}>
                                {recLabels[rec.category] || rec.category}
                              </span>
                            </td>
                            <td className="diet-age">{rec.usage_count}</td>
                            <td className="diet-tokens">{(rec.item?.token_estimate || rec.potential_savings || 0).toLocaleString()}</td>
                            <td className="rec-reason">{rec.reason}</td>
                            <td className="diet-actions">
                              {rec.category !== 'HIGH_VALUE' && (
                                <button className="diet-action-archive" title="아카이브" onClick={() => setArchiveConfirm(rec.item)}>🗄️</button>
                              )}
                              {canInjectToHermes(rec.item) && (
                                <button className="diet-action-copy" title="Hermes Skill로 변환/주입" onClick={() => handleInjectSkillToHermes(rec.item)}>H</button>
                              )}
                              <button className="diet-action-copy" title="다른 워크스페이스로 복사" onClick={() => { setCopyModal(rec.item); fetchWorkspaceList(); }}>📋</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                )
              ) : sorted.length === 0 ? (
                <div className="diet-empty">정리할 항목이 없습니다 ✓</div>
              ) : (
                <table className="diet-table">
                  <thead>
                    <tr><th>이름</th><th>타입</th><th>토큰</th><th>마지막 수정</th><th>액션</th></tr>
                  </thead>
                  <tbody>
                    {sorted.map((item, idx) => (
                      <tr key={idx} className={item.is_large && item.is_stale ? 'diet-row-both' : item.is_stale ? 'diet-row-stale' : 'diet-row-large'}>
                        <td className="diet-name" title={item.source_path}>{item.name}</td>
                        <td className="diet-type">{item.type}</td>
                        <td className="diet-tokens">{(item.token_estimate || 0).toLocaleString()}</td>
                        <td className="diet-age">{item.days_old !== null ? `${item.days_old}일 전` : '—'}</td>
                        <td className="diet-actions">
                          <button className="diet-action-archive" title="아카이브" onClick={() => setArchiveConfirm(item)}>🗄️</button>
                          <button className="diet-action-copy" title="다른 워크스페이스로 복사" onClick={() => { setCopyModal(item); fetchWorkspaceList(); }}>📋</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="diet-footer">
                아카이브: 파일을 <code>~/&#123;workspace&#125;-archive/YYYYMMDD/</code> 로 이동 | 복사: 다른 에이전트 워크스페이스로 복제
              </div>
            </div>
          </div>
        );
      })()}
    </div>
  );
}

export default App;
