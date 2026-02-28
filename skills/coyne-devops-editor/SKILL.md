---
name: coyne-devops-editor
description: Safely edit only Coyne's resourcing app and website repositories with strict repo/folder guardrails, branch-first workflow, and PR-first delivery. Use when asked to implement, fix, refactor, or improve code/content for the resourcing app or website while enforcing: whitelist-only repos, path-scoped edits, no direct pushes to main, no billing/infra/secrets changes, and no dependency additions without explicit approval.
---

# Coyne DevOps Editor

Execute day-to-day engineering edits for Coyne's website and resourcing app with constrained blast radius and predictable review flow.

## Operating Guardrails (non-negotiable)

1. Touch only approved repositories listed in `references/guardrails.md`.
2. Modify files only in approved folders listed in `references/guardrails.md`.
3. Always create a new branch for each task.
4. Never push directly to `main` (or protected default branch).
5. Always open a PR that includes:
   - summary
   - screenshots (if UI changed)
   - test results
   - risk notes
6. Never edit billing, infrastructure, IAM, deployment secrets, environment secrets, or key-management files.
7. Never add new dependencies without explicit user approval in the current conversation.

If any request conflicts with guardrails, stop and ask for clarification before making changes.

## Standard Workflow

1. Validate scope
   - Confirm target repo is whitelisted.
   - Confirm all requested paths are in allowed folders.
   - Reject or trim out-of-scope work.
2. Create branch
   - Branch name format: `feat/<short-slug>-<yyyymmdd>` or `fix/<short-slug>-<yyyymmdd>`.
3. Implement
   - Keep changes focused and minimal.
   - Prefer small, reviewable commits.
4. Verify
   - Run repo tests/lint/type-check where available.
   - Capture output for PR notes.
5. Open PR
   - Use the checklist in `references/pr-checklist.md`.
   - Include summary, screenshots (if UI), test results, and risk notes.
6. Handoff
   - Share PR link and expected Vercel preview behavior.

## GitHub + Vercel Delivery Model

- Create branch + PR on GitHub.
- Vercel should auto-create a Preview Deployment for the PR (when repo integration is already configured).
- Reviewer validates preview URL before merge.
- Merge triggers production deploy (or manual promotion, depending on Vercel project settings).

Do not require direct Vercel access for normal PR-preview workflows.

## Allowed Day-to-Day Work

- Website/app copy, pages, components, styles
- Resourcing features (forms, dashboards, tables)
- Bug fixes
- SEO and performance improvements
- Small safe refactors
- Changelog and release-note generation

## Setup Expectations

Use `references/github-access.md` for access requirements:
- Preferred: GitHub fine-grained PAT scoped only to approved repos with least privilege
- Alternative: GitHub App (better long-term, more setup)
