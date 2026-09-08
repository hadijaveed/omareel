# Release readiness and independent UX review

## Scope

0.9.2 is an Omarchy 4 beta, not a promise of universal laptop compatibility.
Default fixed-region/window privacy behavior is intentionally unchanged.
Fresh-machine fixtures are automated; actual GPU, camera, permissions,
suspend/resume, monitor docking, and a real cloud account still need testing
on each supported hardware family before broad certification.

## Changes

- Quattro compatibility hotfix (0.9.2): Stop and other action buttons use the
  native `Quickshell.execDetached(argv)` API available on Quattro 4.0.0 instead
  of depending on the newer Commons helper. First widget load safely creates
  the CLI link without replacing another command or changing keybindings.
  Stop and Toggle recover a saved raw take when the recorder has already exited.
  Setup tests forbid the unsupported helper, and workflow tests recover an
  actual synthetic MP4 without signaling an unrelated PID.

- Marketplace security follow-up (0.9.1): all owned QML text sinks explicitly use PlainText. Shared Hint covers process output and endpoint errors. Local native-style dropdown/toggle variants protect device/config labels, and the upload tooltip no longer interpolates a destination through an upstream AutoText sink. Qt regression verifies literal error rendering, zero protected-sink loopback image requests, and a working vulnerable positive control.

- Startup timeout now fails with a persistent error instead of claiming to record an absent file. Partial media is retained for recovery.
- Enabled devices and recording tools are checked before capture; setup also probes GPU information and available storage.
- Camera pixel format, resolution and frame rate are negotiated as a single advertised combination. A requested camera failure aborts startup with recovery instructions.
- System microphone level/mute is preserved by default. Explicit volume management never unmutes.
- Voice model downloads use immutable revisions, SHA-256 verification, retry, timeout and atomic replacement. Invalid model files are not selected.
- CLI linking reports actual failure and refuses to replace unrelated commands; setup/upgrade instructions state the platform and limitations.
- Launcher exposes readiness and persistent startup errors. Setup reports real success/failure. Stop says Save, not Share. Right-click opens controls rather than discarding; discard requires confirmation. Camera layout is grouped with Camera; voice presets are directly selectable. Opening a page resets its scroll position.

## Automated release checks

Run shell syntax, `node tests/helpers.js`, and all four Python regression
suites: setup, workflow, audio, upload. Upload integration uses a local HTTPS
S3-compatible fixture, never a customer's account. QML parser and Omarchy
manifest validation complement these tests but do not prove live UI behavior.
The CI audio dependency is built from pinned upstream RNNoise v1.21.

Before releasing an action change, also run `python3 tests/shell-actions-native.py`
on each supported Quickshell version. This exercises the production Stop button
handlers and CLI launcher in native Quickshell, verifies that a real child
process receives `stop`, and checks literal arguments containing shell syntax.
It accesses no camera, microphone, recording state, or cloud service.

The 0.9.2 hotfix passed this native check on Omarchy 4.0.0-1 with Quickshell
0.3.0.r20.g28771c7-2 and Omarchy 4.0.1-1 with Quickshell 0.3.1-1. Both machines
also passed setup and Stop/recovery checks. A real GPU capture stopped through
the production QML handler saved a moving, playable MP4 on the 4.0.1 machine.
The 4.0.0 test session had only a virtual FALLBACK output, so a new GPU capture
could not be tested there; its existing 94.45-second stranded take was recovered.

## Independent UX assessment

The compact, theme-aware launcher fits Omarchy well. It keeps recording and
sharing separate and offers useful saved-video actions. The remaining gap is
confidence before Start: device names alone cannot prove the correct camera
or a healthy microphone level.

For a newcomer-friendly next iteration, prioritize:

1. **Device check first:** an on-demand camera preview, live microphone meter,
   and five-second record/playback test. Start/stop device access explicitly;
   don't silently open the camera whenever the launcher appears.
2. **One main flow:** Choose capture → Check devices → Record → Saved.
   Keep codec, denoiser engine, VAD controls and storage credentials in advanced
   settings. Camera shape/crop/placement is now directly under Camera.
3. **Plain language:** System audio means “sound from this laptop.” Noise
   cleanup should explain the naturalness tradeoff and let users compare a
   short sample. Avoid claiming a microphone or percentage is universally best.
4. **Predictable stopping:** show first-use guidance about the system-bar Stop
   button, including what happens with fullscreen/autohiding bars. Confirm
   discard and keep saved actions available until dismissed.
5. **Sharing as an optional next step:** first success is a locally playable
   video. Introduce storage setup only when Upload is requested. A successful
   configuration save is different from a successful upload/readback test.
6. **Small-screen/accessibility pass:** keyboard-only operation, visible focus,
   readable error contrast, 125–200% scaling, short-height screens and long
   device names. Prefer wrapped action rows and scrollable content.

These are recommendations, not claims that live meters, camera previews or
a guided wizard have already been implemented.

## Physical release checklist

- Fresh stock Omarchy 4 install on Intel, AMD and NVIDIA/hybrid graphics.
- System default and explicit mic, USB unplug/replug, muted source and laptop mic.
- Built-in and USB cameras, another app holding the camera, 4:3/16:9/low-fps modes.
- Area/window/screen, all camera positions, fractional scaling, dock/undock.
- Playback has moving screen frames, audible voice, correct camera and A/V sync.
- Low storage, startup denial, canceled picker, interrupted cleanup/upload.
- Public and private cloud upload/readback, expiry, thumbnail/player and deletion.
- Install → test take → update → test take; settings and old recordings survive.

Do not mark the physical checklist passed based on fixtures alone.
