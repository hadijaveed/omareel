# Studio mode

Development feature, not yet part of the published marketplace release.

Studio is a small finishing step, not a timeline editor. The normal recording
workflow stays the default. It adds no packages beyond the existing Python and
FFmpeg requirements and never records extra devices or downloads backgrounds.

## The simple flow

1. Turn on **Studio mode** just below Area / Window / Screen, then record normally.
2. After Stop and audio cleanup, Studio opens with a frame preview.
3. Choose **Midnight**, **Paper**, or **Minimal**. Use **Adjust** only if needed.
4. Choose **Export styled copy**, or **Use original** to skip styling.
5. Open the saved video to check playback. Choose Upload or Copy as usual.

## Manual zooms

Use the time slider to find a moment, then choose **Add zoom here** and click
the part of the picture to enlarge. Set the start and end seconds and choose
1.25×, 1.5× or 2×. The video smoothly zooms in, holds, and returns to its original
framing by the end of that range; the background and decorative frame stay still.
Use **View zoom** to inspect its midpoint, or **Remove** to delete it.

You can add up to eight non-overlapping zooms, at least half a second each.
While choosing a focus point, the preview shows the unzoomed picture. The point
stays at its relative position in the frame as the picture enlarges. The slider
shows frame previews; check the motion in the exported video with Open.
These zooms are added manually in Studio after recording. Recording-time mouse
clicks are not captured or turned into zooms automatically.

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
| Screen framing | Fit | Fit without stretching, or Fill with edge cropping |
| Fixed zoom | Off (1×) | 1.25× or 1.5×, with a position to keep in view |

**Remember style** saves the appearance for later, excluding per-video zoom
ranges and the preview time; it does not turn
Studio on, change microphone settings, or change your sharing destination.
**Reset** restores the current draft to defaults; remember it if you also want
to reset your saved preference. Switching looks keeps your canvas/zoom choices.

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

The preview shows the frame at the selected time, not video playback. The same layout/filter
path is used for preview and export, but check the full exported video for
motion and composition before sharing an important recording.

Output is SDR H.264 MP4, quality CRF 18, at the original long edge capped at
3840 pixels. Background spacing reduces the screen's size inside that canvas.
Portrait or square output may leave generous background around a wide screen;
Fill or zoom can crop important content. The original retains its full quality.
Rendering uses two CPU encoding threads, so long or high-resolution videos take
time and additional disk space. The disposable preview cache keeps eight frames.

**Fixed zoom** under Adjust still crops the entire video. Manual zoom ranges
animate only during the selected times. There is no automatic click zoom or
cursor tracking. The camera is already part of the finished video;
zoom/crop affects it too. Independent camera placement belongs in a future
separate-layer capture design, not this toggle. HDR sources are rejected with
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
