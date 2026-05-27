# Agent Harness Studio — Product Assessment and Skill Converter Direction

Last updated: 2026-05-27

## Current Usefulness

Agent Harness Studio has crossed from "local inventory viewer" into a practical agent-ops tool.
The biggest shift is that it no longer only says "this file is large" or "this file is old"; for
Claude Code it can now say "this skill/subagent is large and has not been invoked recently" or
"this subagent is frequently used, so do not archive it casually."

Current personal/local usefulness: **7/10**.

Current general-product usefulness: **5/10**.

Why it is useful now:
- It gives one place to inspect multiple local agent workspaces.
- It can edit real harness files with backups and optional git history.
- It has a Diet/Smart recommendation path for Claude Code cleanup.
- It can separate high-value active components from unused context weight.
- It has early Agent Runner/Pi read-only execution and diff audit surfaces.

Main limitations:
- The highest-value actions are still visually tucked away inside modals.
- Usage-aware recommendations are currently strongest for Claude Code; other agents degrade safely but lack rich telemetry.
- Smart recommendations are heuristic, not yet a fully explainable lifecycle policy.
- Archive is reversible by filesystem/git, but the UI does not yet make undo/restore confidence obvious enough.
- The next durable value is cross-agent transfer: moving good skills between ecosystems without manual copy/paste.

## Next Product Bet: Skill Converter

The most useful next feature is a **select-and-inject Skill Converter**:

> Pick good Claude Code skills in Studio, convert their metadata into Hermes-compatible shape,
> and inject them into `~/.hermes/skills/{skill-name}/SKILL.md` with auditability.

This is more useful than another passive dashboard because it turns Studio into a migration and
reuse tool. Users can curate what worked in one agent environment and make it available to another.

## Desired UX

Primary flow:
1. Select Claude Code workspace.
2. Open Skills.
3. Sort/filter or use Smart recommendations to find high-value or interesting skills.
4. Click **To Hermes** on a selected skill.
5. Studio writes a converted `SKILL.md` under the Hermes workspace.
6. User switches to Hermes workspace and sees the injected skill.

Secondary flow:
1. Open a Claude Code `SKILL.md` in the editor.
2. Inspect or tweak the content.
3. Click **Inject to Hermes**.
4. If the target exists, Studio asks before overwrite.

## Conversion Policy

Claude Code skill frontmatter commonly includes:
- `name`
- `description`
- `allowed-tools`
- `user-invocable`
- `metadata.category`
- `metadata.tags`
- `triggers`
- `progressive_disclosure`

Hermes scans:
- top-level `name`, `description`, `version`, `platforms`
- nested `metadata.hermes.tags`
- nested `metadata.hermes.category`
- nested `metadata.hermes.requires_tools`
- nested `metadata.hermes.related_skills`

Conversion should:
- Preserve the Markdown body unchanged.
- Preserve obvious generic keys such as `license`, `triggers`, and `progressive_disclosure`.
- Convert tags from comma-separated strings or arrays into `metadata.hermes.tags`.
- Convert category from `metadata.category` or top-level `category` into `metadata.hermes.category`.
- Map Claude `allowed-tools` into best-effort Hermes `requires_tools`.
- Add `metadata.hermes.converted_from` with source agent/path/time.

## Safety Policy

- Never overwrite an existing Hermes skill unless the user confirms overwrite.
- Respect `HARNESS_READONLY=1`.
- Keep conversion local-only; no network calls or LLM required.
- If source skill has companion directories such as `references/`, `templates/`, `scripts/`,
  `modules/`, or `assets/`, copy them next to the injected Hermes skill.
- Log an audit event for every inject.
- If Hermes workspace is a git repo, stage and commit the injected skill directory.

## Done State for First Useful Version

- [x] Backend endpoint accepts `source_path`, target Hermes workspace, overwrite flag, and `dry_run`.
- [x] UI shows **To Hermes** beside Claude skills.
- [x] UI shows **Inject to Hermes** in the Skill editor.
- [x] Smart recommendations can inject recommended Claude skills to Hermes from the action column.
- [x] Existing frontmatter-only converter still works.
- [x] Build passes and a dry conversion can be inspected through API without touching real skills.

## Implemented API

### Convert Current Text

```http
POST /api/convert/skill
```

Body:

```json
{
  "content": "---\nname: sample\n---\n\n# Sample",
  "target": "hermes"
}
```

### Convert And Inject Source Skill

```http
POST /api/convert/skill/inject
```

Body:

```json
{
  "source_path": "/Users/letitbe/.claude/skills/agency-client-interview/SKILL.md",
  "target_workspace": "/Users/letitbe/.hermes",
  "source_agent": "claude-code",
  "overwrite": false,
  "dry_run": false
}
```

Behavior:
- Converts source frontmatter to Hermes metadata shape.
- Writes `~/.hermes/skills/{skill-name}/SKILL.md`.
- Copies companion directories when present: `references/`, `templates/`, `scripts/`, `modules/`, `assets/`.
- Returns `409` if the target skill already exists and `overwrite` is false.
- With `dry_run: true`, returns the converted content and target path without writing files.

Smoke test used:

```bash
curl -sf -X POST 'http://127.0.0.1:8766/api/convert/skill/inject' \
  -H 'Content-Type: application/json' \
  -d '{"source_path":"/Users/letitbe/.claude/skills/agency-client-interview/SKILL.md","target_workspace":"/Users/letitbe/.hermes","source_agent":"claude-code","dry_run":true}'
```

Expected result:
- `status: "dry_run"`
- `skill_name: "agency-client-interview"`
- `path: "/Users/letitbe/.hermes/skills/agency-client-interview/SKILL.md"`

