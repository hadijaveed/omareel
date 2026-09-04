# Omareel

Loom-style screen recording for [Omarchy](https://omarchy.org). Record an
**area**, a **window**, or your **screen** with an optional camera frame and
the microphone you choose, get the background noise removed, and decide per
video whether it stays local or goes up as a shareable link, with a title.

<p align="center">
  <img src="docs/launcher.png" width="360" alt="Omareel launcher: Area / Window / Screen, microphone, system audio, camera bubble, noise removal, upload">
  <img src="docs/settings.png" width="360" alt="Omareel settings: frame rate, quality, codec, noise removal engine, sharing destination">
</p>

While recording an area, a small floating bar sits in a safe strip at the top
or bottom of the screen:

<p align="center">
  <img src="docs/recording-bar.png" width="430" alt="● 00:03 · Area 1600x900  Stop  Discard">
  <br>
  <img src="docs/done-bar.png" width="560" alt="✓ Saved · upload to share  Upload  Rename  Open  Copy">
</p>

The Recordings page lists every take, newest first; click one to rename it,
upload it, or copy its link or path:

<p align="center">
  <img src="docs/recordings.png" width="360" alt="Recordings: Sprint demo · Today 13:08 · 0:03 · Local">
</p>

## What it does

- **Record** an area (drag, or click a window to snap to it), a single visible
  window through reliable fixed-region capture, or the focused monitor. An
  optional portal mode keeps covered windows captured but is resize-sensitive.
  GPU encoding through `gpu-screen-recorder`.
- **Camera frame** in any corner of the recording: a rounded 16:9 frame
  (the Loom look), a circle, or a portrait card, in four sizes, any camera.
  It works the same way in every mode, like a screen studio: the camera is
  recorded to its own file and a self-view floats in the corner where the
  frame will be. Area, Screen, and reliable Window captures include that
  self-view as-is; a portal Window capture draws the frame in after Stop.
- **Pick your microphone** and your system-audio source from dropdowns.
- **Voice clean-up.** RNNoise reduces noise, with a small, time-aligned
  natural component to preserve speech detail. Neutral EQ and two-pass
  loudness normalisation keep the result consistent.
- **Instant playback for viewers.** The MP4 index is moved to the front so
  browsers start playing immediately and seek with range requests.
- **Share only what you choose.** After Stop the banner offers **Upload**;
  give the video a title and the link lands on your clipboard. Everything
  else stays in `~/Videos/Omareel`. Flip *Upload every recording* in the
  launcher if you would rather have every take uploaded automatically.
- **Name your videos.** A recording is saved under a random UUID. Rename it
  from the banner, the launcher, or the Recordings page and the mp4,
  thumbnail and raw take move together (`Sprint demo: API v2` →
  `Sprint-demo-API-v2.mp4`). The UUID stays the object key on the upload
  destination, so links never change and are never guessable.
- **Destinations:** Cloudflare R2, AWS S3, Backblaze B2, any S3-compatible
  endpoint, or any rclone remote you already have. A small player page
  (titled with your title) is uploaded next to the video.
- **Configure everything from the bar**, including the upload credentials.
  Credentials are written to rclone's own config file, never to the plugin's.

## Install

```bash
omarchy plugin add https://github.com/hadijaveed/omareel.git --enable
~/.config/omarchy/plugins/hadijaveed.omareel/bin/omareel setup --link
```

`setup` checks dependencies, downloads the RNNoise models, and symlinks
`omareel` into `~/.local/bin` so keybindings can call it. Then add a keybinding
in `~/.config/hypr/bindings.lua`:

```lua
o.bind("SUPER + SHIFT + R", "Omareel", "omareel toggle")
```

Optional but recommended for the most reliable noise removal (see below):

```bash
sudo pacman -S noise-suppression-for-voice
```

For uploads:

```bash
sudo pacman -S rclone
```

Everything else (`gpu-screen-recorder`, `ffmpeg`, `slurp`, `mpv`, `jq`,
`wl-clipboard`) ships with Omarchy.

### Omarchy menu entries (optional)

Add to `~/.config/omarchy/extensions/omarchy-menu.jsonc` to get
Super+Space → Capture → Omareel:

```jsonc
"trigger.capture.omareel": {"icon":"󰑊","label":"Omareel","aliases":["omareel","record"],"description":"Record a video and share a link"},
"trigger.capture.omareel.stop": {"icon":"","label":"Stop recording","when":"omareel active","action":"omareel stop"},
"trigger.capture.omareel.cancel": {"icon":"󰜺","label":"Discard recording","when":"omareel active","action":"omareel cancel"},
"trigger.capture.omareel.area": {"icon":"󰆞","label":"Record area","when":"! omareel active","action":"omareel start area"},
"trigger.capture.omareel.window": {"icon":"","label":"Record window","when":"! omareel active","action":"omareel start window"},
"trigger.capture.omareel.screen": {"icon":"󰍹","label":"Record screen","when":"! omareel active","action":"omareel start screen"},
"trigger.capture.omareel.last": {"icon":"","label":"Copy last link","action":"omareel last"},
"trigger.capture.omareel.open": {"icon":"","label":"Open recordings","action":"omareel open"},
"trigger.capture.omareel.settings": {"icon":"","label":"Omareel settings","action":"omarchy-shell omareel settings"}
```

## Using it

**Bar button:** click → launcher (Stop while recording) · right-click → copy
the last link (Discard while recording) · middle-click → open the recordings
folder.

**Launcher:** pick Area / Window / Screen. Toggle the microphone, system audio
and camera and pick devices underneath each; the camera row also sets the
frame size, shape and corner. Toggle noise removal and automatic upload. The
gear opens settings.

**After Stop:** the floating banner (and the launcher) show the finished
recording with **Upload**, **Rename**, **Open** and **Copy**. Upload asks for
a title, renames the files to it, uploads the video, thumbnail and player
page, and copies the link. Rename only renames. The banner stays until you
upload it, close it (✕), or start the next recording; ✕ keeps the file local.

**Recordings page:** the *Recordings* button in the launcher (or
`omarchy-shell omareel recordings`) lists everything in `index.jsonl`. Click
a row for a name field plus Upload / Copy link or path / Open. Renaming a
video that is already shared re-uploads its player page with the new title.

The same from a terminal: `omareel upload last --title="…"`,
`omareel rename <file.mp4> "…"`, `omareel copy <file.mp4>`.

**Window/Screen controls:** the Omareel timer in the system bar is the Stop
control, shown as a red **REC · STOP** pill so no floating controls are burned
into the video. Click it to stop or right-click to discard. Drag the pill to
move the Omareel widget anywhere along the bar; the whole bar can be configured
at the top or bottom.
Screen mode captures the monitor's usable rectangle, excluding its reserved
system bar. Other windows or notifications inside the selected region are
visible in KMS recordings; keep the intended content in place.

**Keyboard:** `omareel toggle` opens the launcher when idle and stops the
recording when one is running.

## Sharing setup

Open the gear, choose a destination, fill in the fields, **Save
credentials**, then **Test upload**. The test uploads a probe file, fetches it
back through the public URL, and deletes it.

| Destination | You need |
|---|---|
| **Cloudflare R2** | Account ID, bucket, an R2 API token (Object Read & Write), and the bucket's public URL (custom domain or the `r2.dev` subdomain). Free egress, so viewers cost nothing. |
| **AWS S3** | Region, bucket, access key + secret, public URL (bucket website endpoint or CloudFront). |
| **Backblaze B2** | Region (e.g. `us-west-004`), bucket, application key ID + key, the bucket's friendly URL. |
| **S3-compatible** | Endpoint URL, bucket, key + secret, public URL. MinIO, Wasabi, Hetzner, etc. |
| **Existing rclone remote** | A `remote:path` you already configured with `rclone config` (Google Drive, Dropbox, OneDrive…). Leave the public URL empty and the share link comes from `rclone link`. |

The bucket must allow public reads of the uploaded objects. Objects are named
by the recording's UUID, so links are not guessable and survive local renames.
Uploads set explicit `Content-Type` and `Content-Disposition: inline` headers
and the player page carries Open Graph video tags, so Slack, Teams and
friends unfurl the link as a page with a poster and a click opens the player.

Credentials are stored by `omareel remote save` in
`~/.config/rclone/rclone.conf` (mode 600) under the `[omareel]` remote.
`~/.config/omarchy/omareel.json` holds only the non-secret settings, which
makes it safe to keep in a dotfiles repo.

## Camera layouts

Camera layout is built from four independent controls, available in the
launcher whenever Camera is on:

- **Position:** all four corners, top/bottom center, and left/right center.
- **Frame:** Landscape 16:9, Rectangle 4:3, Portrait 8:9, or Circle.
- **Crop:** Full, Close (1.25×), or Tight (1.5×). Crops remain centered and
  never stretch the camera image.
- **Size:** Small, Medium, Large, or Extra large.

Useful starting points are Circle + Medium + Close at bottom-right for product
demos, Rectangle + Large + Close at right-center for a presenter layout, and
Portrait + Medium + Tight at left-center when the UI needs the right side.
Every layout stays inside a 3 % safe margin. Omareel snapshots the selection
when recording begins and uses the same size, crop, mask, and position math for
the live self-view and Window-mode export.

## Noise removal

Microphone and desktop audio are captured as separate tracks. Only the
microphone goes through the speech chain: convert to 48 kHz mono → apply a
configurable pre-gain → cut rumble below 70 Hz → denoise → neutral tone →
light compression → two-pass `loudnorm` to −16 LUFS → a −1.5 dB true-peak
safety limiter. Desktop audio is mixed back afterwards at 50 %, so denoising
never damages music or application sound.

Omareel also reapplies the configured microphone source level (80% by default)
when each recording starts. Browser calls can otherwise leave USB microphones
at a much quieter system level, making the final loudness pass raise the room
noise along with the voice.

**Strength** controls the whole cleanup profile: *Natural* uses minimal FFT
processing, while *Clean* (the default) and *Strong* use RNNoise voice
isolation. Clean combines 85% denoised speech with 15% time-aligned original
speech. A soft gate, guided by the cleaned voice, reduces that natural
component during pauses so it does not restore room noise. Strong uses the
fully denoised signal and firmer levelling, at the cost of more altered tone.
No preset adds bass or cuts the presence band by default.
Very quiet takes have make-up gain capped at 18 dB, so a mostly silent take
does not amplify faint room noise up to speech level.

Omareel measures the installed LADSPA model's delay, feeds it in 10 ms blocks,
flushes the tail, and removes the measured delay before mixing. The installed
1.21 model adds 20 ms on top of VAD look-ahead; its internal Dry Mix does not
account for that model delay. Omareel therefore leaves internal Dry Mix at
zero and aligns the paths itself. Failed latency calibration triggers the
fallback engine rather than an unaligned mix. The default VAD threshold is
50%, with 300 ms tail grace and 50 ms retroactive grace.

The engine setting `auto` selects transparent `afftdn` cleanup for Natural and
RNNoise LADSPA for Clean and Strong when the plugin is installed. If LADSPA is
unavailable, it tries the downloaded RNNoise model before falling back to FFT
cleanup. An explicit engine selection overrides that behavior:

1. **RNNoise LADSPA plugin** from the `noise-suppression-for-voice` package.
   Aggressive suppression for a difficult room.
2. **ffmpeg `arnndn`** with the models `omareel setup` downloads. ffmpeg
   9.0.1's `arnndn` intermittently emits NaN samples, which makes the AAC
   encoder abort, so Omareel retries it a few times before falling back.
3. **ffmpeg `afftdn`**, a plain FFT denoiser. The Clean and Strong profiles
   follow it with a soft downward expander: room tone stays down between words
   even after loudness levelling, without a hard gate clipping syllables.

The raw take is kept as `<id>.raw.mp4` (toggle in settings), so a bad clean-up
can always be redone with `omareel finalize <raw.mp4>`.
Turning Voice clean-up off also bypasses tone, compression, and loudness
normalisation; only the short capture-pop mute and audio encoding remain.

Saved actions stay available until Close or the next recording. Recording,
processing, and sharing commands are serialized; a duplicate click cannot
start a second picker or finalize the same file twice. Settings writes are
also serialized so rapidly changing multiple options preserves each change.

### Regression checks

Run `python3 tests/audio-regression.py` for local DSP tests (FFmpeg and the
RNNoise LADSPA plugin required), `python3 tests/workflow-regression.py` for
isolated workflow tests, and `node tests/helpers.js` for card placement and
configuration helpers. Fixtures are synthetic and uploads are mocked; tests
never upload a real recording. DSP checks cover timing at multiple look-ahead
settings, the final partial frame, silence, cleanup Off, and untouched desktop
audio. A listening check on your own microphone remains necessary to choose
between Natural, Clean, and Strong.

## CLI

```
omareel start [area|window|screen] [--no-mic] [--desktop-audio] [--webcam] [--no-denoise] [--no-upload]
omareel stop | cancel | dismiss | toggle | status | last | open
omareel upload last|<video.mp4> [--title="…"]   # share one recording
omareel rename last|<video.mp4> "<title>"        # rename mp4 + thumbnail + raw
omareel copy   last|<video.mp4>                  # copy its link, or path if local
omareel devices                      # JSON: mics, outputs, cameras
omareel doctor                       # JSON: deps, active denoiser, upload state
omareel config get | merge '<json>'  # read / deep-merge omareel.json
omareel remote save|status|test      # upload credentials → rclone.conf
omareel finalize <raw.mp4> [out.mp4]
omareel setup [--link]

omarchy-shell omareel open|close|toggle|settings|recordings|status|refresh
```

Headless smoke test (no picker):

```bash
omareel start area --region=1280x720+200+200 --no-upload; sleep 4; omareel stop
```

## Config

`~/.config/omarchy/omareel.json`, all editable from the settings page:

```jsonc
{
  "outputDir": "~/Videos/Omareel",
  "fps": 30,                  // 30 | 60
  "codec": "h264",            // h264 (plays everywhere) | hevc | av1
  "quality": "very_high",     // medium | high | very_high | ultra
  "windowCaptureMode": "region", // region (reliable) | portal (occlusion-safe)
  "mic": true,          "micDevice": "default",
  "micVolumePercent": 80,   // restored at the start of every take
  "desktopAudio": false, "desktopDevice": "default",
  "webcam": false,       "webcamDevice": "auto",
  "webcamSize": "medium",     // small | medium | large | xlarge (16/22/30/40 % of the recording height)
  "webcamShape": "frame",     // frame (16:9) | classic (4:3) | portrait (8:9) | circle
  "webcamPosition": "bottom-right", // 4 corners | top/bottom-center | center-left/right
  "webcamZoom": "full",       // full | close (1.25x) | tight (1.5x)
  "denoise": true,
  "denoiseEngine": "auto",    // auto | ladspa | arnndn | afftdn | off
  "denoiseModel": "bd",       // arnndn model: bd (general) | sh (speech)
  "denoiseStrength": "normal", // light/natural | normal/clean | strong
  "micGainDb": 0,             // optional processing pre-gain after capture
  "vadThreshold": 50,         // LADSPA voice gate, %
  "vadGraceMs": 300,          // keep word and sentence endings
  "vadRetroactiveMs": 50,     // recover beginnings; adds this much denoiser latency
  "desktopMix": 0.5,          // desktop level when mixed with a microphone
  "keepRaw": true,
  "upload": {
    "auto": false,              // true: upload every recording without asking
    "provider": "none",       // none | r2 | s3 | b2 | s3compat | existing
    "accountId": "", "region": "", "endpoint": "",
    "bucket": "", "prefix": "", "remote": "",
    "publicBase": "",
    "playerPage": true
  }
}
```

## How it works

```
launcher / keybind / menu
        │
        ▼
bin/omareel start …          gpu-screen-recorder (VAAPI/NVENC); ffmpeg records the camera to
                             <id>.cam.mp4 and tees it to an mpv self-view
        │  state.json: picking → recording        ← Panel.qml shows the floating bar
        ▼
bin/omareel stop
        ├─ ffmpeg: mic → highpass → selected denoiser → voice EQ/compression
        │          desktop audio → mix after cleanup → 2-pass loudnorm/limiter → +faststart
        │          + camera overlay for optional portal Window recordings
        ├─ thumbnail, index.jsonl  (<uuid>.mp4 until renamed)
        ├─ wl-copy path, notification
        │  state.json: processing → done (banner: Upload / Open / Copy)
        ▼
bin/omareel upload last --title="…"       (Upload button, or upload.auto)
        ├─ rclone copyto  <id>.mp4 <id>.jpg <id>.html
        └─ wl-copy URL, notification
           state.json: uploading → done → idle
```

The shell plugin never talks to the recorder directly. `bin/omareel` writes
`$XDG_RUNTIME_DIR/omareel/state.json` on every phase change and both QML files
watch it, so the bar button, the floating controls, and the CLI always agree.

## Known limits

- Floating controls are part of the screen, so Window and whole-screen
  recordings hide them; the movable system-bar timer and the keybinding still
  stop the recording. Area recordings use a safe top or bottom strip and hide
  the card when neither is outside the selected region.
- **A camera can only stream to one program at a time.** If Chromium,
  Firefox or a call app holds it (a Meet, Slack or Teams call, or a tab that
  was granted the camera), the camera cannot start. Omareel says so in the
  launcher ("In use by Chromium") and in a notification, and records without
  the camera. End the call or close that tab, then record again.
- Reliable Window mode records a fixed on-screen rectangle. Keep the selected
  window visible and in place during the take; covered pixels are recorded as
  covered. This avoids portal freezes caused by dynamic window resizing.
- Optional portal Window mode remains available in settings for occlusion-safe
  capture. Portal recordings with a camera are re-encoded once to composite
  the camera frame and may fail if the portal renegotiates its dimensions.
- No pause/resume yet.

## Developing

`BarWidget.qml`, `Panel.qml`, and `Omareel.js` hot-reload on save; manifest
changes need `omarchy restart shell`. Shell log:
`ls -t /run/user/1000/quickshell/by-id/*/log.log | head -1`. Recorder and
ffmpeg log: `$XDG_RUNTIME_DIR/omareel/omareel.log`.

## License

MIT
