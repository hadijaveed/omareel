import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Omareel.js" as Omareel

// Bar launcher for Omareel: a record glyph (with a live timer while recording)
// that opens a Loom-style start panel — pick Area / Window / Screen, choose
// microphone, system-audio source and webcam, flip noise removal and upload,
// and a settings page (gear) for recording quality and the upload destination
// (Cloudflare R2, AWS S3, Backblaze B2, any S3 endpoint, or an existing
// rclone remote). Credentials go straight to rclone.conf via bin/omareel and
// are never stored in omareel.json.
//
// IPC:  omarchy-shell omareel open|close|toggle|status|refresh|settings
Panel {
  id: root

  moduleName: "hadijaveed.omareel"
  ipcTarget: "omareel"
  manageIpc: false

  readonly property string cli: String(Qt.resolvedUrl("bin/omareel")).replace(/^file:\/\//, "")
  readonly property string home: Quickshell.env("HOME")
  readonly property string runtimeDir: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/omareel"

  property var state: ({ phase: "idle" })
  property var config: ({})
  property var devices: ({ mics: [], outputs: [], cameras: [] })
  property var remoteStatus: ({})
  property var doctor: ({})
  property int nowSec: Math.floor(Date.now() / 1000)

  property string page: "launcher" // launcher | settings | recordings
  property var recordings: []       // index.jsonl, newest first
  property string selectedFile: ""  // expanded row on the recordings page
  property string draftName: ""     // rename field on the recordings page
  property bool editing: false      // a text field has focus → shortcuts off
  property string message: ""       // save/test feedback on the settings page
  property bool working: false
  property string draftKey: ""
  property string draftSecret: ""

  readonly property string phase: Omareel.phaseOf(state)
  readonly property bool recording: phase === "recording"
  readonly property bool busy: phase === "picking" || phase === "processing" || phase === "uploading"
  readonly property bool finished: phase === "done"
  readonly property bool idle: phase === "idle"
  readonly property string elapsed: Omareel.formatElapsed(state, nowSec)

  readonly property bool micOn: Omareel.get(config, "mic", true) === true
  readonly property bool desktopOn: Omareel.get(config, "desktopAudio", false) === true
  readonly property bool webcamOn: Omareel.get(config, "webcam", false) === true
  readonly property bool denoiseOn: Omareel.get(config, "denoise", true) === true
  readonly property string provider: String(Omareel.get(config, "upload.provider", "none"))
  readonly property bool uploadReady: Omareel.uploadReady(config, remoteStatus)
  readonly property bool uploadAuto: uploadReady && Omareel.get(config, "upload.auto", false) === true
  readonly property bool canUpload: Omareel.canUpload(state)
  property string draftTitle: ""

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  // ---- actions ------------------------------------------------------------

  function cliRun(args) { Util.execArgv([root.cli].concat(args)) }

  function start(kind) {
    root.close()
    cliRun(["start", kind])
  }

  // Optimistic local update + persisted deep-merge through the CLI.
  function setConfig(path, value) {
    root.config = Omareel.withValue(root.config, path, value)
    var proc = mergeComponent.createObject(root, {
      command: [root.cli, "config", "merge", JSON.stringify(Omareel.patchFor(path, value))]
    })
    proc.running = true
  }

  readonly property string outputDir: String(Omareel.get(config, "outputDir", "~/Videos/Omareel")).replace(/^~/, home)

  function renameLast() {
    var title = root.draftTitle.trim()
    if (!title) return
    root.draftTitle = ""
    root.cliRun(["rename", "last", title])
  }
  function selectRecording(entry) {
    var file = entry ? String(entry.file) : ""
    root.selectedFile = root.selectedFile === file ? "" : file
    root.draftName = entry ? String(entry.title || "") : ""
  }
  function renameSelected() {
    var title = root.draftName.trim()
    if (!title || !root.selectedFile) return
    root.cliRun(["rename", root.selectedFile, title])
  }
  function uploadSelected() {
    if (!root.selectedFile) return
    root.cliRun(["upload", root.selectedFile, "--title=" + root.draftName.trim()])
    root.close()
  }

  function uploadLast() {
    if (!root.canUpload) return
    var title = root.draftTitle.trim()
    root.draftTitle = ""
    root.cliRun(["upload", "last", "--title=" + title])
  }

  function refreshAll() {
    stateFile.reload()
    configFile.reload()
    devicesProc.running = true
    remoteProc.running = true
    doctorProc.running = true
  }

  function missingForSave() {
    var need = []
    if (root.provider === "r2" && !Omareel.get(root.config, "upload.accountId", "")) need.push("Cloudflare account ID")
    if ((root.provider === "s3" || root.provider === "b2") && !Omareel.get(root.config, "upload.region", "")) need.push("Region")
    if (root.provider === "s3compat" && !Omareel.get(root.config, "upload.endpoint", "")) need.push("Endpoint URL")
    if (!Omareel.get(root.config, "upload.bucket", "")) need.push("Bucket")
    if (!root.remoteStatus.hasSecret) {
      if (!root.draftKey) need.push(root.provider === "b2" ? "Key ID" : "Access key ID")
      if (!root.draftSecret) need.push(root.provider === "b2" ? "Application key" : "Secret access key")
    }
    return need
  }

  function saveRemote() {
    var need = missingForSave()
    if (need.length) { root.message = "Fill in: " + need.join(", "); return }
    if (root.provider === "b2" && root.draftKey && /^K0/.test(root.draftKey)) {
      root.message = "That Key ID looks like the application key (starts with K00…). Backblaze's keyID is 25 characters and starts with the cluster number, e.g. 005…"
      return
    }
    root.message = "Saving…"
    root.working = true
    saveProc.environment = ({
      OMAREEL_ACCESS_KEY_ID: root.draftKey,
      OMAREEL_SECRET_ACCESS_KEY: root.draftSecret
    })
    saveProc.running = true
  }

  function testRemote() {
    if (root.provider !== "existing" && !root.remoteStatus.hasSecret) {
      var need = missingForSave()
      root.message = "Save credentials first" + (need.length ? " — fill in: " + need.join(", ") : "")
      return
    }
    if (!Omareel.get(root.config, "upload.publicBase", "") && root.provider !== "existing") {
      root.message = "Enter the bucket's public URL first, so the test can fetch the probe back"
      return
    }
    root.message = "Testing… uploading a probe file"
    root.working = true
    testProc.running = true
  }

  onOpenedChanged: if (opened) { root.editing = false; refreshAll() }

  // ---- state / config plumbing -------------------------------------------

  FileView {
    id: indexFile
    path: root.outputDir + "/index.jsonl"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      root.recordings = Omareel.parseJsonl(text(), 30)
      if (root.selectedFile && !root.recordings.some(function(e) { return String(e.file) === root.selectedFile })) root.selectedFile = ""
    }
    onLoadFailed: root.recordings = []
  }
  FileView {
    path: root.outputDir
    watchChanges: true
    printErrors: false
    onFileChanged: indexFile.reload()
  }

  FileView {
    id: stateFile
    path: root.runtimeDir + "/state.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.state = Omareel.parseJson(text(), { phase: "idle" })
    onLoadFailed: root.state = { phase: "idle" }
  }

  // state.json is replaced atomically (write tmp + mv), which some watchers
  // report on the directory rather than the file. Watch both.
  FileView {
    path: root.runtimeDir
    watchChanges: true
    printErrors: false
    onFileChanged: stateFile.reload()
  }

  FileView {
    id: configFile
    path: root.home + "/.config/omarchy/omareel.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.config = Omareel.parseJson(text(), {})
    onLoadFailed: root.config = {}
  }

  // `omareel status` creates the runtime dir, the default config and an idle
  // state file, so the watchers above have something to attach to.
  Process {
    command: [root.cli, "status"]
    running: true
    onExited: function() {
      stateFile.reload()
      configFile.reload()
    }
  }

  Component {
    id: mergeComponent
    Process {
      onExited: function() { configFile.reload(); destroy() }
    }
  }

  Process {
    id: devicesProc
    command: [root.cli, "devices"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.devices = Omareel.parseJson(text, { mics: [], outputs: [], cameras: [] })
    }
  }

  Process {
    id: remoteProc
    command: [root.cli, "remote", "status"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.remoteStatus = Omareel.parseJson(text, {})
    }
  }

  Process {
    id: doctorProc
    command: [root.cli, "doctor"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.doctor = Omareel.parseJson(text, {})
    }
  }

  Process {
    id: saveProc
    command: [root.cli, "remote", "save"]
    stdout: StdioCollector { id: saveOut; waitForEnd: true }
    stderr: StdioCollector { id: saveErr; waitForEnd: true }
    onExited: function(code) {
      root.working = false
      var out = String(saveOut.text || "").trim(), err = String(saveErr.text || "").trim()
      root.message = code === 0 ? (out || "Saved") : ("Save failed: " + (err || out || "exit " + code))
      if (code === 0) { root.draftKey = ""; root.draftSecret = ""; keyField.text = ""; secretField.text = "" }
      remoteProc.running = true
    }
  }

  Process {
    id: testProc
    command: [root.cli, "remote", "test"]
    stdout: StdioCollector { id: testOut; waitForEnd: true }
    stderr: StdioCollector { id: testErr; waitForEnd: true }
    onExited: function(code) {
      root.working = false
      var out = String(testOut.text || "").trim(), err = String(testErr.text || "").trim()
      root.message = (code === 0 ? "" : "Test failed\n") + (out || err || "exit " + code)
    }
  }

  Process {
    id: linkProc
    command: [root.cli, "setup", "--link"]
    onExited: function() { root.message = "Linked ~/.local/bin/omareel"; doctorProc.running = true }
  }

  Timer {
    interval: 1000
    repeat: true
    running: root.recording || root.busy
    triggeredOnStart: true
    onTriggered: root.nowSec = Math.floor(Date.now() / 1000)
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.page = "launcher"; root.open() }
    function close(): void { root.close() }
    function show(): void { root.open() }
    function hide(): void { root.close() }
    function toggle(): void { root.toggle() }
    function settings(): void { root.page = "settings"; root.open() }
    function recordings(): void { root.selectedFile = ""; root.page = "recordings"; root.open() }
    function status(): string { return root.phase }
    function refresh(): void { root.refreshAll() }
  }

  // ---- bar button ---------------------------------------------------------

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.recording ? "󰑊 " + root.elapsed : (root.busy ? "󰑊 …" : "󰑊")
    active: root.recording
    tooltipText: root.recording ? "Stop Omareel recording" : "Omareel: record & share"
    onPressed: function(b) {
      if (b === Qt.LeftButton) {
        if (root.recording) root.cliRun(["stop"])
        else { root.page = "launcher"; root.toggle() }
      } else if (b === Qt.RightButton) {
        if (root.recording) root.cliRun(["cancel"])
        else root.cliRun(["last"])
      } else if (b === Qt.MiddleButton) {
        root.cliRun(["open"])
      }
    }
  }

  // ---- reusable bits ------------------------------------------------------

  component SettingField: Column {
    id: field
    property string label: ""
    property string placeholder: ""
    property string path: ""
    property bool secret: false
    property alias text: input.text
    property alias input: input
    signal edited(string value)
    width: parent.width
    spacing: Style.space(3)
    Text {
      text: field.label
      color: Color.popups.text
      opacity: 0.7
      font.family: Style.font.family
      font.pixelSize: Style.font.bodySmall
    }
    TextField {
      id: input
      width: parent.width
      password: field.secret
      placeholderText: field.placeholder
      font.family: Style.font.family
      font.pixelSize: Style.font.body
      foreground: Color.popups.text
      text: field.path ? String(Omareel.get(root.config, field.path, "")) : ""
      onActiveFocusChanged: root.editing = activeFocus
      onTextEdited: field.edited(text)
      onEditingFinished: if (field.path) root.setConfig(field.path, text.trim())
    }
  }

  component Heading: PanelSectionHeader {
    width: parent.width
  }

  component Hint: Text {
    width: parent.width
    color: Color.popups.text
    opacity: 0.65
    font.family: Style.font.family
    font.pixelSize: Style.font.bodySmall
    wrapMode: Text.Wrap
  }

  // ---- popup --------------------------------------------------------------

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(
      (root.page === "settings" ? settingsColumn.implicitHeight
       : root.page === "recordings" ? libraryColumn.implicitHeight : launcherColumn.implicitHeight), Style.space(720))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: root.editing
      onCloseRequested: {
        if (root.page !== "launcher") root.page = "launcher"
        else root.close()
      }
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Flickable {
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: root.page === "settings" ? settingsColumn.implicitHeight
          : root.page === "recordings" ? libraryColumn.implicitHeight : launcherColumn.implicitHeight
        boundsBehavior: Flickable.StopAtBounds

        // ================================================================
        // Launcher page
        // ================================================================
        Column {
          id: launcherColumn
          width: parent.width
          spacing: Style.space(10)
          visible: root.page === "launcher"

          Item {
            width: parent.width
            height: Math.max(headerRow.implicitHeight, gear.implicitHeight)
            Row {
              id: headerRow
              spacing: Style.space(8)
              Text {
                text: "󰑊"
                color: root.recording ? Color.urgent : Color.popups.text
                font.family: Style.font.family
                font.pixelSize: Style.font.iconLarge
                anchors.verticalCenter: parent.verticalCenter
              }
              Column {
                anchors.verticalCenter: parent.verticalCenter
                Text {
                  text: "Omareel"
                  color: Color.popups.text
                  font.family: Style.font.family
                  font.pixelSize: Style.font.title
                  font.bold: true
                }
                Text {
                  text: root.idle ? "Record a video and share a link" : Omareel.statusText(root.state, root.nowSec)
                  color: Color.popups.text
                  opacity: 0.65
                  font.family: Style.font.family
                  font.pixelSize: Style.font.bodySmall
                }
              }
            }
            Button {
              id: gear
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              iconText: "󰒓"
              tooltipText: "Settings"
              onClicked: { root.message = ""; root.page = "settings" }
            }
          }

          PanelSeparator { width: parent.width }

          // Recording controls
          Row {
            visible: root.recording
            spacing: Style.space(8)
            Button {
              iconText: "󰓛"
              text: "Stop & share"
              active: true
              onClicked: { root.close(); root.cliRun(["stop"]) }
            }
            Button {
              iconText: "󰆴"
              text: "Discard"
              onClicked: { root.close(); root.cliRun(["cancel"]) }
            }
          }

          Hint {
            visible: root.busy && !root.recording
            opacity: 1
            text: Omareel.statusText(root.state, root.nowSec)
          }

          // Last recording: local file (Upload / Open / Copy) or its link.
          Column {
            visible: root.finished
            width: parent.width
            spacing: Style.space(6)
            Hint { text: Omareel.shortShare(root.state, 48); elide: Text.ElideMiddle; wrapMode: Text.NoWrap }
            Row {
              width: parent.width
              spacing: Style.space(6)
              TextField {
                id: titleField
                width: parent.width - renameBtn.width - Style.space(6)
                placeholderText: root.canUpload ? "Title — Enter renames, Upload shares" : "Name — Enter renames the files"
                text: root.draftTitle
                onTextEdited: root.draftTitle = text
                onActiveFocusChanged: root.editing = activeFocus
                onAccepted: root.renameLast()
              }
              Button {
                id: renameBtn
                anchors.verticalCenter: parent.verticalCenter
                iconText: "󰏫"
                tooltipText: "Rename the video files"
                onClicked: root.renameLast()
              }
            }
            Row {
              spacing: Style.space(8)
              Button {
                visible: root.canUpload
                iconText: "󰅧"
                text: "Upload"
                active: true
                tooltipText: "Upload to " + Omareel.uploadSummary(root.config).replace(/^To /, "") + " and copy the link"
                onClicked: root.uploadLast()
              }
              Button {
                iconText: "󰏌"
                text: "Open"
                onClicked: {
                  var share = Omareel.shareTarget(root.state)
                  if (share) Util.execArgv(["xdg-open", share])
                }
              }
              Button {
                iconText: "󰆏"
                text: root.state.url ? "Copy link" : "Copy path"
                onClicked: {
                  var share = Omareel.shareTarget(root.state)
                  if (share) Util.execDetached("printf %s " + Omareel.shellQuote(share) + " | wl-copy")
                }
              }
              Button {
                visible: root.canUpload
                iconText: "󰅖"
                tooltipText: "Keep it local and clear this"
                onClicked: root.cliRun(["dismiss"])
              }
            }
          }

          PanelSeparator { width: parent.width; visible: root.finished }

          // Start buttons
          Heading { visible: root.idle || root.finished; text: "Record" }
          Row {
            visible: root.idle || root.finished
            width: parent.width
            spacing: Style.space(8)
            Button {
              iconText: "󰆞"
              text: "Area"
              tooltipText: "Drag a region, or click a window to snap to it"
              onClicked: root.start("area")
            }
            Button {
              iconText: "󰖯"
              text: "Window"
              tooltipText: "Pick an app; it stays captured even when covered (camera is composited in after Stop)"
              onClicked: root.start("window")
            }
            Button {
              iconText: "󰍹"
              text: "Screen"
              tooltipText: "The whole focused monitor"
              onClicked: root.start("screen")
            }
          }

          // Sources
          Heading { visible: root.idle || root.finished; text: "Sources" }
          Column {
            visible: root.idle || root.finished
            width: parent.width
            spacing: Style.space(4)

            Toggle {
              width: parent.width
              label: "Microphone"
              description: root.micOn ? Omareel.deviceLabel(root.devices.mics, Omareel.get(root.config, "micDevice", "default")) : "Off"
              checked: root.micOn
              onClicked: root.setConfig("mic", !root.micOn)
            }
            Dropdown {
              visible: root.micOn
              width: parent.width
              showLabel: false
              options: root.devices.mics
              value: String(Omareel.get(root.config, "micDevice", "default"))
              onChanged: function(v) { root.setConfig("micDevice", v) }
            }

            Toggle {
              width: parent.width
              label: "System audio"
              description: root.desktopOn ? Omareel.deviceLabel(root.devices.outputs, Omareel.get(root.config, "desktopDevice", "default")) : "Off"
              checked: root.desktopOn
              onClicked: root.setConfig("desktopAudio", !root.desktopOn)
            }
            Dropdown {
              visible: root.desktopOn
              width: parent.width
              showLabel: false
              options: root.devices.outputs
              value: String(Omareel.get(root.config, "desktopDevice", "default"))
              onChanged: function(v) { root.setConfig("desktopDevice", v) }
            }

            Toggle {
              width: parent.width
              label: "Camera"
              description: root.webcamOn
                ? (Omareel.cameraBusy(root.devices.cameras, Omareel.get(root.config, "webcamDevice", "auto"))
                   ? "Held by " + Omareel.cameraBusy(root.devices.cameras, Omareel.get(root.config, "webcamDevice", "auto")) + " — end that call or tab, or the camera is skipped"
                   : Omareel.deviceLabel(root.devices.cameras, Omareel.get(root.config, "webcamDevice", "auto")) + " · " + Omareel.get(root.config, "webcamSize", "medium"))
                : "Off — puts you in the corner of the video"
              checked: root.webcamOn
              onClicked: root.setConfig("webcam", !root.webcamOn)
            }
            Row {
              visible: root.webcamOn
              width: parent.width
              spacing: Style.space(6)
              Dropdown {
                width: parent.width - sizeDrop.width - Style.space(6)
                showLabel: false
                options: root.devices.cameras
                value: String(Omareel.get(root.config, "webcamDevice", "auto"))
                onChanged: function(v) { root.setConfig("webcamDevice", v) }
              }
              Dropdown {
                id: sizeDrop
                width: Style.space(110)
                showLabel: false
                options: [
                  { value: "small", label: "Small" },
                  { value: "medium", label: "Medium" },
                  { value: "large", label: "Large" },
                  { value: "xlarge", label: "Extra large" }
                ]
                value: String(Omareel.get(root.config, "webcamSize", "medium"))
                onChanged: function(v) { root.setConfig("webcamSize", v) }
              }
            }
          }

          // Options
          Heading { visible: root.idle || root.finished; text: "Options" }
          Column {
            visible: root.idle || root.finished
            width: parent.width
            Toggle {
              width: parent.width
              label: "Noise removal"
              description: "RNNoise clean-up of the microphone after recording"
              checked: root.denoiseOn
              onClicked: root.setConfig("denoise", !root.denoiseOn)
            }
            Row {
              visible: root.webcamOn
              width: parent.width
              spacing: Style.space(6)
              Dropdown {
                width: (parent.width - Style.space(6)) / 2
                options: [
                  { value: "frame", label: "Frame (16:9, rounded)" },
                  { value: "circle", label: "Circle" },
                  { value: "portrait", label: "Portrait (8:9)" }
                ]
                value: String(Omareel.get(root.config, "webcamShape", "frame"))
                onChanged: function(v) { root.setConfig("webcamShape", v) }
              }
              Dropdown {
                width: (parent.width - Style.space(6)) / 2
                options: [
                  { value: "bottom-right", label: "Bottom right" },
                  { value: "bottom-left", label: "Bottom left" },
                  { value: "top-right", label: "Top right" },
                  { value: "top-left", label: "Top left" }
                ]
                value: String(Omareel.get(root.config, "webcamCorner", "bottom-right"))
                onChanged: function(v) { root.setConfig("webcamCorner", v) }
              }
            }
            Toggle {
              width: parent.width
              label: "Upload every recording"
              description: root.uploadReady
                ? (root.uploadAuto ? Omareel.uploadSummary(root.config) + " · off: decide per video after Stop"
                                   : "Off · each recording gets an Upload button after Stop")
                : (root.provider === "none" ? "Set a destination in settings (gear)"
                                            : "Finish the destination in settings (gear)")
              checked: root.uploadAuto
              onClicked: {
                if (root.uploadReady) root.setConfig("upload.auto", !root.uploadAuto)
                else { root.message = ""; root.page = "settings" }
              }
            }
          }

          PanelSeparator { width: parent.width; visible: root.idle || root.finished }

          Row {
            visible: root.idle || root.finished
            spacing: Style.space(8)
            Button {
              iconText: "󰉋"
              text: "Recordings"
              tooltipText: "Rename, upload or copy earlier recordings"
              onClicked: { root.selectedFile = ""; root.page = "recordings" }
            }
            Button {
              iconText: "󰌷"
              text: "Copy last link"
              onClicked: { root.close(); root.cliRun(["last"]) }
            }
          }
        }

        // ================================================================
        // Recordings page: every recording in index.jsonl, newest first.
        // Click a row to rename it, upload it, or copy its link/path.
        // ================================================================
        Column {
          id: libraryColumn
          width: parent.width
          spacing: Style.space(8)
          visible: root.page === "recordings"

          Item {
            width: parent.width
            height: libBack.implicitHeight
            Button {
              id: libBack
              iconText: "󰁍"
              text: "Back"
              onClicked: { root.editing = false; root.page = "launcher" }
            }
            Text {
              anchors.centerIn: parent
              text: "Recordings"
              color: Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.title
              font.bold: true
            }
            Button {
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              iconText: "󰉋"
              tooltipText: "Open the folder"
              onClicked: { root.close(); root.cliRun(["open"]) }
            }
          }

          PanelSeparator { width: parent.width }

          Hint {
            visible: root.recordings.length === 0
            text: "Nothing recorded yet."
          }

          Repeater {
            model: root.recordings
            delegate: Column {
              id: row
              required property var modelData
              readonly property bool selected: root.selectedFile === String(modelData.file)
              readonly property bool shared: !!modelData.url
              width: libraryColumn.width
              spacing: Style.space(6)

              Rectangle {
                width: parent.width
                height: rowText.implicitHeight + Style.space(12)
                radius: Style.cornerRadius / 2
                color: row.selected ? Util.alpha(Color.accent, 0.12) : (rowHover.hovered ? Util.alpha(Color.popups.text, 0.06) : "transparent")
                HoverHandler { id: rowHover }
                TapHandler { onTapped: root.selectRecording(row.modelData) }
                Column {
                  id: rowText
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.margins: Style.space(8)
                  Text {
                    width: parent.width
                    text: Omareel.recordingName(row.modelData)
                    color: Color.popups.text
                    font.family: Style.font.family
                    font.pixelSize: Style.font.body
                    elide: Text.ElideMiddle
                  }
                  Text {
                    width: parent.width
                    text: Omareel.recordingMeta(row.modelData)
                    color: row.shared ? Color.accent : Color.popups.text
                    opacity: row.shared ? 0.9 : 0.6
                    font.family: Style.font.family
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                  }
                }
              }

              Column {
                visible: row.selected
                width: parent.width
                spacing: Style.space(6)
                leftPadding: Style.space(8)
                Row {
                  width: parent.width - Style.space(8)
                  spacing: Style.space(6)
                  TextField {
                    width: parent.width - saveNameBtn.width - Style.space(6)
                    placeholderText: "Name"
                    text: root.draftName
                    onTextEdited: root.draftName = text
                    onActiveFocusChanged: root.editing = activeFocus
                    onAccepted: root.renameSelected()
                  }
                  Button {
                    id: saveNameBtn
                    anchors.verticalCenter: parent.verticalCenter
                    iconText: "󰆓"
                    text: "Rename"
                    onClicked: root.renameSelected()
                  }
                }
                Flow {
                  width: parent.width - Style.space(8)
                  spacing: Style.space(6)
                  Button {
                    visible: !row.shared && root.uploadReady
                    iconText: "󰅧"
                    text: "Upload"
                    active: true
                    onClicked: root.uploadSelected()
                  }
                  Button {
                    iconText: "󰆏"
                    text: row.shared ? "Copy link" : "Copy path"
                    onClicked: root.cliRun(["copy", String(row.modelData.file)])
                  }
                  Button {
                    iconText: "󰏌"
                    text: "Open"
                    onClicked: Util.execArgv(["xdg-open", row.shared ? String(row.modelData.url) : String(row.modelData.file)])
                  }
                  Button {
                    visible: row.shared
                    iconText: "󰈔"
                    text: "Play file"
                    onClicked: Util.execArgv(["xdg-open", String(row.modelData.file)])
                  }
                }
              }
            }
          }
        }

        // ================================================================
        // Settings page
        // ================================================================
        Column {
          id: settingsColumn
          width: parent.width
          spacing: Style.space(10)
          visible: root.page === "settings"

          Item {
            width: parent.width
            height: backBtn.implicitHeight
            Button {
              id: backBtn
              iconText: "󰁍"
              text: "Back"
              onClicked: { root.editing = false; root.page = "launcher" }
            }
            Text {
              anchors.centerIn: parent
              text: "Settings"
              color: Color.popups.text
              font.family: Style.font.family
              font.pixelSize: Style.font.title
              font.bold: true
            }
            Text {
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              text: "v" + String(root.doctor.version || "")
              color: Color.popups.text
              opacity: 0.5
              font.family: Style.font.family
              font.pixelSize: Style.font.caption
            }
          }

          PanelSeparator { width: parent.width }

          // -- Recording --
          Heading { text: "Recording" }
          Row {
            width: parent.width
            spacing: Style.space(6)
            Dropdown {
              width: (parent.width - Style.space(12)) / 3
              label: "Frame rate"
              options: [ { value: "30", label: "30 fps" }, { value: "60", label: "60 fps" } ]
              value: String(Omareel.get(root.config, "fps", 30))
              onChanged: function(v) { root.setConfig("fps", parseInt(v)) }
            }
            Dropdown {
              width: (parent.width - Style.space(12)) / 3
              label: "Quality"
              options: [
                { value: "medium", label: "Medium" },
                { value: "high", label: "High" },
                { value: "very_high", label: "Very high" },
                { value: "ultra", label: "Ultra" }
              ]
              value: String(Omareel.get(root.config, "quality", "very_high"))
              onChanged: function(v) { root.setConfig("quality", v) }
            }
            Dropdown {
              width: (parent.width - Style.space(12)) / 3
              label: "Codec"
              options: [
                { value: "h264", label: "H.264 (plays everywhere)" },
                { value: "hevc", label: "HEVC (smaller)" },
                { value: "av1", label: "AV1 (smallest)" }
              ]
              value: String(Omareel.get(root.config, "codec", "h264"))
              onChanged: function(v) { root.setConfig("codec", v) }
            }
          }
          Toggle {
            width: parent.width
            label: "Keep the raw take"
            description: "Save <id>.raw.mp4 next to the cleaned-up file"
            checked: Omareel.get(root.config, "keepRaw", true) === true
            onClicked: root.setConfig("keepRaw", !(Omareel.get(root.config, "keepRaw", true) === true))
          }
          SettingField {
            label: "Recordings folder"
            path: "outputDir"
            placeholder: "~/Videos/Omareel"
          }

          // -- Noise removal --
          Heading { text: "Noise removal" }
          Dropdown {
            width: parent.width
            label: "Engine"
            options: [
              { value: "auto", label: "Auto (best available)" },
              { value: "ladspa", label: "RNNoise LADSPA plugin" },
              { value: "arnndn", label: "ffmpeg arnndn (RNNoise)" },
              { value: "afftdn", label: "ffmpeg afftdn (basic FFT)" },
              { value: "off", label: "Off" }
            ]
            value: String(Omareel.get(root.config, "denoiseEngine", "auto"))
            onChanged: function(v) { root.setConfig("denoiseEngine", v) }
          }
          Dropdown {
            width: parent.width
            label: "Strength"
            options: [
              { value: "light", label: "Light — most natural voice" },
              { value: "normal", label: "Normal — voice first, noise mostly gone" },
              { value: "strong", label: "Strong — noisy rooms; can sound thin" }
            ]
            value: String(Omareel.get(root.config, "denoiseStrength", "normal"))
            onChanged: function(v) { root.setConfig("denoiseStrength", v) }
          }
          Hint {
            text: "Active: " + String(root.doctor.engine || "…")
              + (root.doctor.ladspa === false ? "\nFor the most reliable clean-up:  sudo pacman -S noise-suppression-for-voice" : "")
          }

          // -- Sharing --
          Heading { text: "Sharing" }
          Dropdown {
            width: parent.width
            label: "Destination"
            options: Omareel.PROVIDERS
            value: root.provider
            onChanged: function(v) { root.message = ""; root.setConfig("upload.provider", v) }
          }
          Hint {
            visible: root.provider !== "none" && root.remoteStatus.rcloneInstalled === false
            text: "rclone is not installed:  sudo pacman -S rclone"
          }
          SettingField {
            visible: root.provider === "r2"
            label: "Cloudflare account ID"
            path: "upload.accountId"
            placeholder: "32 hex characters from the R2 overview page"
          }
          SettingField {
            visible: root.provider === "s3" || root.provider === "b2"
            label: root.provider === "b2" ? "Region — from the bucket's endpoint s3.<region>.backblazeb2.com" : "Region (e.g. us-east-1)"
            path: "upload.region"
            placeholder: root.provider === "b2" ? "us-west-004" : "us-east-1"
          }
          SettingField {
            visible: root.provider === "s3compat"
            label: "Endpoint URL"
            path: "upload.endpoint"
            placeholder: "https://s3.example.com"
          }
          SettingField {
            visible: root.provider === "existing"
            label: "rclone remote and path"
            path: "upload.remote"
            placeholder: "gdrive:Omareel  or  myremote:bucket/videos"
          }
          SettingField {
            visible: root.provider !== "none" && root.provider !== "existing"
            label: "Bucket"
            path: "upload.bucket"
          }
          SettingField {
            visible: root.provider !== "none" && root.provider !== "existing"
            label: "Folder inside the bucket (optional)"
            path: "upload.prefix"
          }
          SettingField {
            id: keyField
            visible: root.provider !== "none" && root.provider !== "existing"
            label: root.provider === "b2" ? "Key ID (keyID, 25 chars, starts with 00…)" : "Access key ID"
            path: ""
            placeholder: root.remoteStatus.hasSecret ? "saved — leave blank to keep" : ""
            onEdited: function(v) { root.draftKey = v }
          }
          SettingField {
            id: secretField
            visible: root.provider !== "none" && root.provider !== "existing"
            label: root.provider === "b2" ? "Application key (starts with K00…)" : "Secret access key"
            secret: true
            path: ""
            placeholder: root.remoteStatus.hasSecret ? "saved — leave blank to keep" : ""
            onEdited: function(v) { root.draftSecret = v }
          }
          SettingField {
            visible: root.provider !== "none"
            label: root.provider === "existing" ? "Public URL of that path (blank → rclone link)" : "Public URL of the bucket"
            path: "upload.publicBase"
            placeholder: root.provider === "b2" ? "https://f004.backblazeb2.com/file/<bucket>" : "https://pub-xxxx.r2.dev  or  https://v.yourdomain.com"
          }
          Toggle {
            visible: root.provider !== "none"
            width: parent.width
            label: "Upload a player page"
            description: "Share <id>.html with a poster and download link instead of the bare .mp4"
            checked: Omareel.get(root.config, "upload.playerPage", true) === true
            onClicked: root.setConfig("upload.playerPage", !(Omareel.get(root.config, "upload.playerPage", true) === true))
          }
          Row {
            visible: root.provider !== "none"
            spacing: Style.space(8)
            Button {
              iconText: "󰆓"
              text: "Save credentials"
              visible: root.provider !== "existing"
              active: root.draftKey !== "" && root.draftSecret !== ""
              onClicked: root.saveRemote()
            }
            Button {
              iconText: "󰐊"
              text: root.working ? "Working…" : "Test upload"
              onClicked: if (!root.working) root.testRemote()
            }
          }
          Hint {
            visible: root.message !== ""
            opacity: 0.9
            text: root.message
          }
          Hint {
            visible: root.provider !== "none"
            text: "Credentials are written to ~/.config/rclone/rclone.conf (mode 600) and never to omareel.json."
          }

          // -- Setup --
          Heading { text: "Setup" }
          Hint {
            text: (root.doctor.linked === true ? "CLI on PATH: ~/.local/bin/omareel"
                                                : "Put the CLI on your PATH so keybindings can call it:")
          }
          Button {
            visible: root.doctor.linked !== true
            iconText: "󰌷"
            text: "Link omareel into ~/.local/bin"
            onClicked: linkProc.running = true
          }
          Hint {
            text: "Suggested keybinding (~/.config/hypr/bindings.lua):\n"
              + "o.bind(\"SUPER + SHIFT + R\", \"Omareel\", \"omareel toggle\")"
          }
          Hint {
            visible: Array.isArray(root.doctor.missing) && root.doctor.missing.length > 0
            text: "Missing tools: " + (root.doctor.missing || []).join(", ")
          }
        }
      }
    }
  }
}
