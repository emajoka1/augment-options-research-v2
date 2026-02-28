# Guardrails

## Repository whitelist

Replace placeholders with exact owner/repo names:

- `YOUR_ORG/website-repo`
- `YOUR_ORG/resourcing-app-repo`

Do not work in any other repository.

## Folder whitelist

Allowed edit paths (example):

- `/apps/web`
- `/apps/resourcing`

Do not edit outside approved folders, even inside whitelisted repos.

## Explicitly forbidden change areas

- Billing / subscription code
- Infrastructure / platform config (Terraform, Pulumi, CloudFormation, Helm, etc.)
- Secrets / env files / key material / token handling
- IAM / auth provider admin config

## Dependency policy

No new dependencies (runtime or dev) without explicit approval in current chat.
