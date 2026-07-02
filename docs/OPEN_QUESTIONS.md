# Open Questions

## Product

1. Should Jarvis answer by voice, text notification, menu bar popover, or all
   three?

   When Jarvis is summoned, it will pop out on the screen in a similar way to Siri, and there will be a small typing pane. I will answer by voice, but in settings we can set it to display the text only, or display the text while speaking. It will also be an icon in the Menu. 

   Codex response:
   Agreed. The default UI should be a Siri-like floating panel plus a menu bar icon. I recommend three response modes in Settings: voice only, text only, and voice plus live transcript. The panel should also show clear states: listening, transcribing, thinking, asking approval, and acting.

2. Should it be Mac-only permanently, or should the core be portable later?
   
   For now, MacOS will be enough. I don't like windows anyway 😋

   Codex response:
   Good. We should build Jarvis as Mac-first and not waste early work on Windows. I still recommend keeping the agent core somewhat portable, because that makes testing easier and prevents all logic from being trapped inside Swift UI code.

3. Should the first real demo be Outlook email, browser research, files, or
   coding help?

   It should have the skills to do all of these anyway in the first prototype. You will have time to run localhosts and test it. 

   Codex response:
   I understand the ambition, and the first prototype can include basic tools for all four areas. But one thing needs to be polished enough to trust. My recommendation is: first prototype includes simple typed/voice routing for Outlook, browser, files, and coding, while the polished demo is Outlook read-only summarization. That gives us a real wow moment without giving the model too much power too early.

   My Response: 
   Actually, there's something I haven't told you yet. I have a MacBook Air at home that is always plugged into power and can also generally see all of my files(it's also logged in to onedrive desktop) and it also has all of my Office software in it, such as Outlook and Word. And guess what? My computer and my MacBook Air are connected via a Tailnet. Perhaps we could show a small window of what my Macbook Air screen looks like with Jarvis working there. We have a stable SSH connection anyway. So yeah, that should help for heavy tasks: We could put our Jarvis app on the Macbook Air as well, and it could help with some heavy tasks. This is because my computer is constantly opening and closing, so my Jarvis may not be able to always work on my own computer.

## Voice

1. Is push-to-talk acceptable for the first prototype?

   So we will have a configurable keyboard shortcut in our app Settings to wake Jarvis, but I also want a decent listener for 'Hey Jarvis'. Later, we can set something that only listens to my voice. 

   Codex response:
   Agreed. The keyboard shortcut should ship first because it is reliable and easy to test. In parallel, we can build a local "Hey Jarvis" wake-word experiment. Voice-only activation should come later, after the normal wake-word system is stable.

   My Response:
   No, I say we try to have the 'hey jarvis' as fast as possible. What I meant in my last answer meant that later, we could upgrade this to something that will only listen to my voice, so if somebody else said 'hey jarvis', it wouldn't work. And evenlater, we could do something like only listen to my voice forever, whatever I say, so that nobody could force me to say 'hey Jarvis' and then they could say whatever they want.

2. Should wake-word detection be fully local?

   If Siri can do it, we probably can too. Of course, if testing shows that we will need online speech-to-text, we will use it, because we needed wifi for Jarvis anyway(the model runs online).

   Codex response:
   I agree with the split, but I want to define the terms carefully. The wake-word detector should be local, because always-streaming room audio to the cloud is a bad privacy design. After Jarvis wakes, the actual command transcription can be local or cloud depending on quality, speed, and settings.
   
3. How much false activation is acceptable?

   Virtually zero, but we will work towards that and it will not be needed for the first prototype. But again, if Apple can do it with crappy Siri, so can we. 

   Codex response:
   Virtually zero is the correct target. In practice, no wake-word system reaches literal zero, so the safety design must assume false activations will happen sometimes. A false activation may open the popup, but it must not perform protected actions without confirmation.

4. Should Jarvis keep listening after one command for follow-up questions?

   Jarvis is always listening. However, the popup window will disappear in a settable amount of time, say 10 seconds or 20. 

   Codex response:
   Yes, with one correction: Jarvis should always listen for the wake phrase, but it should not always transcribe everything. After wake, the popup can stay in conversation mode for a configurable timeout like 10, 20, or 30 seconds. During that window, follow-up questions can continue without saying "Hey Jarvis" again.

## Model Backend

1. Should Jarvis use an OpenAI API key stored in Keychain?

   Nope, it should use the OpenAI Oauth system. The user will login to their OpenAI account, and it will work like that. In the app, we can also see the usage limits and remaining credits. 

   Codex response:
   This is the main place where I need to push back. The official OpenAI API documentation still describes API-key authentication for API calls. Codex CLI can sign in with a ChatGPT account and use eligible ChatGPT plans, but that is not the same as a general public OAuth system that any native app can use to spend a user's ChatGPT subscription.

   My recommendation: support two backend modes. Mode 1 is "Codex login mode," where Jarvis delegates coding/project tasks to the official Codex CLI after the user signs in through Codex. Mode 2 is "API key mode," where general Jarvis model calls use an OpenAI API key stored in Keychain. If OpenAI later exposes a proper native-app OAuth flow for API usage, we can swap it in. Usage limits and remaining credits should be designed in the UI, but exact support depends on what OpenAI exposes officially.

   My response:
   Hmm. We do need to talk more about this. I did some research, and there are two ways to leverage this subscription. The first one is via OpenClaw. So I have a question: Since OpenClaw is open-sourced, can we go online and find the part in the OpenClaw code that allows us to use the Codex subscription?
   The second one is via something apparently called Puter.js, and there are apparently more ways for a third-party app to sign in via an automated OAuth bridge, and the third-party calls are directly debited from the user's independent account balance. Come back to me about this topic after your own research.
   
2. Should it call Codex CLI as a local subprocess for coding tasks?

   I mean, I think an app can still run terminal commands, and there doesn't seem to be anything special about Codex CLI that we can't make. However, if there's something special about Codex CLI, feel free to tell me and I'll consider it. It should be fine anyway.

   Codex response:
   There is something special about Codex CLI: it already has project-aware coding behavior, ChatGPT-plan login support, model routing, sandbox/approval patterns, patch editing, terminal output handling, and lots of edge cases we would otherwise have to rebuild. Jarvis should not become just a wrapper around Codex CLI, but for coding tasks I recommend using Codex CLI as a specialist tool when available.

   My response: Sure. Like I said last time(probably later down there in this file somewhere), our Jarvis can decide that a coding task is too much for it to do and instead leverage a better model like 5.5 xhigh in something like Codex CLI. 

   Status (implemented): Jarvis delegates coding/project work to the Codex CLI as a specialist tool via
   `codex.delegate`/`codex.job` (read-only) and now a write-capable tier `codex.delegate_write`/`codex.job_write`
   (workspace-write sandbox, confined to the project folder, gated behind typed confirmation). See
   `docs/SAFETY_MODEL.md` and `codex_delegate_plan(..., write_capable=True)` in `jarvis/tools.py`.

3. Should Realtime API be used early, or only after command execution works?

   It's not an API key we are using anyway. And I don't really understand your question anyway. What do you mean after command execution works? Isn't the command itself written and issued by the AI? And the AI will come back after the command finishes or if it times out, right?

   Codex response:
   By "command execution works," I mean the full tool loop: user asks, AI proposes a tool call, Jarvis checks policy, Jarvis executes the tool, output comes back, and the AI continues or stops. You are right that the AI writes or chooses the command, but the app must be the thing that validates and executes it.

   The Realtime API question is about voice latency, not command authority. Realtime is useful for natural speech-to-speech interaction, but it is not required to prove that Jarvis can safely control tools. My recommendation is: first build wake/record/transcribe -> text agent -> tool execution -> response. Add Realtime later when the action layer is reliable.

   My response: Actually, at first after reading your answer I was still kinda stumped. So then I went online and did some research, so I think the Realtime API you're talking about is this kind of OpenAI real-time chatbot thingy, which is cool. But firstly, if this is an API key, then it probably has API billing. And second, I don't like anything that I can't control. Let's go with your idea for now. If we need Realtime, we'll probably do it later.

4. What is the default low-cost model target?

   This is one of the harder parts. Here's what I'll be thinking. I want GPT 5.5 Low thinking on Fast mode, for the best speed we can with decent wits. Then, if AI thinks that it's met a hard problem, is there a way to integrate it with the Codex app, and type prompts in there? For example, prompt one of my Codex agents in a Codex project in the Codex app to do something in that project directory? This way, we use the model that is in the Codex project, which is usually the ideal model for the thing. Or, if there isn't a Codex project that Jarvis can find, perhaps Jarvis can write a prompt to a different model, like GPT 5.5 xhigh or something, if the intelligence is needed, and choose whether to use Fast mode(which burns 2.5 times the credits). 

   Codex response:
   The current official model list I checked shows GPT-5.2, GPT-5.2-Codex, GPT-5 mini, GPT-5 nano, and related models, not GPT-5.5. So we should make the exact model configurable instead of hardcoding a name.

   Recommended routing:
   - Default assistant model: a fast low-cost model such as GPT-5 mini or the current best small/fast model.
   - Normal hard task: GPT-5.2 or equivalent frontier model with low/medium reasoning.
   - Coding/project task: delegate to Codex CLI or a Codex model when possible.
   - Very hard task: ask for approval before using a high-cost/high-reasoning mode.

   Prompting an existing Codex project is possible in principle, but directly controlling the Codex desktop app by typing into it would be brittle. The cleaner route is to detect the project folder and call Codex CLI with a prompt. If there is an official Codex App automation interface later, we can use that instead.

   My response: 
   Sure. If(like I said above with the model calling) I am wrong about calling these Codex models(the models I can normally choose from in Codex), then we can use these. And they should be faster too. But I still want them to be as smart as possible.

## Safety

1. Which actions should require typed confirmation instead of voice approval?

   I'd say I'd trust you to make those decisions, but you need to tell them to me for me to approve.

   Codex response:
   Proposed typed-confirmation list for your approval:

   - Sending email, messages, posts, forms, or anything external.
   - Uploading, exporting, forwarding, or sharing private data.
   - Revealing credentials, tokens, passwords, cookies, account data, or secrets.
   - Deleting, overwriting, moving, or renaming important files.
   - Running `sudo`, changing system/security/network/VPN/browser/shell/Git/Codex settings, or installing/uninstalling software.
   - Running destructive shell patterns such as `rm -rf`, broad `mv`, broad `chmod`, broad `chown`, disk formatting, keychain changes, or scripts piped from the internet.
   - Payments, purchases, subscriptions, or financial/account changes.

   Voice approval is fine for lower-risk actions, but these should require a visible confirmation in the Jarvis popup.

   My response:
   Sure. This sounds solid. It's a go. 

2. Should private reads like email summaries require approval every time?

   Email summaries and reads, if Jarvis is: 1. Not changing anything, so it's not a write, it's not writing emails; 2. Not exporting it anywhere, like forwarding an email, sending it somewhere other than locally on my computer, then we DON'T need approval. However, if Jarvis is editing anything, exporting anything to anywhere, then it needs my approval.

   Codex response:
   Accepted with one guardrail: once you have granted Outlook/email read permission, Jarvis can summarize locally without asking every time, as long as it does not modify, send, forward, export, download attachments, or copy content outside the local response. The popup should still visibly show when it is reading private content.

3. Should shell commands be disabled until a later milestone?

   What milestone will this be? For example, is this like our next version after our 1st try, or what? I personally don't think so, but if a command can be dangerous, like for example any sudo command or rm -rf command or stuff like that, then of course it should ask me first. 

   Codex response:
   I agree: shell commands should not be totally disabled. In Milestone 1, read-only commands are allowed. Mutating commands can exist early, but only with policy checks and confirmation. Dangerous commands need typed confirmation, not casual voice approval.

   Examples of allowed early commands: `pwd`, `ls`, `find`, `rg`, `cat`, `sed -n`, `git status`, `python --version`.

   Examples requiring confirmation: `rm`, `mv`, `cp` outside a safe folder, `chmod`, `chown`, `git push`, `git reset`, `git checkout` that discards changes, `brew install`, `curl | sh`, `sudo`, `defaults write`, and network/security/VPN changes.

4. Should Jarvis have a strict project-folder sandbox by default?

   Probably not by default, because you never know what I may want Jarvis to do for me. But if you do want a sandbox or if you think it may be useful in some circumstances, feel free to pitch you ideas to me. 

   Codex response:
   I recommend a capability sandbox instead of a strict folder sandbox. Jarvis can work across your Mac, but each class of action has its own permission and risk level. For example, reading visible email is one permission, editing files is another, shell writes are another, and system settings are another.

   I also recommend optional task sandboxes. For coding projects, Jarvis should default to the project folder. For risky file operations, it should stage changes in a review folder before touching the real files.

   My response: 
   This sounds solid to me. If Jarvis can 'default to the project folder' like you said, meaning it will provide its own project folder based on my commands and keep itself in there, then beautiful. Good luck with that, and I hope you can make it happen. But if you can't, tell me and we need to change this. 

   Status (implemented): The write-capable Codex tier (`codex.delegate_write`/`codex.job_write`) runs the Codex CLI
   with a `workspace-write` sandbox whose working directory is resolved through `_safe_root()`, so any project
   directory that escapes the Jarvis workspace root falls back to the workspace root — Codex can create/edit/overwrite
   files only inside the project folder. It stays behind the level-4 typed-confirmation gate and can be disabled with
   `JARVIS_CODEX_WRITE_ENABLED=0`. This delivers the "default to the project folder and keep itself in there" behavior
   for coding tasks. Broader capability sandboxes for other action classes remain future work.

## Technical

1. Swift-first, Python-first, or hybrid Swift plus Python?

   Well, let me ask you back: Which is best for you or for the app? Which do you write best, or which runs faster on the app? If Swift is faster on MacOS, then consider it. If Python is better for running AI, then consider that. Do what you want, but still inform me of your decision and tell me your reason. 

   Codex response:
   My decision: hybrid Swift plus Python.

   Swift/SwiftUI is best for the Mac app: menu bar, permissions, microphone, screen recording, Accessibility, notifications, launch at login, and polished UI. Python is best for the agent core: model calls, tool orchestration, local scripts, testing, and fast iteration. The Swift app can talk to a local Python worker through a local IPC channel.

2. How should the app package Python dependencies if Python is used?

   This is a very technical detail and I will leave it up to you. 

   Codex response:
   Decision: during development, use `uv` with a locked Python environment. For release builds, do not rely on the system Python. Package a self-contained Python worker inside the app bundle, or compile/package the worker into a standalone executable if that proves cleaner. This keeps Jarvis installable on your Mac without fragile dependency setup.

3. Should automation use Accessibility APIs, AppleScript, Shortcuts, or all of
   them?

   Define automation. What are Accessibility APIs, AppleScript, or Shortcuts? Explain and ask me the question again. 

   Codex response:
   Automation means Jarvis taking actions in apps on your behalf.

   Accessibility APIs are macOS permissions that let an app inspect and control UI elements: buttons, text fields, menus, clicks, and keystrokes. They are powerful and generic, but sensitive.

   AppleScript is Apple's scripting system. Some apps expose clean commands like "open this message" or "create this event." It is more reliable than clicking when an app supports it, but not every app supports it well.

   Shortcuts are user-approved workflows in Apple's Shortcuts app. They are good for repeatable actions and safer integrations, but less flexible than full UI control.

   My recommendation: use all three, but in this priority order: app-specific APIs or Shortcuts first, AppleScript second, Accessibility last. Re-asked question: do you approve Jarvis using Accessibility control for apps that do not offer cleaner automation, as long as protected actions still require confirmation?

   My response: 
   Okay. I approve Jarvis using Accessibility, which is totally fine with me. Also, assuming that the 'some apps' that expose clean commands will most likely be Apple's own apps, you can tell me and for example I will login to my email on the Apple Mail app so that Jarvis can access it better. Unless Microsoft was nice enough to put these things into Outlook, but I doubt it. It's Microsoft. C'mon. 

4. Where should audit logs live?

   What is an audit log, and what is it for? Explain and ask me a the question. 

   Codex response:
   An audit log is Jarvis's local record of what happened. It is for debugging, safety, and trust. It should record things like: timestamp, your command transcript, the model's plan, tool calls requested, risk level, approval result, command output summary, and errors.

   It should not store raw microphone audio or screenshots by default. Those should only be saved in a debug mode you explicitly enable.

   My recommendation: logs live locally at `~/Library/Application Support/Jarvis/logs`, are viewable from Settings, and have configurable retention. Re-asked question: should the default retention be 30 days, 90 days, or "until I delete them"?

   My response:
   1. What do you think it should be? 30, 90, or until I suddenly magically remember to delete them(not that smart)? 
   2. For example, could we set a file size limit? Like for example, if the '~/Library/Application Support/Jarvis/logs' folder exceeds 1 GB or 500MB or 2GB or whatever, it will automatically delete the oldest ones until the size gets below that size limit. 

## Reference Notes

These notes were checked while answering the backend questions on 2026-06-02:

- OpenAI API authentication currently documents API keys for API calls: https://platform.openai.com/docs/api-reference/authentication
- OpenAI Realtime API is for low-latency audio/text interaction and transcription: https://platform.openai.com/docs/guides/realtime
- OpenAI audio docs distinguish Realtime voice agents from the simpler speech-to-text -> text model -> text-to-speech chain: https://platform.openai.com/docs/guides/audio
- Codex CLI can be used with ChatGPT plan sign-in or API key setup: https://github.com/openai/codex
- OpenAI model docs currently list GPT-5.2 and related models, not GPT-5.5: https://platform.openai.com/docs/models

Follow-up note:

- A later check found GPT-5.5 references in current OpenAI/OpenClaw-facing materials. Treat the exact model target as configurable and re-check official model availability before wiring live model calls.

## Final Notes

Later when you start coding, make a list of features that you may not make in that specific prototype, so that I can keep track of what cool ideas we had that we didn't want to make just yet. 
