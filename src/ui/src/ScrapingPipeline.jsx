/**
 * ScrapingPipeline — visualizes the hybrid scraping pipeline status.
 * Phases: firecrawl → jina → tls → browser
 */

const PHASES = [
  { id: "firecrawl", label: "Firecrawl",    icon: "🔥" },
  { id: "jina",      label: "Jina Reader",  icon: "📖" },
  { id: "tls",       label: "TLS Stealth",  icon: "🔐" },
  { id: "browser",   label: "Browser",      icon: "🌐" },
];

function PhaseStatusIcon({ status, isWinner }) {
  if (isWinner) return <span className="phase-icon winner" title="Winning phase">🏆</span>;
  if (status === "success") return <span className="phase-icon success" title="Success">✓</span>;
  if (status === "error" || status === "failure") return <span className="phase-icon error" title="Failed">✗</span>;
  if (status === "skipped") return <span className="phase-icon skipped" title="Skipped">—</span>;
  return <span className="phase-icon pending" title="Not attempted">○</span>;
}

export default function ScrapingPipeline({ result }) {
  if (!result) return null;

  const { attempts = [], phase_used } = result;

  // Build a map from phase id → attempt data
  const attemptMap = {};
  for (const a of attempts) {
    attemptMap[a.phase] = a;
  }

  return (
    <div className="scraping-pipeline">
      <div className="pipeline-header">
        <span className="pipeline-title">🔍 Scraping Pipeline</span>
        {phase_used && (
          <span className="pipeline-winner-badge">
            Won: {PHASES.find(p => p.id === phase_used)?.label ?? phase_used}
          </span>
        )}
        {result.status === "error" && !phase_used && (
          <span className="pipeline-fail-badge">All phases failed</span>
        )}
      </div>

      <div className="pipeline-phases">
        {PHASES.map((phase, idx) => {
          const attempt = attemptMap[phase.id];
          const status = attempt?.status ?? "pending";
          const isWinner = phase.id === phase_used;
          const durationMs = attempt?.duration_ms ?? null;
          const errorMsg = attempt?.error_message ?? null;

          return (
            <div key={phase.id} className="pipeline-phase-wrapper">
              {/* Connector arrow between phases */}
              {idx > 0 && (
                <div className={`pipeline-arrow ${isWinner ? "arrow-active" : ""}`}>→</div>
              )}
              <div className={`pipeline-phase ${status} ${isWinner ? "winner" : ""}`}>
                <div className="phase-top">
                  <span className="phase-emoji">{phase.icon}</span>
                  <PhaseStatusIcon status={status} isWinner={isWinner} />
                </div>
                <div className="phase-label">{phase.label}</div>
                {durationMs !== null && (
                  <div className="phase-duration">{durationMs}ms</div>
                )}
                {errorMsg && status !== "success" && (
                  <div className="phase-error" title={errorMsg}>
                    {errorMsg.length > 40 ? errorMsg.slice(0, 40) + "…" : errorMsg}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {result.title && (
        <div className="pipeline-result-meta">
          <span className="result-label">Title:</span>
          <span className="result-value">{result.title}</span>
        </div>
      )}
    </div>
  );
}
