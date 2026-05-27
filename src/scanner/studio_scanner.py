from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_scanner import BaseHarnessScanner


class StudioScanner(BaseHarnessScanner):
    """Scanner for Agent Harness Studio's own project files."""

    def _add_file(
        self,
        results: List[Dict[str, Any]],
        item_type: str,
        rel_path: str,
        summary: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        path = self.workspace_dir / rel_path
        if not path.exists():
            return
        results.append({
            "type": item_type,
            "name": name or path.name,
            "source_path": str(path),
            "state": "ACTIVE",
            "summary": summary,
            "metadata": {
                "relative_path": rel_path,
                "size_bytes": path.stat().st_size if path.is_file() else 0,
                "exists": True,
                **(metadata or {}),
            },
        })

    def scan_all(self) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []

        for rel_path, summary in [
            ("AGENTS.md", "Workspace operating contract and handoff guidance"),
            ("HANDOFF.md", "Current implementation handoff and next-step context"),
            ("README.md", "Project overview and local run instructions"),
            ("ARCHITECTURE.md", "Technical architecture notes"),
            ("docs/prd.md", "Product requirements"),
            ("docs/api.md", "API reference"),
            ("docs/wireframe.md", "UI and layout reference"),
        ]:
            self._add_file(results, "Root Context", rel_path, summary)

        for rel_path, summary in [
            ("requirements.txt", "Python backend dependencies"),
            ("run.sh", "Local backend and Vite startup script"),
            ("src/ui/package.json", "Frontend package scripts and dependencies"),
            ("src/ui/vite.config.js", "Vite dev server configuration"),
        ]:
            self._add_file(results, "Config", rel_path, summary)

        for rel_path, summary in [
            ("src/server/app.py", "FastAPI API surface, Chat Molder, scanning, saving, and git integration"),
            ("src/ui/src/App.jsx", "Main React Studio interface"),
            ("src/ui/src/App.css", "Main Studio visual system and layout"),
            ("src/ui/src/ScrapingPipeline.jsx", "Web Context scraping result UI"),
            ("src/ui/src/ArchitectureGraph.jsx", "Architecture graph visualization"),
        ]:
            self._add_file(results, "Skill", rel_path, summary, metadata={"category": "Studio Source"})

        scanner_dir = self.workspace_dir / "src" / "scanner"
        if scanner_dir.exists():
            for scanner_file in sorted(scanner_dir.glob("*_scanner.py")):
                self._add_file(
                    results,
                    "Skill",
                    str(scanner_file.relative_to(self.workspace_dir)),
                    f"Agent workspace scanner: {scanner_file.stem}",
                    name=scanner_file.name,
                    metadata={"category": "Scanner"},
                )

        scrapers_dir = self.workspace_dir / "src" / "server" / "scrapers"
        if scrapers_dir.exists():
            for scraper_file in sorted(scrapers_dir.glob("*.py")):
                if scraper_file.name == "__init__.py":
                    continue
                self._add_file(
                    results,
                    "Skill",
                    str(scraper_file.relative_to(self.workspace_dir)),
                    f"Hybrid web scraper component: {scraper_file.stem}",
                    name=scraper_file.name,
                    metadata={"category": "Scraper"},
                )

        docs_dir = self.workspace_dir / "docs"
        if docs_dir.exists():
            md_files = sorted(p.name for p in docs_dir.glob("*.md"))
            if md_files:
                results.append({
                    "type": "Memory Directory",
                    "name": "Studio Docs",
                    "source_path": str(docs_dir),
                    "state": "ACTIVE",
                    "summary": f"{len(md_files)} project reference documents",
                    "metadata": {
                        "dir_name": "docs",
                        "md_files": md_files,
                        "on_demand": True,
                    },
                })

        return self._finalize_items(results)
