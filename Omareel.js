.pragma library

// Pure helpers shared by BarWidget.qml and Panel.qml. No Qt imports so the
// file stays node-testable.

function parseJson(text, fallback) {
  try {
    var value = JSON.parse(String(text || ""))
    return value && typeof value === "object" ? value : fallback
  } catch (e) {
    return fallback
  }
}

function phaseOf(state) {
  return state && state.phase ? String(state.phase) : "idle"
}

function pad2(n) {
  return (n < 10 ? "0" : "") + n
}

// "mm:ss" (or "h:mm:ss") since state.startedAt, frozen at stoppedAt once the
// recording has stopped so the processing/done banners show the final length.
function formatElapsed(state, nowSec) {
  if (!state || !state.startedAt) return "00:00"
  var phase = phaseOf(state)
  var end = phase === "recording" ? nowSec : (state.stoppedAt || state.updatedAt || nowSec)
  var secs = Math.max(0, Math.floor(end - state.startedAt))
  var h = Math.floor(secs / 3600)
  var m = Math.floor((secs % 3600) / 60)
  var s = secs % 60
  return (h > 0 ? h + ":" + pad2(m) : pad2(m)) + ":" + pad2(s)
}

function statusText(state, nowSec) {
  var phase = phaseOf(state)
  switch (phase) {
  case "picking": return "Pick what to record…"
  case "recording": return formatElapsed(state, nowSec) + (state.target ? "  ·  " + state.target : "")
  case "processing": return "Cleaning up audio…"
  case "uploading": return "Uploading" + (state.progress ? "  " + state.progress + "%" : "…")
  case "done":
    if (state.url) return "Link copied to clipboard"
    return state.canUpload ? "Saved  ·  upload to share" : "Saved  ·  path copied"
  default: return ""
  }
}

function shareTarget(state) {
  if (!state) return ""
  return state.url ? String(state.url) : String(state.file || "")
}

// Shorten a URL/path for a one-line banner.
function shortShare(state, max) {
  var s = shareTarget(state)
  if (s.length <= max) return s
  return "…" + s.slice(s.length - max + 1)
}

// Recorded region as {x, y, w, h} in logical coordinates, or null.
function regionOf(state) {
  if (!state || !state.region) return null
  var m = /^(\d+)x(\d+)\+(-?\d+)\+(-?\d+)$/.exec(String(state.region))
  if (!m) return null
  return { w: +m[1], h: +m[2], x: +m[3], y: +m[4] }
}

// True when the floating controls, centred at the top of `screen`, would sit
// inside the recorded region; the panel then moves to the bottom edge.
function placeAtBottom(state, screen, cardWidth, cardHeight, topOffset) {
  var r = regionOf(state)
  if (!r || !screen) return false
  var sx = screen.x || 0, sy = screen.y || 0, sw = screen.width || 0
  var cx0 = sx + (sw - cardWidth) / 2, cx1 = cx0 + cardWidth
  var cy0 = sy + topOffset, cy1 = cy0 + cardHeight
  var overlapsX = r.x < cx1 && r.x + r.w > cx0
  var overlapsY = r.y < cy1 && r.y + r.h > cy0
  return overlapsX && overlapsY
}

function screenNamed(screens, name) {
  if (!screens) return null
  var list = screens.values !== undefined ? screens.values : screens
  for (var i = 0; i < list.length; i++) {
    if (list[i] && String(list[i].name) === String(name)) return list[i]
  }
  return list.length > 0 ? list[0] : null
}

function get(obj, path, fallback) {
  var cur = obj
  var parts = String(path).split(".")
  for (var i = 0; i < parts.length; i++) {
    if (cur === null || cur === undefined || typeof cur !== "object") return fallback
    cur = cur[parts[i]]
  }
  return cur === undefined || cur === null ? fallback : cur
}

// Deep copy of `config` with `path` set to `value`.
function withValue(config, path, value) {
  var next = JSON.parse(JSON.stringify(config || {}))
  var parts = String(path).split(".")
  var cur = next
  for (var i = 0; i < parts.length - 1; i++) {
    if (typeof cur[parts[i]] !== "object" || cur[parts[i]] === null) cur[parts[i]] = {}
    cur = cur[parts[i]]
  }
  cur[parts[parts.length - 1]] = value
  return next
}

// {a: {b: value}} patch object for `omareel config merge`.
function patchFor(path, value) {
  return withValue({}, path, value)
}

function shellQuote(value) {
  return "'" + String(value).replace(/'/g, "'\\''") + "'"
}

// Human label for a device value from a devices list, falling back to the value.
function deviceLabel(list, value) {
  if (!Array.isArray(list)) return String(value || "")
  for (var i = 0; i < list.length; i++) {
    if (String(list[i].value) === String(value)) return String(list[i].label)
  }
  return String(value || "")
}

var PROVIDERS = [
  { value: "none", label: "Off — keep recordings local" },
  { value: "r2", label: "Cloudflare R2" },
  { value: "s3", label: "AWS S3" },
  { value: "b2", label: "Backblaze B2 (S3 API)" },
  { value: "s3compat", label: "S3-compatible (custom endpoint)" },
  { value: "existing", label: "Existing rclone remote" }
]

function providerLabel(value) {
  for (var i = 0; i < PROVIDERS.length; i++) if (PROVIDERS[i].value === value) return PROVIDERS[i].label
  return String(value || "none")
}

// One-line description of the sharing destination for the launcher toggle.
function uploadSummary(config) {
  var p = get(config, "upload.provider", "none")
  if (p === "none") return "Set a destination in settings (gear)"
  if (p === "existing") return "To " + get(config, "upload.remote", "rclone remote")
  var bucket = get(config, "upload.bucket", "")
  return "To " + providerLabel(p) + (bucket ? " · " + bucket : "")
}

// index.jsonl → array of entries, newest first, at most `max`.
function parseJsonl(text, max) {
  var out = []
  var lines = String(text || "").split("\n")
  for (var i = lines.length - 1; i >= 0 && out.length < (max || 25); i--) {
    var line = lines[i].trim()
    if (!line) continue
    try { out.push(JSON.parse(line)) } catch (e) {}
  }
  return out
}

function baseName(path) {
  var s = String(path || "")
  return s.slice(s.lastIndexOf("/") + 1).replace(/\.mp4$/, "")
}

// Display name of an index entry: its title, else the file name.
function recordingName(entry) {
  if (!entry) return ""
  return entry.title ? String(entry.title) : baseName(entry.file)
}

function formatDuration(sec) {
  sec = Math.max(0, parseInt(sec || 0, 10))
  var m = Math.floor(sec / 60), s = sec % 60
  return m + ":" + (s < 10 ? "0" : "") + s
}

// "Today 12:56 · 0:04 · Shared" style meta line for the recordings list.
function recordingMeta(entry) {
  if (!entry) return ""
  var parts = []
  if (entry.at) {
    var d = new Date(entry.at * 1000), now = new Date()
    var sameDay = d.toDateString() === now.toDateString()
    var hm = ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2)
    parts.push(sameDay ? "Today " + hm : d.toLocaleDateString(Qt.locale(), "MMM d") + " " + hm)
  }
  if (entry.duration) parts.push(formatDuration(entry.duration))
  parts.push(entry.url ? "Shared" : "Local")
  return parts.join("  ·  ")
}

// A finished recording that is still local and has somewhere to go.
function canUpload(state) {
  return !!state && phaseOf(state) === "done" && !state.url && state.canUpload === true
}

function uploadReady(config, remoteStatus) {
  var p = get(config, "upload.provider", "none")
  if (p === "none") return false
  if (p === "existing") return String(get(config, "upload.remote", "")) !== ""
  return String(get(config, "upload.bucket", "")) !== "" && !!(remoteStatus && remoteStatus.hasSecret)
}
