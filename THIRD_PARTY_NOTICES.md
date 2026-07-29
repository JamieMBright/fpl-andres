# Third-Party Notices

FPL Andres vendors the following development-only design guidance. These files guide
coding agents and are not part of the application runtime bundle.

## Anthropic Frontend Design Skill

- Source: `https://github.com/anthropics/skills`
- Revision: `b29e7cf65e5cb78a5ac33d582270551bc74a14eb`
- Path: `skills/frontend-design`
- License: Apache License 2.0
- Local files:
  - `.github/skills/frontend-design/SKILL.md`
  - `.github/skills/frontend-design/LICENSE.txt`
- SHA-256:
  - `1608ea77fbb6fc30d13a97d12cfa8ebf31358d40f0dd97beed24829d6b3f45dd`
  - `0d542e0c8804e39aa7f37eb00da5a762149dc682d7829451287e11b938e94594`
- Modifications: none.

## Vercel Labs Web Interface Guidelines

- Source: `https://github.com/vercel-labs/web-interface-guidelines`
- Revision: `4e799d45c17aec1498c269287a83b9dba22b966b`
- Path: `command.md`
- License: MIT
- Local files:
  - `.github/skills/web-design-guidelines/references/web-interface-guidelines.md`
  - `.github/skills/web-design-guidelines/references/LICENSE.txt`
- SHA-256:
  - `eea73cb6dd46fee9faec9973e8e7fe198b5f07ec326f14d276a56e50287e1cab`
  - `6cd1609c9c12233507cdd2ce0d32e9a721e3c27494951be06b90090deeeeb7af2`
- Modifications: none to the vendored reference or license. The project-authored
  `.github/skills/web-design-guidelines/SKILL.md` wrapper reads the local reference
  instead of fetching mutable instructions at review time.

## Supabase Agent Skills

- Source: `https://github.com/supabase/agent-skills`
- Revision: `1ad9aaeb49caafd9e95c0a91116f71890eebbc53`
- Paths: `skills/supabase`, `skills/supabase-postgres-best-practices`
- Versions: `0.1.5`, `1.4.0`
- License: MIT
- Local files: `.agents/skills/supabase/**`,
  `.agents/skills/supabase-postgres-best-practices/**`,
  `.agents/skills/SUPABASE_AGENT_SKILLS_LICENSE.txt`, `skills-lock.json`
- Installation: copied project-locally for GitHub Copilot with
  `npx skills add supabase/agent-skills --agent github-copilot --skill supabase supabase-postgres-best-practices --copy --yes`.
- Modifications: none to vendored skill files. Repository instructions override generic
  iterative-development advice because this free-plan deployment has one hosted
  production database and no hosted staging project.
