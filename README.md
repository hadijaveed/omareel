# Omareel

Loom-style screen recording for [Omarchy](https://omarchy.org). Record an
**area**, a **window**, or your **screen** with an optional camera frame and
the microphone you choose, get the background noise removed, and decide per
video whether it stays local or goes up as a shareable link, with a title.

<p align="center">
  <img src="docs/launcher.png" width="360" alt="Omareel launcher: Area / Window / Screen, microphone, system audio, camera bubble, noise removal, upload">
  <img src="docs/settings.png" width="360" alt="Omareel settings: frame rate, quality, codec, noise removal engine, sharing destination">
</p>

While recording, a small floating bar sits at the top of the screen:

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

- **Record** an area (drag, or click a window to snap to it), a window
  (snap to its rectangle), or the focused monitor. The capture is Omarchy's
  own recorder path: the same picker, the same `gpu-screen-recorder` flags
  (60 fps, GPU encode), the same one-pass audio clean-up. Omareel adds the
  controls, titles, uploads and share links on top.
- **Camera frame** in any corner of the recording: a rounded 16:9 frame
  (the Loom look), a circle, or a portrait card, in four sizes, any camera.
  It is one floating window that the capture sees, just like Omarchy's own
  recorder: what you see is what is recorded, and Super+drag moves it
  anywhere during the take.
- **Pick your microphone** and your system-audio source from dropdowns.
- **Audio like the stock recorder.** Microphone and system audio merged into
  one track, the capture pop muted, one-pass loudness normalisation. RNNoise
  clean-up exists behind an experimental switch in settings, off by default.
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

## Noise removal (experimental, off by default)

When switched on, the chain is: cut rumble below 80 Hz → denoise → tone correction → two-pass
`loudnorm` to −16 LUFS. RNNoise at full strength thins a voice out and makes
it sound shrill (measured on a real take: spectral centroid 2.7 → 3.4 kHz,
+2 dB above 3 kHz). Blending the raw signal back in fixes the tone but lets
the room noise back in with it, so instead the suppression stays at full
strength and an EQ pair (−3 dB high shelf above 4 kHz, +1.5 dB low shelf
below 200 Hz) puts the body back; measured against the raw take the bands
land within half a decibel. **Strength** in settings: *Normal* as above,
*Light* keeps 30 % of the raw signal for the most natural voice in a quiet
room, *Strong* is full suppression without the low-shelf lift for very noisy
rooms. Two-pass loudness normalisation applies one linear gain instead of the
single-pass dynamic mode, which pumps and exaggerates sibilance.

The engine setting `auto` picks, in order:

1. **RNNoise LADSPA plugin** from the `noise-suppression-for-voice` package.
   Reliable and the same plugin a live PipeWire "clean mic" setup uses.
2. **ffmpeg `arnndn`** with the models `omareel setup` downloads. ffmpeg
   9.0.1's `arnndn` intermittently emits NaN samples, which makes the AAC
   encoder abort, so Omareel retries it a few times before falling back.
3. **ffmpeg `afftdn`**, a plain FFT denoiser.

The raw take is kept as `<id>.raw.mp4` (toggle in settings), so a bad clean-up
can always be redone with `omareel finalize <raw.mp4>`.

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
  "mic": true,          "micDevice": "default",
  "desktopAudio": false, "desktopDevice": "default",
  "webcam": false,       "webcamDevice": "auto",
  "webcamSize": "medium",     // small | medium | large | xlarge (16/22/30/40 % of the recording height)
  "webcamShape": "frame",     // frame (16:9, rounded) | circle | portrait (8:9 card)
  "webcamCorner": "bottom-right", // bottom-left | top-right | top-left
  "denoise": true,
  "denoiseEngine": "auto",    // auto | ladspa | arnndn | afftdn | off
  "denoiseModel": "bd",       // arnndn model: bd (general) | sh (speech)
  "denoiseStrength": "normal", // light (30 % raw blended back) | normal (full + EQ) | strong (full, no low lift)
  "vadThreshold": 50,         // LADSPA gate, %; lower if word starts get clipped
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
bin/omareel start …          omarchy-capture-region picker → gpu-screen-recorder -k auto -f 60 -fm cfr
                             (+ mpv camera window in the corner of the region, as Omarchy's recorder)
        │  state.json: picking → recording        ← Panel.qml shows the floating bar
        ▼
bin/omareel stop
        ├─ ffmpeg: trim first frame → mute capture pop → loudnorm → +faststart (video stream-copied)
        │          (experimental denoise chain only when switched on)
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

- The floating controls are part of the screen, so whole-screen recordings
  hide them (the bar button timer and the keybinding still stop the
  recording). Area recordings put them at whichever edge is outside the
  region (top, bottom, left, right) and hide them when none is.
- **A camera can only stream to one program at a time.** If Chromium,
  Firefox or a call app holds it (a Meet, Slack or Teams call, or a tab that
  was granted the camera), the camera cannot start. Omareel says so in the
  launcher ("In use by Chromium") and in a notification, and records without
  the camera. End the call or close that tab, then record again.
- Window mode snaps the capture to a window's rectangle; it is the same
  screen capture as Area, so anything covering the window is recorded too.
  Keep it on top while recording.
- No pause/resume yet.

## Developing

`BarWidget.qml`, `Panel.qml`, and `Omareel.js` hot-reload on save; manifest
changes need `omarchy restart shell`. Shell log:
`ls -t /run/user/1000/quickshell/by-id/*/log.log | head -1`. Recorder and
ffmpeg log: `$XDG_RUNTIME_DIR/omareel/omareel.log`.

## License

MIT
