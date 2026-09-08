# Studio screenshots

These assets show the real 0.9.3 development UI and exporter. `demo.qml` is a
fictional documentation workspace, used as non-sensitive example recording
content. It is not an Omareel interface or a customer testimonial.

Regenerate on an Omarchy desktop:

```bash
python3 docs/capture-studio-screenshots.py
```

The script renders the sample, creates a temporary three-second MP4, supplies
one synthetic click in the normal recording metadata format, and exports it
through `omareel studio export`. It extracts the Midnight and Paper first frames
and a later frame during the click zoom. The editor image captures the actual
`StudioEditor.qml`, native Omarchy controls, and a real generated preview.

The script isolates configuration, recordings, runtime/cache, desktop hooks and
rclone settings. It opens no camera or microphone, captures no desktop pixels,
and uploads nothing. Output PNGs go in `docs/`; temporary media is deleted.

Review all four images after regeneration. The screenshots demonstrate visual
output, not physical capture compatibility or the timing of real click delivery.
The native click and Studio tests cover those paths separately.
