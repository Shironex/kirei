# kirei

A specialized agent team for Claude Code. Automated research → execute workflow with domain-specific specialists.

## Agents

| Agent | Model | Purpose |
|-------|-------|---------|
| `kirei` | opus | General research & investigation |
| `kirei-security` | opus | Security audit (OWASP, auth, injection) |
| `kirei-ui` | opus | UI/UX audit (impeccable skills integration) |
| `kirei-refactor` | opus | Code quality & refactoring plan |
| `kirei-perf` | opus | Performance bottleneck analysis |
| `kirei-arch` | opus | Architecture mapping + Excalidraw diagram |
| `kirei-build` | sonnet | Execute findings — normal/focused tasks |
| `kirei-forge` | opus | Execute findings — complex/multi-file tasks |

## Skill

`/kirei [task description]` — auto-detects type and complexity, spawns the right research agent then execute agent.

## How it works

1. `/kirei` detects task type (security/ui/refactor/perf/arch/general) and complexity (build/forge)
2. Spawns the appropriate `kirei-*` research agent
3. Research agent investigates, validates findings with the user via AskUserQuestion, writes `docs/research/YYYY-MM-DD-topic.md` in the target repo, and produces a structured handoff
4. Spawns `kirei-build` (sonnet) or `kirei-forge` (opus) with the handoff
5. Execute agent implements and verifies

## Install

```bash
# Copy agents to global Claude Code agents directory
cp agents/*.md ~/.claude/agents/

# Copy skill to global skills directory
cp skills/kirei.md ~/.claude/skills/kirei.md
```

## Design decisions

- **Ref MCP for docs** — agents use `mcp__Ref__ref_*` for library documentation; falls back to WebSearch if unavailable. context7 is not used.
- **AskUserQuestion after investigation** — findings are validated with the user once analysis is complete, not before. Prevents scope conversations from slowing down clear tasks.
- **Findings persistence** — every investigation writes to `docs/research/` in the target repo so findings survive across sessions.
- **Two execute tiers** — kirei-build (sonnet) for focused changes, kirei-forge (opus) for complex multi-file work. Research agent recommends which; orchestrator skill decides.
- **Omniscribe integration** — all agents update omniscribe_status and omniscribe_tasks throughout so the UI stays in sync.
