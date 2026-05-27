import { useEffect, useRef, useState } from 'react';
import mermaid from 'mermaid';
import './App.css';

const API_BASE = "";

export default function ArchitectureGraph({ workspace }) {
  const containerRef = useRef(null);
  const [graphDefinition, setGraphDefinition] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'loose',
    });
  }, []);

  useEffect(() => {
    const fetchGraph = async () => {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/api/graph/mermaid?workspace=${workspace}`);
        if (!res.ok) throw new Error("Failed to load graph");
        const data = await res.json();
        setGraphDefinition(data.mermaid);
        setError(null);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    fetchGraph();
  }, [workspace]);

  useEffect(() => {
    if (graphDefinition && containerRef.current) {
      containerRef.current.innerHTML = '';
      mermaid.render('mermaid-graph-svg', graphDefinition).then((result) => {
        if (containerRef.current) {
          containerRef.current.innerHTML = result.svg;
        }
      }).catch(err => {
        console.error("Mermaid rendering error", err);
      });
    }
  }, [graphDefinition]);

  if (loading) return <div className="glass-panel" style={{ padding: '2rem' }}>Loading Architecture Graph...</div>;
  if (error) return <div className="glass-panel" style={{ padding: '2rem', color: 'var(--accent-red)' }}>Error: {error}</div>;

  return (
    <div className="glass-panel" style={{ padding: '2rem', minHeight: '400px', overflow: 'auto' }}>
      <h2 style={{ marginBottom: '1rem', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '0.5rem' }}>
        Harness Architecture
      </h2>
      <div 
        ref={containerRef} 
        style={{ width: '100%', display: 'flex', justifyContent: 'center' }} 
      />
    </div>
  );
}
