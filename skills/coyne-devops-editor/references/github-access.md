# GitHub Access Requirements

## Preferred: Fine-grained PAT

Create a fine-grained personal access token for the agent with:

- Repository access: only the two approved repos
- Permissions:
  - Contents: Read and write
  - Pull requests: Read and write
  - Workflows: Read (only if needed)

Use least privilege and rotate periodically.

## Alternative: GitHub App

Use a GitHub App for tighter long-term governance and auditability. This is generally better than PATs but requires extra setup.

## Vercel note

If Vercel is already connected to GitHub repos, the agent usually does not need direct Vercel credentials for PR previews.
