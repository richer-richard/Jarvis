# MacBook Air Remote Worker

Leo has an always-plugged MacBook Air that can see OneDrive files, has Office
apps installed, and is connected to the MacBook Pro through a Tailnet. This is
a strong future direction for heavy or long-running Jarvis tasks.

## Intended Split

- MacBook Pro: front-end/controller, voice capture, approval UI.
- MacBook Air: long jobs, Office automation, Codex tasks, background workflows.

## Prototype Boundary

The current prototype should not execute remote commands automatically. It
should only record the architecture and leave room for a worker protocol until
remote planning, approvals, and audit identity are designed.

Manual reachability evidence:

- 2026-06-04 04:18 CST: Codex ran a bounded read-only Tailnet SSH probe with
  batch mode and a 5 second connect timeout:
  `ssh -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new hongyi@100.72.212.85 uname -a`
- Result: success. The host identified as `Hongyis-MacBook-Air.local`, Darwin
  25.5.0, arm64.
- This proves the Tailnet helper idea is reachable from the current MacBook Pro
  context, but it does not yet mean Jarvis has a safe remote-worker execution
  feature.

## Safety Requirements

- Remote worker must authenticate the controller.
- Remote actions must appear in the local Jarvis approval UI.
- Remote audit logs must identify which machine acted.
- Remote writes, exports, setting changes, and shell mutations need the same
  strong-confirmation policy as local actions.
- Remote screen preview should be read-only until a separate control policy is approved.

## Future Worker API Sketch

- `GET /api/worker/health`
- `POST /api/worker/plan`
- `POST /api/worker/execute` with approval token
- `GET /api/worker/audit`
- `GET /api/worker/screen-preview`
