import React from 'react';

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

export default EditorErrorBoundary;
