# cua-driver Feasibility Evaluation for Jarvis

Author: research teammate (autonomous run), 2026-07-02
Status: evaluation only — no code adopted, no dependency added.
Scope: whether Jarvis should adopt `cua-driver` (from `github.com/trycua/cua`) to
replace or augment its current UI-automation stack for Microsoft Teams and Chrome
reading.

> **Bottom line up front.** cua-driver is a genuinely interesting, MIT-licensed,
> element-indexed background automation driver that targets *exactly* the class
> of failure Jarvis keeps hitting (occluded / wrong-Space / wrong-surface
> capture). But it is young (open-sourced ~April 2026, Rust port at sub-1.0
> `v0.6.x` as of this writing), it is built on **undocumented private macOS SPIs**
> that trade one kind of fragility for another, and its accessibility-tree
> approach is *weakest* precisely where Jarvis needs it most today (Teams running
> as a **web app inside Chrome**). Recommendation: run a **narrow, read-only
> prototype against the single worst case now**, keep the current stack as the
> fail-closed source of truth, and defer any broad adoption until after the Rust
> core rewrite. Do **not** rip out the existing OCR/AppleScript path.

I did **not** install or run cua-driver for this evaluation (see
[§6 Testing honesty](#6-testing-honesty)); all capability claims below are from
documentation and source review, cross-checked against Jarvis's own source and
bug history.

---

## 1. What it is

`cua-driver` is the background computer-use driver inside the open-source
`trycua/cua` project — "open-source infrastructure for Computer-Use Agents" that
lets an agent drive full desktops on macOS, Windows, and Linux. The driver is the
piece that actually clicks/types/scrolls/inspects a running app; the surrounding
`cua` repo also ships sandboxes, SDKs, and benchmarks that are **not** relevant
to Jarvis.

**Addressing model — the core idea.** Instead of screen coordinates or OCR, the
primary addressing mode is **element-indexed**. The agent calls `get_window_state`
(a snapshot), receives an accessibility tree with per-element indexes plus a
screenshot ("set-of-mark" / `som` mode), then acts by index:

```
click({ pid, window_id, element_index })
```

Element indexes are refreshed on every snapshot, so the pre-action and
post-action window state are part of the contract. Because a click fires the
underlying **AX action directly**, it "works on hidden and occluded targets and
[doesn't] involve coordinates" — it does not move the user's cursor, does not
steal focus, and does not drag the user across Spaces. This is the headline
property: *background* computer-use.

**How it delivers events (the private-SPI part).** Under the hood it uses:

- **`SLEventPostToPid`** — a private SPI in
  `/System/Library/PrivateFrameworks/SkyLight.framework` (the undocumented C
  layer WindowServer uses to drive every on-screen window). It "posts synthesized
  events to one specific process without going through the HID tap," i.e.
  bypasses `IOHIDPostEvent`/`CGEventPost` so the shared cursor doesn't move.
- **yabai's focus-without-raise pattern** — two `SLPSPostEventRecordTo` calls to
  make a target AppKit-active for event routing while its window stays where it
  is in the z-stack.
- A `_AXObserverAddNotificationAndCheckRemote` private API to keep an app's
  accessibility tree live even when the window is occluded.

The project author is explicit that this was reverse-engineered: *"None of this
is documented. Half of it doesn't even appear in any Apple header."* Keep that
sentence in mind for [§4 Risk](#4-risk-assessment).

**Run modes.** The same handlers are reachable three ways:

- **MCP stdio server** — `cua-driver mcp` (registers as an MCP tool provider; a
  Claude-Code-computer-use compat mode also exists).
- **Long-running daemon** — `cua-driver serve` (also launchable as
  `open -n -g -a CuaDriver --args serve`); holds persistent OS handles.
- **One-shot CLI** — `cua-driver call <tool> '<json-args>'`; "the stdio MCP
  server and shell commands call the same driver handlers."

**Tool surface (documented):** `launch_app({bundle_id})`, `get_window_state({pid,
window_id})`, `list_apps`, `click({pid, window_id, element_index})`, `type_text`,
`scroll`, `screenshot({pid, window_id})`, `check_permissions`, `cua-driver stop`.

**Implementation & platforms.** Two implementations exist: a **Swift** reference
driver for macOS (AppKit + Accessibility.framework) and a **Rust** cross-platform
port, `cua-driver-rs`, covering macOS/Windows/Linux (Windows adds a UIPI-bypass
crate; Linux uses `portal-libei` on Wayland). Visual feedback is provided by
`cursor-overlay` / `pip-preview` crates so the agent's actions are visible without
interrupting the primary display.

**Permissions.** One-time grant of **Accessibility** *and* **Screen Recording** to
the driver app (CuaDriver.app) in System Settings → Privacy & Security.

**License & maturity.** MIT (trycua open-sourced the framework ~April 2026 under
MIT). The Rust driver is versioned `cua-driver-rs-v0.6.x` as of ~late June 2026 —
**sub-1.0, roughly one quarter old at the time of this evaluation**, with frequent
(≈weekly) releases. Read that as: actively developed, but early, with expected API
churn and thin real-world battle-testing.

## 2. What it would (and would not) replace in Jarvis

### 2a. Jarvis's current automation stack (verified from source)

- **`JarvisNativeBrowserReader.swift`** — reads Chrome's active tab by driving it
  with **`NSAppleScript`**: it runs `execute javascript "... document.body.innerText ..."
  in theTab` to scrape page text. Its failure taxonomy (all handled explicitly in
  source) is telling: `not_running`, `no_window`, `automation_not_allowed`
  (AppleScript errors `-1743`/`-1723`), `chrome_javascript_unavailable`, and the
  Teams-specific `teams_page_text_unavailable`. It depends on the user having
  granted **Automation** permission *and* enabling Chrome's *"Allow JavaScript
  from Apple Events."*
- **`JarvisNativeOutlookReader.swift`** — captures a window with
  **ScreenCaptureKit** (`SCShareableContent` / `SCStream`) and runs **Vision**
  OCR (`VNRecognizeTextRequest`), with a **CoreGraphics** fallback
  (`CGWindowListCopyWindowInfo` + `CGWindowListCreateImage`) that crops by
  screen bounds. Source labels for the result include `native_vision_ocr_screen`
  and `native_vision_ocr_screen_display_fallback`. This is the coordinate/OCR path
  and it is the fragile one.
- **`JarvisNativeBrowserPermission.swift`** — the Automation-permission probe for
  the above.

### 2b. The pain, in Jarvis's own words

`codex_task_queue.md` and `JARVIS_BUG_BACKLOG.md` document a long, ongoing fight
against exactly the failure classes cua-driver targets. Concrete examples:

- **Wrong-Space / wrong-surface OCR.** The visible-screen probe repeatedly
  captured the wrong macOS Space or the wrong window and had to be hardened to
  *fail closed*: e.g. `codex_task_queue.md` records the fallback being hardened
  "against the live wrong-Space OCR shape (`Slide 1 of 68`, `Local assistant
  prototype`, and OCR-mangled `teams cloud microsott`)", and another entry where
  "native OCR clearly captured Codex/ChatGPT/other Chrome text" while Chrome
  reported a Teams URL, forcing a `browser_focus_not_verified` refusal.
- **A whole family of honest-failure states that exist *because* the current
  approach can't confirm what's on screen:** `browser_focus_not_verified`,
  `native_capture_failed`, `teams_page_text_unavailable`,
  `chrome_javascript_unavailable`, and the subject-level
  `assignment_subject_mismatch` (Jarvis read `Lesson 2: The Geography of Greece`
  when asked for the newest *Music* assignment). Dozens of task-queue entries are
  incremental hardening of these states.
- **AppleScript/Automation brittleness** against Chrome (the `-1743`/`-1723`
  denials and the `chrome_javascript_unavailable` path).
- **Stage Manager** is an explicit design constraint (`JARVIS_BUG_BACKLOG.md:457`:
  the overlay must remain "usable with Stage Manager"), and Stage Manager is one
  of the things that moves windows out from under coordinate-based capture.

> **Calibration note.** The task brief mentioned a specific
> `SCStreamErrorDomain -3811` capture error. I searched `JARVIS_BUG_BACKLOG.md`
> and `codex_task_queue.md` and **did not find that literal error code**; the
> ScreenCaptureKit failures surface in Jarvis as `native_capture_failed`. I'm
> flagging this rather than citing a code I couldn't verify.

### 2c. Where cua-driver maps on — and where it does not

**Would genuinely help:**

- **Confirming what surface is actually frontmost / present.** cua-driver's
  `get_window_state` + `list_apps` give a structured, per-`pid`/`window_id` view
  of real windows and their AX elements. That is a far stronger "is Teams actually
  here?" signal than cropping a display and OCR-ing it, and directly attacks the
  wrong-Space / wrong-surface `browser_focus_not_verified` class.
- **Occluded / background targets.** Because it fires AX actions by index rather
  than clicking coordinates, it can (in principle) read and drive a Teams or
  Outlook window that is *not* frontmost, without stealing the user's focus or
  yanking them across Spaces — the exact thing Stage Manager and multi-Space
  setups break today.
- **Native desktop apps** (Outlook desktop, Finder, System Settings, the Teams
  *desktop* app): for these, a live AX tree is dramatically more reliable than
  OCR and doesn't need Chrome's Automation grant at all.

**Would NOT help (be honest about scope):**

- **Nothing above the UI layer.** Wake-word ("Hey Jarvis"), STT, model routing,
  Codex integration, the safety gate — cua-driver is purely about *driving apps*.
  It replaces a *sensor/effector*, not the brain.
- **The marquee case is its weakest case.** Jarvis's headline target is **Teams
  running as a web app inside Chrome**, read via `document.body.innerText`.
  cua-driver reads the **accessibility tree**, not the DOM. For a complex
  Chromium/Electron web SPA the AX tree is what VoiceOver would see — often
  incomplete, lagging, or virtualized — and the project's own writeup flags
  Chromium/Electron caveats directly: *"Chromium coerces synthetic right-clicks on
  web content to left-clicks,"* Electron accessibility trees *"pause when the
  app's window is occluded"* unless a private observer API is used, and Chrome's
  renderer only accepts events posted through the `SLEventPostToPid` channel plus
  a `(-1,-1)` "primer click" to satisfy its user-activation gate. In other words:
  the background-occluded reading Jarvis most wants is precisely where the AX
  approach is most caveated for Chrome web content. **This must be the thing the
  prototype tests first**, because if it doesn't work for Teams-in-Chrome, the
  biggest single win doesn't materialize. (A cleaner win may be to point Jarvis at
  the **Teams desktop app** instead, where the AX tree is a first-class citizen —
  worth testing as an alternative.)
- **It does not read raw page text the way Jarvis does today.** Switching to
  cua-driver for Teams would mean re-deriving assignment content from AX elements,
  not `innerText`; the `assignment_subject_mismatch` honesty logic would need to
  be re-expressed against tree nodes.

## 3. Integration approach

Two shapes are plausible given how Jarvis already works (it shells out to `codex`
as a subprocess, so subprocess integration is familiar):

1. **One-shot CLI per action** (`cua-driver call click '{...}'`) — simplest,
   matches the `codex` pattern.
2. **Persistent daemon + thin client** — spawn/supervise `cua-driver serve` once,
   then issue `get_window_state` / `click` / `type_text` against the running
   daemon (via MCP stdio or `cua-driver call`, which hit the same handlers).

**Recommendation: the persistent daemon, not one-shot CLI.** Reasoning that is
specific to this tool, not generic:

- The **snapshot→act contract is stateful**. `element_index` values are only
  meaningful relative to the last `get_window_state`; a fresh process per click
  throws away that state and re-pays cold-start plus TCC-permission re-detection
  every call. The daemon exists precisely because it "holds persistent OS
  handles."
- The private **AX observers** (`_AXObserverAddNotificationAndCheckRemote`) that
  keep occluded trees live are inherently long-lived; they don't fit a
  spin-up-per-click model.
- A single supervised daemon is also the smallest **audit surface** for a
  component that holds Accessibility + Screen Recording — one process to
  watch/restart/version-pin rather than a fork per action.

**Where the client lives:** today, the **Python worker** would supervise the
daemon and call it. But note the strategic fit: the Jarvis Rust core rewrite is
in flight, and cua-driver's cross-platform driver is *itself* `cua-driver-rs`
(Rust). The cleanest long-term integration is the **Rust core supervising /
speaking to cua-driver-rs**, keeping the private-SPI linkage in a separate process
(CuaDriver.app), never linked into `Jarvis.app` itself. So: prototype from Python
now, but design the client thin and process-boundary'd so it ports to the Rust
core unchanged.

**Do not** embed cua-driver's private-framework linkage inside `Jarvis.app`.
Running it as its own app/daemon keeps `Jarvis.app`'s own signing/notarization and
TCC story clean (see next section).

## 4. Risk assessment

| Risk | Severity | Notes |
|---|---|---|
| Private/undocumented SPI fragility | **High** | `SLEventPostToPid`, `SLPSPostEventRecordTo`, `_AXObserverAddNotificationAndCheckRemote` are reverse-engineered, header-less. Any macOS point release can change WindowServer internals with no deprecation warning, no docs, no compile error. |
| Project maturity | **Moderate–High** | Open-sourced ~April 2026; Rust driver at sub-1.0 `v0.6.x`; ~1 quarter old; small maintainer base; frequent releases imply churn. |
| Chromium/web-content coverage | **Moderate** | AX-tree approach is caveated for exactly Jarvis's Teams-in-Chrome case (occlusion pauses, right-click coercion, user-activation gate). |
| Extra permission surface | **Moderate** | Needs its *own* Accessibility + Screen Recording grants. |
| Notarization / distribution | **Low–Moderate** | Notarization (malware scan) is not blocked by private-API use; **Mac App Store** distribution *is* — a hard blocker only if Jarvis ever wants MAS. |
| Operational (long-lived privileged daemon) | **Low–Moderate** | Another background process holding privileged handles to supervise/restart/pin. |
| Licensing | **Low** | MIT — permissive, no copyleft concern. |

Expanded on the two that matter most:

- **You are trading fragility for fragility, not fragility for stability.**
  Jarvis's current stack (AppleScript, ScreenCaptureKit, Vision, CoreGraphics) is
  ugly but built on **public, documented, Apple-supported** APIs — when it breaks,
  it usually breaks by returning an error Jarvis can catch and fail-closed on
  (that's what the whole honest-failure taxonomy is). cua-driver moves the
  automation onto **undocumented private symbols**. When *those* break after a
  macOS update, the failure mode is "a private function disappeared or silently
  changed behavior," which is harder to detect and impossible to get an Apple fix
  for. This is the single most important honest caveat in this whole document.
- **Permission surface and the "explain why" burden.** TCC grants are
  per-binary/bundle-id, so CuaDriver.app needs its **own** Accessibility + Screen
  Recording grants, *separate from* Jarvis's. That does **not conflict** with
  Jarvis's existing grants (independent bundle IDs), but it **doubles** the
  sensitive-permission surface the user must grant and Jarvis must justify — and
  the backlog already stresses explaining precisely why Accessibility is needed
  (`JARVIS_BUG_BACKLOG.md`, Calendar/System §5: "Jarvis must explain exactly why
  and what it enables"). Two apps each holding Accessibility + Screen Recording is
  a bigger thing to explain and a bigger thing to audit.

## 5. Phased adoption recommendation

**Phase 0 — keep the current stack (now).** Do not remove any OCR/AppleScript
code. The honest-failure machinery around Teams represents dozens of hard-won
backlog fixes; it is Jarvis's fail-closed source of truth and must remain so
during any experiment.

**Phase 1 — narrow, read-only prototype against the single worst case (do this
now; cheap, isolated, high signal).**
- Stand up cua-driver as its own daemon and use it purely as a **read-only
  sensor**: `list_apps` + `get_window_state` to answer *"is Teams actually the
  frontmost/present surface, and what does its element tree say?"*
- **Test the hard case first: Teams-in-Chrome.** Run cua-driver's snapshot
  head-to-head against the existing OCR path on the exact
  wrong-Space/wrong-surface scenarios the backlog documents (background/occluded
  Chrome window while another Space is frontmost). Success criterion: does the
  element snapshot correctly identify the Teams assignment where OCR captured the
  wrong Space? If it fails here (plausible, given the Chromium AX caveats), the
  marquee win is not real — record that honestly.
- **Also test the Teams desktop app** as an alternative target, where AX is a
  first-class citizen and cua-driver should shine.
- Minimal PoC: ~1 day of work — a small Python shim that spawns `cua-driver
  serve`, calls `get_window_state`, and dumps a comparison against the current
  probe's output on a handful of recorded failure cases. No changes to Jarvis's
  production path.

**Phase 2 — augment, never blind-replace (only if Phase 1 wins).**
Use cua-driver as an **additional evidence source that the existing honesty gate
cross-checks**: cua-driver says "Teams window present, 'Music assignment' element
found" *and* OCR/DOM agrees → higher confidence; disagreement → keep failing
closed exactly as today. This preserves the fail-closed invariant instead of
betting it on a 3-month-old dependency.

**Phase 3 — consolidate after the Rust core lands.** Only once the Rust core
rewrite is in place, consider promoting `cua-driver-rs` to the primary UI-driving
layer (both are Rust; the integration is cleanest there, with the private-SPI
linkage isolated in a separate process).

**Timing judgment.** The Phase 1 prototype is **worth doing now** — it's isolated,
low-cost, and aimed at a real, well-documented pain point, and it will tell you
whether the AX approach even works for Teams-in-Chrome. **Broad adoption is not
worth it right now**: (a) mid-rewrite is a bad time to also swap the automation
substrate; (b) the private-SPI fragility argues for the thinnest, most-isolated
integration, which the Rust core provides; (c) the current stack's honesty logic
must be preserved regardless of what drives the UI underneath.

## 6. Testing honesty

I did **not** install or run cua-driver during this evaluation. A GUI login
session is present in this environment, but a real hands-on test would require
downloading/building CuaDriver.app and granting it **Accessibility + Screen
Recording on the user's real machine** — a security-sensitive, hard-to-reverse
permission grant to a third-party binary that I will not perform unprompted, and
that would not be reproducible from a clean checkout anyway. I also did not write
a throwaway prototype script, because without those grants it could not verify
anything concrete, and a script that only *looks* like a test would be worse than
none. Every capability claim above is sourced from documentation and from reading
Jarvis's own source and bug history, not from execution.

## Sources

- trycua/cua repo: <https://github.com/trycua/cua>
- cua-driver README: <https://github.com/trycua/cua/blob/main/libs/cua-driver/README.md>
- cua-driver product page: <https://cua.ai/cua-driver>
- "Inside macOS window internals" (SkyLight / SLEventPostToPid / yabai; Chromium & Electron caveats): <https://cua.ai/blog/inside-macos-window-internals>
- "Build your own operator on macOS, part 2": <https://cua.ai/blog/build-your-own-operator-on-macos-2>
- DeepWiki cua-driver overview (daemon-proxy model, Swift + Rust impls): <https://deepwiki.com/trycua/cua/6-cua-driver:-background-computer-use>
- Release history (cua-driver-rs v0.6.x): <https://github.com/trycua/cua/releases>
- MIT license / open-sourcing (~April 2026): <https://pulse24.ai/news/2026/4/29/13/trycua-open-sources-cua-agent-framework>
- Jarvis source: `swift-shell/Sources/JarvisMacNative/JarvisNativeBrowserReader.swift`, `JarvisNativeOutlookReader.swift`, `JarvisNativeBrowserPermission.swift`
- Jarvis history: `JARVIS_BUG_BACKLOG.md`, `codex_task_queue.md`
