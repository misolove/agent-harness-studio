# Agent Harness Studio

An open-source control tower to visualize and modify your AI agent's **Harness** (Memory, Skills, Hooks, MCP, Root Context) via a natural language web dashboard.

## 🧠 Core Philosophy: Harness over Model

We believe that the design of an agent's **Harness** is more critical for practical productivity than the underlying model performance. This studio empowers builders to refine the agent's environment systematically.

![Architecture Diagram](docs/assets/architecture.svg)

### 📺 Demo Video

Check out our [Intro Video](docs/assets/agent-harness-studio-intro.mp4) to see the studio in action.

---

## ✨ Key Features

- **Harness Inspector**: Real-time visualization of distributed configs, memory stores, and skills.
- **Chat Molder**: Modify harness components (like creating new skills) via natural language chat.
- **Web Context Harness (Beta)**: Extract, clean, and integrate web sources as agent context (powered by Firecrawl).
- **Sandbox Mode**: Safely test changes in a mirrored environment (`HERMES_HOME` isolation).
- **Live Diff & Validation**: Review code changes with a high-fidelity diff viewer before applying.
- **Port Management**: Optimized to run alongside tools like Agent Cat (Port 8766).

---

## 🛠 Tech Stack

- **Backend**: FastAPI (Python)
- **Frontend**: React + Vite
- **Engine**: Custom Harness Scanner (Hermes focused)
- **LLM**: Local 9router (Qwen/Gemma compatible)

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Node.js & npm
- A running 9router or OpenAI-compatible local LLM (Port 20128)

### 2. Installation
```bash
git clone https://github.com/misolove/agent-harness-studio.git
cd agent-harness-studio
pip install -r requirements.txt
cd src/ui && npm install && npm run build
```

### 3. Run Studio
```bash
# Production mode
./run.sh

# Sandbox mode (Isolated testing)
./test_sandbox.sh
```

Access the dashboard at `http://localhost:5173`.

---

## 🗺 Roadmap

- [x] Initial PRD & 1-pager
- [x] Core Scanner Engine (Hermes)
- [x] Chat Molder Prototype (Natural Language → Skill)
- [x] Sandbox & Env Badge UI
- [ ] Multi-Agent Support (Claude Code, Codex)
- [ ] Harness Preset Gallery

---

## 📜 Documentation

- [1-pager](docs/1pager.md): Why we built this.
- [PRD](docs/prd.md): Product Requirements Document.
- [Wireframe](docs/wireframe.md): UI/UX Concept design.

---

## 🤝 Contributing

We welcome all contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for more details.

---

## 📄 License

MIT © [letitbe](https://github.com/misolove)
