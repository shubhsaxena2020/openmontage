# OpenMontage AI Wiring

This repo already ships the project-wide instruction files most tools need:

- `AGENTS.md`
- `PROJECT_CONTEXT.md`
- `CLAUDE.md`
- `CODEX.md`
- `CURSOR.md`
- `COPILOT.md`
- `.cursor/rules/openmontage.mdc`
- `.github/copilot-instructions.md`
- `.agents/skills/*`
- `.claude/skills/*`
- `.codex/prompts/*`
- `.windsurfrules`

For tools that already understand `AGENTS.md`, the repo is already wired. For tools that need a local config file, the exact file and content are below.

## Per Tool

| Tool | File / Dir to Create or Edit | Exact Content or Line |
|---|---|---|
| Claude Code | `C:\Users\shubh\Projects\OpenMontage\CLAUDE.md` | Already present. Keep the pointer to `AGENT_GUIDE.md` and `PROJECT_CONTEXT.md`. The current file is enough: `MANDATORY: Read [AGENT_GUIDE.md](AGENT_GUIDE.md) before responding to ANY user message.` |
| OpenAI Codex CLI | `C:\Users\shubh\Projects\OpenMontage\AGENTS.md` | Already present. Codex reads this file before work. The current root file already says to read `AGENT_GUIDE.md`. If you want a global default, create `~/.codex/AGENTS.md` with reusable rules, but no repo change is required. |
| OpenCode | `C:\Users\shubh\Projects\OpenMontage\opencode.json` | Create this file with:<br><br>```json\n{\n  \"$schema\": \"https://opencode.ai/config.json\",\n  \"instructions\": [\"AGENTS.md\", \"PROJECT_CONTEXT.md\"]\n}\n``` |
| Gemini CLI | `C:\Users\shubh\Projects\OpenMontage\.gemini\settings.json` | Create this file with:<br><br>```json\n{\n  \"context\": {\n    \"fileName\": [\"AGENTS.md\", \"PROJECT_CONTEXT.md\"]\n  }\n}\n``` |
| Qwen Code | `C:\Users\shubh\Projects\OpenMontage\.qwen\settings.json` | Create this file with:<br><br>```json\n{\n  \"context\": {\n    \"fileName\": [\"AGENTS.md\", \"PROJECT_CONTEXT.md\"]\n  }\n}\n```<br>Qwen also accepts `QWEN.md`; this settings file is the cleanest way to point it at the repo's existing AGENTS-based contract. |
| Kiro CLI | `C:\Users\shubh\Projects\OpenMontage\AGENTS.md` | No extra file is required because Kiro supports `AGENTS.md` directly. If you want a Kiro-native workspace file anyway, create `C:\Users\shubh\Projects\OpenMontage\.kiro\steering\openmontage.md` with: `Read AGENT_GUIDE.md first, then PROJECT_CONTEXT.md.` |
| Goose | `C:\Users\shubh\Projects\OpenMontage\AGENTS.md` | No extra file is required because Goose loads `AGENTS.md` and `.agents/skills/` automatically. If you want a Goose-only hint file, create `C:\Users\shubh\Projects\OpenMontage\.goosehints` with: `Read AGENT_GUIDE.md first and treat it as the source of truth.` |
| Hermes Agent | `C:\Users\shubh\Projects\OpenMontage\AGENTS.md` | No extra file is required because Hermes loads `AGENTS.md` directly. If you want the highest-priority Hermes file, create `C:\Users\shubh\Projects\OpenMontage\.hermes.md` with: `Read AGENT_GUIDE.md first, then PROJECT_CONTEXT.md.` |
| Google Antigravity (`agy`) | `C:\Users\shubh\Projects\OpenMontage\AGENTS.md` and `C:\Users\shubh\Projects\OpenMontage\.agents\skills\` | No extra file is required for orchestrator behavior because Antigravity reads `AGENTS.md` and discovers `SKILL.md` files under `.agents/skills/`. If you need Google Cloud MCP wiring, add `C:\Users\shubh\Projects\OpenMontage\.agents\mcp_config.json` separately. |
| Cursor | `C:\Users\shubh\Projects\OpenMontage\.cursor\rules\openmontage.mdc` | Already present. Keep the frontmatter and the AGENT_GUIDE pointer. The current file is enough: <br><br>```md\n---\ndescription: OpenMontage project rules\nglobs: [\"**/*\"]\nalwaysApply: true\n---\n\n# OpenMontage\n\nMANDATORY: Read `AGENT_GUIDE.md` before responding to ANY user message.\n``` |
| GitHub Copilot | `C:\Users\shubh\Projects\OpenMontage\.github\copilot-instructions.md` | Already present. Keep the repository instructions pointer to `AGENT_GUIDE.md` and `PROJECT_CONTEXT.md`. The current file is enough: `**MANDATORY: Read [AGENT_GUIDE.md](../AGENT_GUIDE.md) before responding to ANY user message.**` |

## Existing Project Files That Already Do The Job

- `AGENTS.md` is the repo-wide orchestrator contract.
- `CLAUDE.md`, `CODEX.md`, `CURSOR.md`, and `COPILOT.md` are already thin pointers back to `AGENT_GUIDE.md` and `PROJECT_CONTEXT.md`.
- `.cursor/rules/openmontage.mdc` already makes Cursor apply the OpenMontage contract across the repo.
- `.github/copilot-instructions.md` already gives Copilot repo-wide instructions.

## Source References

- OpenAI Codex AGENTS.md instructions: https://learn.chatgpt.com/docs/agent-configuration/agents-md
- OpenCode instructions config: https://opencode.ai/docs/rules/
- Gemini CLI context files and settings: https://google-gemini.github.io/gemini-cli/docs/cli/gemini-md.html and https://google-gemini.github.io/gemini-cli/docs/get-started/configuration.html
- Qwen Code settings and QWEN.md: https://qwenlm.github.io/qwen-code-docs/en/users/configuration/settings/ and https://qwenlm.github.io/qwen-code-docs/en/users/features/memory/
- Kiro steering and AGENTS support: https://kiro.dev/docs/steering/
- Goose context engineering and AGENTS.md: https://goose-docs.ai/docs/guides/context-engineering/
- Hermes context files: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/context-files.md
- Google Antigravity CLI skills/rules: https://antigravity.google/docs/skills/ and https://antigravity.google/docs/rules-workflows/
- Cursor rules: https://cursor.com/docs/rules
- GitHub Copilot repository instructions: https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-custom-instructions and https://docs.github.com/copilot/customizing-copilot/adding-custom-instructions-for-github-copilot
