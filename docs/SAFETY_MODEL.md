# Safety Model

Jarvis needs a safety model before it receives broad computer control.

## Core Principle

The model is an advisor and planner. The app is the authority. Every real
computer action must pass through Jarvis-owned policy checks.

## Risk Levels

### Level 0: Local Conversation

Examples:

- Answer a question.
- Summarize a command transcript.
- Explain what it can do.

Allowed without confirmation.

### Level 1: Read-Only Local Context

Examples:

- Take a screenshot.
- Read visible window text.
- List file names in an approved folder.
- Open an app without reading private content.

Allowed after the user has granted the relevant permission, with audit logging.

### Level 2: Private Read Access

Examples:

- Summarize email.
- Read calendar events.
- Inspect browser pages with logged-in accounts.
- Read documents outside the project folder.

Allowed after the user has granted the relevant app/content permission, with
visible status and audit logging. It must remain local. Editing, forwarding,
exporting, downloading attachments, or transmitting content escalates to a
higher level.

### Level 3: Reversible Changes

Examples:

- Create a draft email.
- Move a file to a staging folder.
- Create a calendar draft.
- Open a website and fill a form without submitting.

Requires confirmation before execution.

### Level 4: External, Destructive, or Sensitive Actions

Examples:

- Send email or messages.
- Delete, rename, overwrite, or move important files.
- Change system, security, network, VPN, browser, shell, Git, or Codex settings.
- Reveal credentials or tokens.
- Download, upload, export, or share private data.
- Run shell commands that modify state.

Requires strong confirmation. Some actions should require a typed passcode or
manual UI approval.

Approved strong-confirmation list:

- Sending email, messages, posts, forms, or anything external.
- Uploading, exporting, forwarding, or sharing private data.
- Revealing credentials, tokens, passwords, cookies, account data, or secrets.
- Deleting, overwriting, moving, or renaming important files.
- Running `sudo`, changing system/security/network/VPN/browser/shell/Git/Codex settings, or installing/uninstalling software.
- Running destructive shell patterns such as `rm -rf`, broad `mv`, broad `chmod`, broad `chown`, disk formatting, keychain changes, or scripts piped from the internet.
- Payments, purchases, subscriptions, or financial/account changes.
- Delegating a coding task to Codex with **write access** to the project folder (see Codex Delegation Tiers).

## Codex Delegation Tiers

Jarvis delegates coding and project work to the OpenAI Codex CLI (`codex exec`) as a specialist
tool. There are two tiers, distinguished by sandbox and risk level:

- **Read-only delegation** — tools `codex.delegate` (synchronous) and `codex.job` (async). Built by
  `codex_delegate_plan(...)` with `--sandbox read-only`. Codex can read files in the resolved project
  folder and answer, but can never create, edit, or overwrite a file or run a state-changing command.
  These stay at their existing low read-only classification, exactly as before.
- **Write-capable delegation** — tools `codex.delegate_write` (synchronous) and `codex.job_write`
  (async). Built by `codex_delegate_plan(..., write_capable=True)` with `--sandbox workspace-write`, so
  Codex may create, edit, and overwrite files. This is a **Level 4** action and always requires typed
  confirmation (`JARVIS APPROVE`), consistent with the other approved typed-confirmation categories
  (running commands with real side effects, system/settings changes).

Both tiers keep `--ask-for-approval never`: Jarvis's own typed-confirmation gate is the
human-in-the-loop approval layer, not Codex's internal one (this matches the headless automation
combination OpenAI's docs describe). Both tiers resolve the target directory through `_safe_root()`,
which forces any path that escapes the Jarvis workspace root back to that root, so a write-capable run
can only ever touch files inside the project folder. The safety classifier also flags natural-language
phrasing that clearly asks Codex to make and save real changes ("have Codex fix this and save it",
"let Codex actually implement this") as Level 4, so a normal read-only "ask Codex" question never
silently gains write access. Write-capable delegation is enabled by default (the project owner
pre-approved it) and can be turned off with `JARVIS_CODEX_WRITE_ENABLED=0`.

## Required Safeguards

- Local wake-word detection before cloud audio.
- Visible status indicator whenever listening, recording, thinking, or acting.
- Kill switch in the menu bar.
- Local pause mode that stops `/api/command` at the server boundary while
  preserving health, mode, policy, tools, readiness, self-check, and audit
  endpoints.
- Optional start-paused launch through `JARVIS_START_PAUSED=1` or
  `scripts/run_dashboard.py --paused` for cautious local runs.
- Pause mode should still classify attempted commands so audit entries preserve
  the attempted risk level even when execution is refused.
- Per-tool permissions.
- Per-app permissions.
- Audit log with timestamps, transcript, plan, requested tools, and outcomes.
- Audit logging should redact obvious password, token, API key, secret,
  credential, and bearer-token values before writing JSONL.
- Audit logging should also redact common standalone key-shaped values such as
  `sk-...`, legacy GitHub token prefixes like `ghp_...`, and fine-grained
  `github_pat_...` tokens.
- Audit logging should redact env/header-style secret labels such as
  `OPENAI_API_KEY=...`, `MY_TOKEN=...`, and `x-api-key: ...`.
- Audit logging should redact values under sensitive structured keys such as
  `token`, `Authorization`, and `OPENAI_API_KEY`.
- Audit logging should cap very long string values after redaction so command
  output or pasted text cannot bloat the local JSONL log.
- Audit logging should normalize JSON-unsafe detail values such as bytes,
  set-like containers, and path/object values into redacted JSON-safe values.
- Audit reads should redact unreadable raw JSONL lines before returning them to
  the dashboard/API.
- Audit reads should tolerate non-UTF-8/corrupted raw lines and surface them as
  unreadable redacted entries instead of crashing.
- Confirmation prompts for protected actions.
- Secrets stored only in Keychain.
- No browser-cookie scraping.
- No hidden credential extraction.
- No private endpoint dependency.
- Localhost static assets must stay inside the packaged static folder.
- The dashboard must bind only to loopback hosts by default. Non-loopback
  hosts such as `0.0.0.0` require an explicit `JARVIS_ALLOW_NON_LOOPBACK=1`
  opt-in.
- Requests must use a loopback `Host` header, preventing DNS-rebinding-style
  access through non-local hostnames.
- Read-only shell commands must run through an argv allowlist rather than raw
  shell interpretation.
- Shell chaining, piping, backgrounding, command substitution, and redirection
  must stop at confirmation or stronger.
- Mutating flags or scripts on otherwise read-only shell tools, such as
  `find -delete`, `find -exec`, `find -fprint`, `sed -i`, `sed 'w file'`, and
  external sed/awk script files, must stop at strong confirmation.
- Shell redirection tokens, including quoted redirects, must stop at strong
  confirmation.
- Natural-language commands that request downloading, installing,
  uninstalling, deleting, removing, overwriting, important setting changes,
  credential exposure, cookie reads, or Keychain access must require
  confirmation gates before any typed tool can execute.
- Natural-language high-risk assessments should explain the reason category,
  such as external transmission, file/software changes, protected settings,
  credentials/cookies/Keychain, or payments.
- Code-runner shell commands such as `python3 -c ...` and `swift build` must
  not auto-execute as read-only commands.
- Natural-language requests for privileged or destructive shell-like execution
  such as `run sudo ...` or `run rm -rf ...` must require strong confirmation
  even without a `shell:` prefix.
- Shell commands that reference paths outside the project folder must stop for
  confirmation, and secret-looking paths, bare sensitive filenames such as
  `id_rsa`, secret-bearing filenames such as `secrets.txt` or `token.json`,
  and Git pathspecs such as `HEAD:.env` must require strong confirmation.
- Helper APIs that accept root folders should fall back to the project root
  when given outside-project paths unless a later permissioned capability
  explicitly expands the boundary.
- Localhost request bodies and audit-list limits must be bounded.
- Command, plan, and mode POST endpoints must require `application/json`
  request bodies.
- Malformed JSON POST bodies must be rejected before any command routing,
  preview routing, mode changes, or tool execution.
- Invalid request sizes, including negative `Content-Length`, must be rejected.
- Audit writes, reads, and retention trimming must be safe under threaded
  localhost request handling.
- Pause-mode state must be safe under threaded localhost request handling.
- Localhost responses should include `X-Content-Type-Options: nosniff` and
  `Cache-Control: no-store`.
- Dashboard responses should include a restrictive Content Security Policy
  limited to same-origin scripts, styles, API calls, and data-image icons.
- Verification must avoid trusting stale already-running workers; current-code
  checks should use runtime/mode metadata or a fresh temporary worker.
- 90-day audit retention target plus a 1 GB default size cap.
- No raw audio or screenshots stored by default.

## Prompt-Injection Handling

Jarvis must treat text from webpages, emails, PDFs, screenshots, terminal
output, and documents as untrusted data.

If untrusted content says things like "ignore previous instructions," "reveal
secrets," "send this file," or "change settings," Jarvis should quote the
suspicious text, identify the source, and ask the user before continuing.

The prototype includes a read-only `safety.injection_scan` tool for this first
step. It flags likely instruction overrides, secret extraction, hidden
behavior, authority impersonation, external transfers, and
destructive/settings changes in untrusted text without following those
instructions.

## Email Example

For "Hey Jarvis, could you check my email?":

Allowed first step:

- Open Outlook.
- Capture visible inbox screenshot.
- Summarize visible unread senders and subjects.

Needs approval:

- Opening individual messages.
- Reading private message bodies.
- Downloading attachments.
- Drafting a reply.

Needs strong approval:

- Sending a reply.
- Forwarding content.
- Deleting or archiving messages.
- Exporting email content.
