# Studio mode

0.9.3 development preview, not yet part of the published marketplace release.
See the [laptop test and release plan](0.9.3-testing.md).

Studio is a small finishing step, not a timeline editor. The normal recording
workflow stays the default. It adds no packages beyond the existing Python and
FFmpeg requirements and never records extra devices or downloads backgrounds.

## The simple flow

1. Turn on **Studio mode** just below Area / Window / Screen, then record normally.
2. After Stop and audio cleanup, Studio opens with a frame preview.
3. Choose **Midnight**, **Paper**, or **Minimal**. Use **Adjust** only if needed.
4. Choose **Export styled copy**, or **Use original** to skip styling.
5. Open the saved video to check playback. Choose Upload or Copy as usual.

## Zoom on clicks

Turn on **Zoom on clicks** beneath the Studio toggle before recording. Ordinary
left-clicks inside the recorded area produce a short 1.5× zoom in the exported
video, followed by a smooth return. Rapid clicks finish the current two-second
zoom before starting another. There are no start/end fields, focus selectors,
or timeline controls. With the toggle off, nothing zooms.

Click locations are collected only for that recording, stored locally, and are
not included in uploads. Existing recordings have no click history: record a
new take with the toggle on. Area, Screen and direct Window capture are supported;
the optional portal Window mode needs the toggle off.

The camera self-view stays visible while recording, just as it does with Studio
off. It is part of the captured screen, so exported click zooms also zoom the
camera and can temporarily crop it out. The original keeps the full picture.
Older takes recorded with separate camera layers still support a fixed camera
in exports; keep their `.studio-screen.mp4` and `.studio-camera.mp4` companions.

You can also choose **Style** on a saved recording, even with Studio mode off.
Closing Studio does not discard the video. Closing during export lets the job
continue; the bar shows it is busy until the copy is ready.

## A few controls, sensible defaults

| Control | Default | Choices |
| --- | --- | --- |
| Look | Midnight | Soft dark gradient, Paper application frame, Minimal solid |
| Background | Midnight gradient | Paper gradient, solid hex color, local PNG/JPEG/WebP |
| Spacing | Comfortable | Compact, Comfortable, Spacious |
| Frame | Rounded | None, Rounded, decorative application title bar |
| Shadow | On | On/off |
| Canvas | Original aspect ratio | Landscape 16:9, Square 1:1, Portrait 9:16 |
| Zoom on clicks | Off | Enable before recording; zooms follow recorded clicks |

Appearance changes save automatically for your next video: look, background,
spacing, frame, shadow and canvas. There is no separate **Remember style** step.
The status below Adjust shows when a save is running; if it fails, **Retry save**
tries again. Changes are stored locally in `studio.style` in Omareel's settings.
They do not turn Studio on, change microphone settings, or change sharing.

**Reset** restores and saves the defaults. Switching looks keeps your canvas
choice, while applying that look's background, frame, spacing and shadow.
Restyling an existing Studio export opens that video's own saved appearance;
new recordings start with your most recently remembered choices.

Local backgrounds must be PNG, JPEG or WebP files up to 50 MB / 40 megapixels. Paste their local
path in Adjust; web URLs and SVG are deliberately not accepted. If you move or
remove the image, choose another background before exporting.

## Originals, sound and sharing

- Your original MP4 stays untouched, including when export fails. The separate
  `.raw.mp4` retention preference continues to work as before.
- Studio encodes only the picture. Existing audio packets are copied without
  another denoise, EQ, volume adjustment or lossy audio encode.
- Every export gets a new UUID and library entry. Uploading it does not replace
  the original shared object. Check the selected video with Open before Upload.
- Automatic upload is paused for a take that starts with Studio enabled, even
  if you change the toggle while recording. Turning Studio off restores your
  existing automatic-upload preference for future takes.
- Editing a styled library entry uses its original, not another layer of frames.
  Renaming the original through Omareel updates that reference. Moving files
  outside Omareel can break the reference; restore the original to restyle.
- No remote upload is performed by preview, export, or Use original. Copying an
  existing shared original still copies its existing link.

## Honest limits

The preview shows the first frame, not video playback. The same layout/filter
path is used for preview and export, but check the full exported video for
motion and composition before sharing an important recording.

Output is SDR H.264 MP4, quality CRF 18, at the original long edge capped at
3840 pixels. Background spacing reduces the screen's size inside that canvas.
Portrait or square output may leave generous background around a wide screen;
Click zoom temporarily crops the screen around the clicked point. The original retains its full quality.
Rendering uses two CPU encoding threads, so long or high-resolution videos take
time and additional disk space. The disposable preview cache keeps eight frames.

Click zoom uses the recorded click location, not cursor tracking or typed text.
The plain original keeps the whole screen. HDR sources are rejected with
guidance to keep the original rather than silently changing their colors.

## Rollback and checks

Turn Studio mode off to return to the normal workflow. Existing originals,
styled exports and links stay usable. This work is isolated on `feat/studio-mode`;
the marketplace commit is not advanced by it. On this development machine the
installed plugin is on a local test branch; its `main` branch retains the stable
version for rollback.

Automated synthetic-media checks cover motion, audio packet/timestamp equality,
preview/export correspondence, geometry, local images, invalid input, busy
recording guards, failure preservation, unique sharing identities, renames and
preview cleanup. They do not certify every GPU/laptop or replace a real short
take at your normal resolution.

```bash
python3 tests/studio-regression.py
# On an Omarchy machine, also exercise the native UI offscreen:
python3 tests/studio-native.py
```
