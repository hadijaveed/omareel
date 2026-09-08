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
  property bool reopening: __REOPEN__
  property var remembered: null
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
  function control(item, label) {
    if (item.label === label) return item
    for (var i=0; i<item.children.length; ++i) {
      var found = control(item.children[i], label)
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
        Component.onCompleted: begin(__VIDEO__, __SAVED_STYLE__)
        onStyleSaved: function(saved) { remembered = saved }
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
        if (reopening) {
          if (!expect(JSON.stringify(editor.style) === JSON.stringify(__SAVED_STYLE__), "New UI process must restore the stored style")) return
          if (!expect(control(editor,"Spacing").value === "small" && control(editor,"Frame").value === "rounded", "Restored controls must show Compact and Rounded")) return
          editor.adjusting = true
          editor.cli = __FAIL_CLI__
          control(editor,"Spacing").changed("large")
          stage = 10
          return
        }
        if (!expect(JSON.stringify(editor.defaults()) === JSON.stringify(__DEFAULTS__), "QML/backend defaults diverge")) return
        if (!expect(button(editor,"Export styled copy").enabled, "Valid preview should enable export")) return
        if (!expect(!button(editor,"Add zoom here"), "Manual zoom controls must be absent")) return
        if (!expect(!button(editor,"Remember style"), "Style changes must not need a separate save button")) return
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
        button(editor,"Reset").clicked()
        stage = 3
      } else if (stage === 3 && !editor.waiting && !editor.savingPreferences && editor.renderedRevision === editor.revision) {
        if (!expect(!editor.adjusting && editor.style.zoom === "1", "Reset restores a compact, unzoomed draft")) return
        if (!expect(JSON.stringify(remembered) === JSON.stringify(__DEFAULTS__), "Reset must also save defaults")) return
        editor.adjusting = true
        control(editor,"Frame").changed("none")
        control(editor,"Spacing").changed("large")
        control(editor,"Frame").changed("rounded")
        control(editor,"Spacing").changed("small")
        control(editor,"Soft shadow").clicked()
        control(editor,"Canvas").changed("landscape")
        stage = 4
      } else if (stage === 4 && !editor.savingPreferences && !editor.waiting && editor.renderedRevision === editor.revision) {
        if (!expect(!editor.styleSaveError && remembered.padding === "small" && remembered.frame === "rounded"
                    && remembered.shadow === false && remembered.aspect === "landscape", "Latest rapid adjustments must win")) return
        editor.exportCopy()
        stage = 5
      } else if (stage === 5 && completed) {
        expect(observedExport && !editor.exporting && editor.feedback === "", "Export completion")
        console.log("STUDIO NATIVE PASS: preview, stale response, reset, automatic preferences and export")
        Qt.quit()
      } else if (stage === 10 && !editor.savingPreferences && editor.styleSaveError !== "") {
        if (!expect(button(editor,"Retry save").visible, "Save failures need a visible retry")) return
        editor.cli = __CLI__
        button(editor,"Retry save").clicked()
        stage = 11
      } else if (stage === 11 && !editor.savingPreferences && editor.styleSaveError === "") {
        if (!expect(remembered.padding === "large", "Retry must save the current style")) return
        console.log("STUDIO NATIVE PASS: restored preferences across process restart, save failure and retry")
        Qt.quit()
      }
    }
  }
}
