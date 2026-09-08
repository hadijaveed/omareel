import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons as Commons
import qs.Ui

// A finishing panel, not a timeline editor. All settings are local drafts
// until explicitly remembered. Export always creates a separate recording.
Column {
  id: root
  property string cli: ""
  property string file: ""
  property var style: defaults()
  property bool adjusting: false
  property string feedback: ""
  property string recordingWarning: ""
  property string previewUrl: ""
  property string previewLabel: ""
  property int revision: 0
  property int renderedRevision: -1
  property int requestedRevision: -1
  readonly property bool exporting: exportProc.running
  readonly property bool waiting: previewProc.running || debounce.running
  signal finished()
  signal editing(bool focused)
  spacing: Commons.Style.space(10)

  function defaults() {
    return {preset:"midnight", background:"midnight", image:"", color:"#20242f", padding:"normal",
      frame:"rounded", shadow:true, aspect:"original", fit:"fit", zoom:"1", focus:"center"}
  }
  function begin(path, saved) {
    if (root.exporting) return
    file = path
    var draft = defaults()
    if (saved) for (var key in draft) if (saved[key] !== undefined) draft[key] = saved[key]
    style = draft
    adjusting = false
    feedback = ""
    previewUrl = ""
    previewLabel = ""
    revision++
    debounce.restart()
  }
  function change(key, value) {
    var draft = JSON.parse(JSON.stringify(style))
    draft[key] = value
    draft.preset = "custom"
    style = draft
    revision++
    feedback = ""
    debounce.restart()
  }
  function preset(name) {
    // Keep framing choices when changing the look; Reset restores everything.
    var draft = JSON.parse(JSON.stringify(style))
    draft.preset = name
    draft.background = name === "minimal" ? "solid" : name
    draft.color = "#20242f"
    draft.frame = name === "paper" ? "application" : name === "minimal" ? "none" : "rounded"
    draft.shadow = name !== "minimal"
    draft.padding = name === "minimal" ? "small" : "normal"
    style = draft
    revision++
    feedback = ""
    debounce.restart()
  }
  function preview() {
    if (!file || exporting) return
    if (previewProc.running) return // onExited picks up the newest draft.
    renderedRevision = -1
    requestedRevision = revision
    previewProc.command = [cli, "studio", "preview", file, JSON.stringify(style)]
    previewProc.running = true
  }
  function exportCopy() {
    if (exporting || waiting || renderedRevision !== revision) return
    feedback = "Exporting a separate copy… You can close this panel; the original is safe."
    exportProc.command = [cli, "studio", "export", file, JSON.stringify(style)]
    exportProc.running = true
  }

  Timer { id: debounce; interval: 350; onTriggered: root.preview() }
  Process {
    id: previewProc
    stdout: StdioCollector { id: previewOut }
    stderr: StdioCollector { id: previewErr }
    onExited: function(code) {
      if (root.requestedRevision !== root.revision) { debounce.restart(); return }
      if (code !== 0) {
        root.feedback = code === 75 ? "Recorder is busy. Finish recording or exporting, then try Preview again." : (previewErr.text.trim() || "Preview failed. Your original is safe; try Preview again.")
        return
      }
      try {
        var result = JSON.parse(previewOut.text)
        root.previewUrl = "file://" + encodeURI(result.file).replace(/#/g, "%23").replace(/\?/g, "%3F")
        root.previewLabel = result.width + " × " + result.height + " · Frame preview · Audio unchanged"
        root.renderedRevision = root.revision
      } catch (e) { root.feedback = "Could not read the frame preview. Try Preview again." }
    }
  }
  Process {
    id: exportProc
    stdout: StdioCollector {}
    stderr: StdioCollector { id: exportErr }
    onExited: function(code) {
      if (code === 0) { root.feedback = ""; root.finished() }
      else root.feedback = code === 75 ? "Recorder is busy. Finish the current operation, then retry." : (exportErr.text.trim() || "Export failed. Your original is safe; try again.")
    }
  }
  Process {
    id: rememberProc
    stdout: StdioCollector {}
    stderr: StdioCollector { id: rememberErr }
    onExited: function(code) {
      root.feedback = code === 0 ? "Style saved for your next Studio recording." : (rememberErr.text.trim() || "Could not save your style. Try again.")
    }
  }
  Process {
    id: originalProc
    stdout: StdioCollector {}
    stderr: StdioCollector { id: originalErr }
    onExited: function(code) {
      if (code === 0) root.finished()
      else root.feedback = originalErr.text.trim() || "Recorder is busy. Try again when it finishes."
    }
  }

  component Hint: Text {
    textFormat: Text.PlainText
    width: parent.width
    color: Commons.Color.popups.text
    font.family: Commons.Style.font.family
    font.pixelSize: Commons.Style.font.bodySmall
    wrapMode: Text.Wrap
  }
  component Action: Button { focusable: true }
  Row {
    spacing: Commons.Style.space(8)
    Action { text: "Back"; enabled: !root.exporting; onClicked: root.finished() }
    Text {
      textFormat: Text.PlainText
      text: "Studio"
      anchors.verticalCenter: parent.verticalCenter
      color: Commons.Color.popups.text
      font.family: Commons.Style.font.family
      font.pixelSize: Commons.Style.font.subtitle
    }
  }
  Hint { text: "Give your recording a frame. Your original stays in Recordings." }
  Hint { visible: root.recordingWarning !== ""; text: root.recordingWarning }
  Rectangle {
    width: parent.width
    height: Math.min(width * 0.625, Commons.Style.space(300))
    color: "#151820"
    Image {
      anchors.fill: parent
      source: root.previewUrl
      fillMode: Image.PreserveAspectFit
      cache: false
      asynchronous: true
      opacity: root.waiting || root.renderedRevision !== root.revision ? 0.45 : 1
    }
    Text {
      textFormat: Text.PlainText
      anchors.centerIn: parent
      visible: root.waiting || !root.previewUrl
      text: root.waiting ? "Preparing frame preview…" : "Preview not available"
      color: "#ffffff"
      font.family: Commons.Style.font.family
      font.pixelSize: Commons.Style.font.bodySmall
    }
  }
  Hint { text: root.previewLabel || "Preview uses the first frame of your recording."; opacity: 0.7 }
  PlainDropdown {
    width: parent.width
    label: "Look"
    enabled: !root.exporting
    options: [{value:"midnight",label:"Midnight — soft gradient"}, {value:"paper",label:"Paper — application frame"},
      {value:"minimal",label:"Minimal — clean solid"}, {value:"custom",label:"Custom adjustments"}]
    value: root.style.preset
    onChanged: function(v) { if (v === "custom") root.adjusting = true; else root.preset(v) }
  }
  Flow {
    width: parent.width
    spacing: Commons.Style.space(6)
    enabled: !root.exporting
    Action { text: root.adjusting ? "Hide adjustments" : "Adjust"; onClicked: root.adjusting = !root.adjusting }
    Action { text: "Reset"; onClicked: root.begin(root.file, null) }
    Action {
      text: rememberProc.running ? "Saving…" : "Remember style"
      enabled: !rememberProc.running
      onClicked: {
        rememberProc.command = [root.cli,"config","merge",JSON.stringify({studio:{style:root.style}})]
        rememberProc.running = true
      }
    }
  }
  Column {
    width: parent.width
    spacing: Commons.Style.space(8)
    visible: root.adjusting
    enabled: !root.exporting
    PlainDropdown {
      width: parent.width; label: "Background"; value: root.style.background
      options: [{value:"midnight",label:"Midnight gradient"},{value:"paper",label:"Paper gradient"},
        {value:"solid",label:"Solid color"},{value:"image",label:"Local image"}]
      onChanged: function(v) { root.change("background",v) }
    }
    TextField {
      width: parent.width
      visible: root.style.background === "solid" || root.style.background === "image"
      placeholderText: root.style.background === "solid" ? "Hex color, e.g. #20242f" : "Paste a local PNG, JPEG or WebP path"
      text: root.style.background === "solid" ? root.style.color : root.style.image
      onActiveFocusChanged: root.editing(activeFocus)
      onEditingFinished: root.change(root.style.background === "solid" ? "color" : "image", text.trim())
    }
    PlainDropdown {
      width: parent.width; label: "Spacing"; value: root.style.padding
      options: [{value:"small",label:"Compact"},{value:"normal",label:"Comfortable"},{value:"large",label:"Spacious"}]
      onChanged: function(v) { root.change("padding",v) }
    }
    PlainDropdown {
      width: parent.width; label: "Frame"; value: root.style.frame
      options: [{value:"none",label:"None"},{value:"rounded",label:"Rounded"},{value:"application",label:"Application — decorative title bar"}]
      onChanged: function(v) { root.change("frame",v) }
    }
    PlainToggle { width: parent.width; label: "Soft shadow"; checked: root.style.shadow; onClicked: root.change("shadow", !root.style.shadow) }
    PlainDropdown {
      width: parent.width; label: "Canvas"; value: root.style.aspect
      options: [{value:"original",label:"Original aspect ratio"},{value:"landscape",label:"Landscape — 16:9"},
        {value:"square",label:"Square — 1:1"},{value:"portrait",label:"Portrait — 9:16"}]
      onChanged: function(v) { root.change("aspect",v) }
    }
    PlainDropdown {
      width: parent.width; label: "Screen framing"; value: root.style.fit
      options: [{value:"fit",label:root.style.zoom === "1" ? "Fit — show the whole screen" : "Fit — keep the zoomed area’s aspect ratio"},
        {value:"fill",label:"Fill — crop edges to fill the frame"}]
      onChanged: function(v) { root.change("fit",v) }
    }
    PlainDropdown {
      width: parent.width; label: "Fixed zoom"; value: root.style.zoom
      options: [{value:"1",label:"Off — 1×"},{value:"1.25",label:"Closer — 1.25×"},{value:"1.5",label:"Close-up — 1.5×"}]
      onChanged: function(v) { root.change("zoom",v) }
    }
    PlainDropdown {
      width: parent.width; label: "Keep in view"; value: root.style.focus
      visible: root.style.zoom !== "1" || root.style.fit === "fill"
      options: [{value:"center",label:"Center"},{value:"top-left",label:"Top left"},{value:"top-center",label:"Top center"},
        {value:"top-right",label:"Top right"},{value:"center-left",label:"Left"},{value:"center-right",label:"Right"},
        {value:"bottom-left",label:"Bottom left"},{value:"bottom-center",label:"Bottom center"},{value:"bottom-right",label:"Bottom right"}]
      onChanged: function(v) { root.change("focus",v) }
    }
    Hint { text: "Zoom is fixed for the whole video. Cropping also crops any recorded camera overlay. No automatic zoom or independent camera editing."; opacity: 0.7 }
  }
  Hint { visible: root.feedback !== ""; text: root.feedback }
  Flow {
    width: parent.width
    spacing: Commons.Style.space(6)
    Action {
      text: root.exporting ? "Exporting…" : "Export styled copy"
      active: true
      enabled: !root.exporting && !root.waiting && root.renderedRevision === root.revision && !originalProc.running
      onClicked: root.exportCopy()
    }
    Action {
      text: "Use original"
      enabled: !root.exporting && !root.waiting && !originalProc.running
      onClicked: { originalProc.command = [root.cli,"studio","select",root.file]; originalProc.running = true }
    }
    Action { text: "Preview"; enabled: !root.exporting && !root.waiting; onClicked: root.preview() }
  }
  Hint { text: "Local export · H.264 · original long edge, up to 3840 px · Upload only when you choose it."; opacity: 0.7 }
}
