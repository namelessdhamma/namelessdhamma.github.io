# ND Browserless GitHub Actions Gateway

Purpose: provide a Browserless control path that does not depend on Make or TinyFish.

## Transport

ChatGPT -> GitHub connector -> public repository issue edit -> GitHub Actions -> Browserless MCP.

The repository is public, so standard GitHub-hosted runners are free for this workflow. Browserless usage remains subject to the Browserless account plan.

## Security

- Only issue events initiated by GitHub actor `namelessdhamma` are accepted.
- Workflow permissions are limited to `contents: read` and `issues: write`.
- Browserless credentials are never committed.
- The only required repository secret is `BROWSERLESS_API_TOKEN`.
- Gateway output is returned as comments on the control issue.

## Implemented commands

The active issue-title transport accepts:

- `[browserless] profiles`
- `[browserless] start-github-auth`
- `[browserless] verify-github-profile`

ChatGPT can trigger a command by editing the control issue title/body. No Make scenario is required.

The GitHub-auth flow creates a Browserless profile named `nd-github`, opens a 100-second interactive live URL, monitors the same Browserless session, saves the profile automatically when authenticated GitHub state is detected, and then performs a fresh-session reuse check.

## Manual bootstrap

One account-owner action is required before first use:

GitHub repository -> Settings -> Secrets and variables -> Actions -> New repository secret.

Name: `BROWSERLESS_API_TOKEN`

Value: the Browserless API token. Do not put the token in an issue, commit, or chat.

After that, ChatGPT can run the gateway and the only normal human step is completing an interactive login when a live Browserless URL is intentionally requested.
