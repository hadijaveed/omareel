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

  readonly property string cli: decodeURIComponent(String(Qt.resolvedUrl("bin/omareel")).replace(/^file:\/\//, ""))
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
  property bool confirmDiscard: false
  property string draftKey: ""
  property string draftSecret: ""

  readonly property string phase: Omareel.phaseOf(state)
  readonly property bool recording: phase === "recording"
  readonly property bool busy: startProc.running || phase === "picking" || phase === "starting" || phase === "processing" || phase === "uploading"
  readonly property bool finished: phase === "done"
  readonly property bool idle: phase === "idle" || phase === "error"
  onPhaseChanged: confirmDiscard = false
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
    if (root.busy || root.recording) return
    root.close()
    startProc.command = [root.cli, "start", kind]
    startProc.running = true
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
    if (!root.remoteStatus.hasSecret || root.draftKey || root.draftSecret) {
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
    if (!root.uploadReady) {
      root.message = root.remoteStatus.message || "Finish the destination settings and save credentials first"
      remoteProc.running = true
      return
    }
    root.message = "Testing… uploading a probe file"
    root.working = true
    testProc.running = true
  }

  onOpenedChanged: if (opened) {
    root.editing = false
    root.confirmDiscard = false
    refreshAll()
    Qt.callLater(function() { contentViewport.contentY = 0 })
  }
  onPageChanged: Qt.callLater(function() { contentViewport.contentY = 0 })

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
    path: Quickshell.env("OMAREEL_CONFIG") || root.home + "/.config/omarchy/omareel.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      root.config = Omareel.parseJson(text(), {})
      remoteRefresh.restart()
    }
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

  Timer {
    id: remoteRefresh
    interval: 150
    onTriggered: {
      if (remoteProc.running) restart()
      else remoteProc.running = true
      if (!doctorProc.running) doctorProc.running = true
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
    onExited: function(code) {
      if (code !== 0) root.doctor = { ready: false, errors: ["Setup check could not run. Install the README requirements and check the settings file."], warnings: [] }
    }
  }

  Process {
    id: startProc
    stderr: StdioCollector { id: startErr; waitForEnd: true }
    onExited: function(code) {
      stateFile.reload()
      if (code !== 0 && code !== 75) {
        root.message = String(startErr.text || "").trim()
        root.page = "launcher"
        root.open()
      }
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
      root.message = (code === 0 ? "" : "Test failed\n") + ([out, err].filter(function(v) { return v !== "" }).join("\n") || "exit " + code)
    }
  }

  Process {
    id: linkProc
    command: [root.cli, "setup", "--link"]
    stdout: StdioCollector { id: setupOut; waitForEnd: true }
    stderr: StdioCollector { id: setupErr; waitForEnd: true }
    onExited: function(code) {
      root.message = (code === 0 ? "Setup complete\n" : "Setup incomplete\n")
        + [String(setupOut.text || "").trim(), String(setupErr.text || "").trim()].filter(function(v) { return v !== "" }).join("\n")
      doctorProc.running = true
    }
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

  // Window/Screen recordings deliberately hide the floating controls because
  // KMS would burn them into the video. Make their safe replacement in the
  // reserved system bar impossible to miss, while keeping the compact icon
  // when idle. Omarchy's bar wrapper already makes every module draggable.
  Rectangle {
    anchors.fill: parent
    anchors.margins: Style.space(1)
    visible: root.recording
    radius: height / 2
    color: Util.alpha(root.bar ? root.bar.urgent : Color.urgent, 0.88)
    border.width: Math.max(1, Style.space(1))
    border.color: root.bar ? root.bar.urgent : Color.urgent
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.recording ? "●  REC  " + root.elapsed + "  ·  STOP" : (root.busy ? "󰑊 …" : "󰑊")
    fontSize: Style.font.body
    horizontalMargin: root.recording ? 14 : 8.5
    foreground: root.recording ? "#ffffff" : (root.bar ? root.bar.barForeground : Color.foreground)
    useActiveColor: !root.recording
    active: root.recording
    tooltipText: root.recording
      ? "Recording — click to stop · right-click for controls · drag to move"
      : "Omareel: record & share"
    onPressed: function(b) {
      if (b === Qt.LeftButton) {
        if (root.recording) root.cliRun(["stop"])
        else { root.page = "launcher"; root.toggle() }
      } else if (b === Qt.RightButton) {
        if (root.recording) root.open()
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
        id: contentViewport
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
              text: "Stop & save"
              active: true
              onClicked: { root.close(); root.cliRun(["stop"]) }
            }
            Button {
              iconText: "󰆴"
              text: root.confirmDiscard ? "Confirm discard" : "Discard"
              onClicked: {
                if (root.confirmDiscard) { root.close(); root.cliRun(["cancel"]) }
                else root.confirmDiscard = true
              }
            }
          }

          Hint {
            visible: root.busy && !root.recording
            opacity: 1
            text: Omareel.statusText(root.state, root.nowSec)
          }

          // Readiness is guidance, not a claim that this laptop is certified.
          Column {
            visible: root.idle || root.finished
            width: parent.width
            spacing: Style.space(6)
            Heading { text: root.phase === "error" ? "Recording did not start" : root.doctor.ready === true ? "Ready to record" : "Check your setup" }
            Hint {
              opacity: 1
              text: root.phase === "error" ? Omareel.statusText(root.state, root.nowSec)
                : root.doctor.ready === true ? "Choose a source below. Start with a short test to check picture and sound."
                  + ((root.doctor.warnings || []).length ? "\n" + root.doctor.warnings.join("\n") : "")
                : doctorProc.running ? "Checking recording tools and devices…"
                : (root.doctor.errors || ["Open Settings to check this laptop before your first recording."]).join("\n")
            }
            Flow {
              width: parent.width
              spacing: Style.space(6)
              visible: root.phase === "error" || root.doctor.ready !== true
              Button { text: "Check again"; enabled: !doctorProc.running; onClicked: root.refreshAll() }
              Button { text: "Setup & details"; onClicked: { root.message = ""; root.page = "settings" } }
              Button { visible: root.phase === "error"; text: "Dismiss"; onClicked: root.cliRun(["dismiss"]) }
            }
          }

          // Last recording: local file (Upload / Open / Copy) or its link.
          Column {
            visible: root.finished
            width: parent.width
            spacing: Style.space(6)
            Hint { visible: String(root.state.warning || "") !== ""; opacity: 1; text: String(root.state.warning || "") }
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
              tooltipText: Omareel.get(root.config, "windowCaptureMode", "region") === "portal"
                ? "Portal capture: stays captured when covered, but can fail if the window resizes"
                : "Reliable capture: pick a visible window and keep it in place during the recording"
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
                   ? "Held by " + Omareel.cameraBusy(root.devices.cameras, Omareel.get(root.config, "webcamDevice", "auto")) + " — close it before recording"
                   : Omareel.deviceLabel(root.devices.cameras, Omareel.get(root.config, "webcamDevice", "auto"))
                     + " · " + Omareel.get(root.config, "webcamSize", "medium")
                     + " · " + Omareel.get(root.config, "webcamPosition", Omareel.get(root.config, "webcamCorner", "bottom-right")))
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
            Row {
              visible: root.webcamOn
              width: parent.width
              spacing: Style.space(6)
              Dropdown {
                width: (parent.width - Style.space(6)) / 2
                options: [
                  { value: "frame", label: "Landscape (16:9)" },
                  { value: "classic", label: "Rectangle (4:3)" },
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
                  { value: "bottom-center", label: "Bottom center" },
                  { value: "bottom-left", label: "Bottom left" },
                  { value: "center-right", label: "Right center" },
                  { value: "center-left", label: "Left center" },
                  { value: "top-right", label: "Top right" },
                  { value: "top-center", label: "Top center" },
                  { value: "top-left", label: "Top left" }
                ]
                value: String(Omareel.get(root.config, "webcamPosition", Omareel.get(root.config, "webcamCorner", "bottom-right")))
                onChanged: function(v) { root.setConfig("webcamPosition", v) }
              }
            }
            Dropdown {
              visible: root.webcamOn
              width: parent.width
              label: "Camera crop"
              options: [
                { value: "full", label: "Full — widest view" },
                { value: "close", label: "Close — 1.25×" },
                { value: "tight", label: "Tight — 1.5×" }
              ]
              value: String(Omareel.get(root.config, "webcamZoom", "full"))
              onChanged: function(v) { root.setConfig("webcamZoom", v) }
            }
            Hint {
              visible: root.webcamOn
              text: "Placement and crop are locked when recording starts, so the self-view and exported video stay matched."
            }
          }

          Heading { visible: root.idle || root.finished; text: "Sound & sharing" }
          Column {
            visible: root.idle || root.finished
            width: parent.width
            spacing: Style.space(4)
            Toggle {
              width: parent.width
              label: "Voice clean-up"
              description: "Reduce background noise after Stop. Stronger cleanup can change the sound of your voice."
              checked: root.denoiseOn
              onClicked: root.setConfig("denoise", !root.denoiseOn)
            }
            Dropdown {
              visible: root.denoiseOn && root.micOn
              width: parent.width
              label: "Voice sound"
              options: [
                { value: "light", label: "Natural — gentle cleanup" },
                { value: "normal", label: "Clean — balanced" },
                { value: "strong", label: "Strong — noisy rooms" }
              ]
              value: String(Omareel.get(root.config, "denoiseStrength", "normal"))
              onChanged: function(v) { root.setConfig("denoiseStrength", v) }
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
          Dropdown {
            width: parent.width
            label: "Window capture"
            options: [
              { value: "region", label: "Reliable — visible window region" },
              { value: "portal", label: "Portal — occlusion-safe, resize-sensitive" }
            ]
            value: String(Omareel.get(root.config, "windowCaptureMode", "region"))
            onChanged: function(v) { root.setConfig("windowCaptureMode", v) }
          }
          Hint {
            text: "Reliable mode uses fixed dimensions so a browser resize cannot freeze the screen track."
          }
          SettingField {
            label: "Recordings folder"
            path: "outputDir"
            placeholder: "~/Videos/Omareel"
          }

          // -- Noise removal --
          Heading { text: "Noise removal" }
          Toggle {
            width: parent.width
            label: "Set microphone volume when recording"
            description: "Off preserves your system level. Does not unmute the microphone."
            checked: Omareel.get(root.config, "manageMicVolume", false) === true
            onClicked: root.setConfig("manageMicVolume", !(Omareel.get(root.config, "manageMicVolume", false) === true))
          }
          Dropdown {
            visible: Omareel.get(root.config, "manageMicVolume", false) === true
            width: parent.width
            label: "Recording input level"
            options: [
              { value: "60", label: "60% — sensitive microphone" },
              { value: "70", label: "70%" },
              { value: "80", label: "80%" },
              { value: "90", label: "90%" },
              { value: "100", label: "100% — quiet microphone" }
            ]
            value: String(Omareel.get(root.config, "micVolumePercent", 80))
            onChanged: function(v) { root.setConfig("micVolumePercent", parseInt(v)) }
          }
          Hint {
            text: "Use system audio settings to choose a comfortable level. Different microphones need different gain."
          }
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
              { value: "light", label: "Natural — minimal processing" },
              { value: "normal", label: "Clean — balanced voice and noise reduction" },
              { value: "strong", label: "Strong — more isolation, less natural tone" }
            ]
            value: String(Omareel.get(root.config, "denoiseStrength", "normal"))
            onChanged: function(v) { root.setConfig("denoiseStrength", v) }
          }
          Hint {
            text: "Active: " + String(root.doctor.engine || "…")
              + " · microphone only · 48 kHz mono"
              + (root.doctor.micVolumePercent !== null && root.doctor.micVolumePercent !== undefined
                  ? "\nCurrent system input: " + String(root.doctor.micVolumePercent) + "%. Check a short sample before a full take." : "")
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
            visible: root.provider === "s3" || root.provider === "b2" || root.provider === "s3compat"
            label: root.provider === "b2" ? "Region — from the bucket's endpoint s3.<region>.backblazeb2.com" : root.provider === "s3compat" ? "Region (if required by your S3 service)" : "Region (e.g. us-east-1)"
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
            label: root.provider === "existing" ? "Public URL of that path (optional)" : "Public URL of the bucket (optional; folder added automatically)"
            path: "upload.publicBase"
            placeholder: root.provider === "b2" ? "https://f004.backblazeb2.com/file/<bucket>" : "https://pub-xxxx.r2.dev  or  https://v.yourdomain.com"
          }
          Toggle {
            visible: root.provider !== "none"
            width: parent.width
            label: "Upload a player page"
            description: "Requires a public URL. Otherwise share the provider's video link."
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
              onClicked: if (!root.working) root.saveRemote()
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
            text: "Leave Public URL blank for provider-generated links (S3: up to 7 days). Test upload checks storage, share access and deletion using only a tiny probe."
          }
          Hint {
            visible: root.provider !== "none"
            text: "Credentials are written to ~/.config/rclone/rclone.conf (mode 600) and never to omareel.json."
          }

          // -- Setup --
          Heading { text: "Setup" }
          Hint { opacity: 1; text: (root.doctor.errors || []).concat(root.doctor.warnings || []).join("\n"); visible: text.length > 0 }
          Hint {
            text: (root.doctor.linked === true ? "CLI on PATH: ~/.local/bin/omareel"
                                                : "Put the CLI on your PATH so keybindings can call it:")
          }
          Button {
            enabled: !linkProc.running && !root.busy && !root.recording
            iconText: "󰌷"
            text: linkProc.running ? "Checking setup…" : "Check setup & install voice models"
            onClicked: { root.message = "Checking this laptop…"; linkProc.running = true }
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
