import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import Quickshell.Hyprland
import qs.Commons
import qs.Ui
import "Omareel.js" as Omareel

// Floating Omareel controls. A click-through full-screen layer with one small
// card: red dot + timer + target while recording (Stop / Discard), then the
// processing and upload progress, then "link copied" with Open / Copy.
//
// Hidden for whole-screen recordings, where it would end up in the video.
// For area recordings it moves to the bottom edge if the region covers the
// top-centre spot. State comes from $XDG_RUNTIME_DIR/omareel/state.json,
// written by bin/omareel.
Item {
  id: root

  property var shell: null
  property var manifest: null
  property string omarchyPath: ""

  readonly property string cli: String(Qt.resolvedUrl("bin/omareel")).replace(/^file:\/\//, "")
  readonly property string runtimeDir: (Quickshell.env("XDG_RUNTIME_DIR") || "/tmp") + "/omareel"

  property var state: ({ phase: "idle" })
  property int nowSec: Math.floor(Date.now() / 1000)
  property bool dismissed: false
  property var targetScreen: null

  readonly property string phase: Omareel.phaseOf(state)
  readonly property bool recording: phase === "recording"
  readonly property bool busy: phase === "processing" || phase === "uploading"
  readonly property bool finished: phase === "done"
  readonly property bool wholeScreen: state && String(state.targetKind || "") === "screen"

  readonly property bool showControls: !dismissed
    && ((recording && !wholeScreen) || busy || finished)

  // Shell routing contract (summon / hide / toggle).
  readonly property bool opened: showControls
  function open(payloadJson) { dismissed = false }
  function close() { dismissed = true }

  function cliRun(args) { Util.execArgv([root.cli].concat(args)) }

  onPhaseChanged: {
    if (phase === "picking" || phase === "recording") {
      dismissed = false
      var focused = Hyprland.focusedMonitor ? Hyprland.focusedMonitor.name : ""
      targetScreen = Omareel.screenNamed(Quickshell.screens, focused)
    }
    if (phase === "idle") dismissed = false
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

  FileView {
    path: root.runtimeDir
    watchChanges: true
    printErrors: false
    onFileChanged: stateFile.reload()
  }

  Process {
    command: [root.cli, "status"]
    running: true
    onExited: function() { stateFile.reload() }
  }

  Timer {
    interval: 1000
    repeat: true
    running: root.recording || root.busy
    triggeredOnStart: true
    onTriggered: root.nowSec = Math.floor(Date.now() / 1000)
  }

  PanelWindow {
    id: window
    visible: root.showControls
    screen: root.targetScreen
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "omareel"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    exclusionMode: ExclusionMode.Ignore
    // Only the card takes clicks; the rest of the layer is transparent to input.
    mask: Region { item: card }

    BorderSurface {
      id: card

      readonly property int pad: Style.space(10)
      readonly property int topOffset: Style.bar.sizeHorizontal + Style.gapsOut * 2
      readonly property bool atBottom: Omareel.placeAtBottom(root.state, window.screen, width, height, topOffset)

      width: row.implicitWidth + pad * 2 + borderLeft + borderRight
      height: row.implicitHeight + pad * 2 + borderTop + borderBottom
      anchors.horizontalCenter: parent.horizontalCenter
      anchors.top: atBottom ? undefined : parent.top
      anchors.bottom: atBottom ? parent.bottom : undefined
      anchors.topMargin: topOffset
      anchors.bottomMargin: Style.space(28)
      color: Util.alpha(Color.popups.background, 0.96)
      borderSpec: Border.surfaceSpec("popups", "border", Color.popups.border, Math.max(1, Style.space(2)))
      radius: Style.cornerRadius

      Row {
        id: row
        anchors.centerIn: parent
        spacing: Style.space(10)

        Rectangle {
          id: dot
          anchors.verticalCenter: parent.verticalCenter
          width: Style.space(10)
          height: width
          radius: width / 2
          color: root.recording ? Color.urgent : Color.accent
          visible: root.recording || root.busy
          SequentialAnimation on opacity {
            running: dot.visible
            loops: Animation.Infinite
            NumberAnimation { to: 0.2; duration: 700; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1.0; duration: 700; easing.type: Easing.InOutSine }
          }
        }

        Text {
          anchors.verticalCenter: parent.verticalCenter
          visible: root.finished
          text: "󰄬"
          color: Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.icon
        }

        Text {
          anchors.verticalCenter: parent.verticalCenter
          text: Omareel.statusText(root.state, root.nowSec)
          color: Color.popups.text
          font.family: Style.font.family
          font.pixelSize: Style.font.body
        }

        Button {
          anchors.verticalCenter: parent.verticalCenter
          visible: root.recording
          iconText: "󰓛"
          text: "Stop"
          tooltipText: "Stop, clean up, and share"
          active: true
          onClicked: root.cliRun(["stop"])
        }
        Button {
          anchors.verticalCenter: parent.verticalCenter
          visible: root.recording
          iconText: "󰆴"
          tooltipText: "Discard recording"
          onClicked: root.cliRun(["cancel"])
        }

        Button {
          anchors.verticalCenter: parent.verticalCenter
          visible: root.finished
          iconText: "󰏌"
          text: "Open"
          onClicked: {
            var share = Omareel.shareTarget(root.state)
            if (share) Util.execArgv(["xdg-open", share])
          }
        }
        Button {
          anchors.verticalCenter: parent.verticalCenter
          visible: root.finished
          iconText: "󰆏"
          text: "Copy"
          onClicked: {
            var share = Omareel.shareTarget(root.state)
            if (share) Util.execDetached("printf %s " + Omareel.shellQuote(share) + " | wl-copy")
          }
        }
        Button {
          anchors.verticalCenter: parent.verticalCenter
          visible: !root.recording
          iconText: "󰅖"
          tooltipText: "Hide"
          onClicked: root.close()
        }
      }
    }
  }
}
