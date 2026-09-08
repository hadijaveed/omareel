// Run through studio-native.py; native controls and real CLI, isolated state.
import QtQuick
import QtQuick.Window
import Quickshell
import qs.Commons as Commons

ShellRoot {
  property int stage: 0
  property int ticks: 0
  property bool completed: false
  property bool observedExport: false
  property bool failed: false
  function expect(condition, message) {
    if (!condition) { failed = true; console.error("STUDIO TEST FAIL", message); Qt.quit() }
    return condition
  }
  function button(item, label) {
    if (item.text === label && item.clicked !== undefined) return item
    for (var i=0; i<item.children.length; ++i) {
      var found = button(item.children[i], label)
      if (found) return found
    }
    return null
  }
  Window {
    id: window
    visible: true; width: 600; height: 800
    color: Commons.Color.popups.background
    Flickable {
      anchors.fill: parent
      anchors.margins: 20
      clip: true
      contentHeight: editor.implicitHeight
      StudioEditor {
        id: editor
        width: parent.width
        cli: __CLI__
        Component.onCompleted: begin(__VIDEO__, {})
        onFinished: completed = true
        onExportingChanged: if (exporting) {
          observedExport = true
          Qt.callLater(function() { expect(!button(editor,"Use original").enabled, "Cannot change selection mid-export") })
        }
      }
    }
  }
  Timer {
    interval: 100; running: true; repeat: true
    onTriggered: {
      ticks++
      if (ticks > 500) { expect(false, "Timed out at stage " + stage + ": " + editor.feedback); return }
      if (failed) return
      if (stage === 0 && !editor.waiting && editor.renderedRevision === editor.revision) {
        if (!expect(JSON.stringify(editor.defaults()) === JSON.stringify(__DEFAULTS__), "QML/backend defaults diverge")) return
        if (!expect(button(editor,"Export styled copy").enabled, "Valid preview should enable export")) return
        window.contentItem.grabToImage(function(result) { result.saveToFile(__SCREENSHOT__) })
        editor.preset("paper")
        editor.preview() // Start a request, then change settings while it runs.
        editor.change("zoom","1.25")
        editor.change("aspect","portrait")
        editor.change("focus","top-right")
        stage = 1
      } else if (stage === 1 && !editor.waiting && editor.renderedRevision === editor.revision) {
        if (!expect(editor.previewLabel.indexOf("180 × 320") === 0, "Stale preview won over latest portrait draft")) return
        editor.adjusting = true
        if (!expect(editor.style.frame === "application", "Paper preset frame")) return
        editor.change("background","image")
        editor.change("image","/missing/studio-background.png")
        stage = 2
      } else if (stage === 2 && !editor.waiting && editor.feedback !== "") {
        if (!expect(editor.renderedRevision === -1 && !button(editor,"Export styled copy").enabled,
                    "Failed preview must disable export")) return
        editor.begin(__VIDEO__, {})
        stage = 3
      } else if (stage === 3 && !editor.waiting && editor.renderedRevision === editor.revision) {
        if (!expect(!editor.adjusting && editor.style.zoom === "1", "Reset restores a compact, unzoomed draft")) return
        button(editor,"Remember style").clicked()
        stage = 4
      } else if (stage === 4 && editor.feedback === "Style saved for your next Studio recording.") {
        editor.seek(0.2)
        editor.addZoom()
        editor.editZoom(0,"end",1.2)
        editor.beginPick(0)
        stage = 5
      } else if (stage === 5 && !editor.waiting && editor.renderedRevision === editor.revision) {
        if (!expect(!button(editor,"Export styled copy").enabled, "Choose focus before exporting")) return
        editor.pickPoint(0.8,0.2)
        stage = 6
      } else if (stage === 6 && !editor.waiting && editor.renderedRevision === editor.revision) {
        if (!expect(editor.pickingZoom === -1 && editor.style.zooms[0].x === 0.8
                    && editor.style.zooms[0].y === 0.2 && Math.abs(editor.style.previewTime-0.7)<0.01,
                    "Click focus and timed preview must be preserved")) return
        if (!expect(!editor.saveZooms([editor.style.zooms[0],editor.style.zooms[0]]), "Reject overlapping zooms")) return
        editor.exportCopy()
        stage = 7
      } else if (stage === 7 && completed) {
        expect(observedExport && !editor.exporting && editor.feedback === "", "Export completion")
        console.log("STUDIO NATIVE PASS: preview, stale response, presets, failure, reset, save, timed click zoom and export")
        Qt.quit()
      }
    }
  }
}
