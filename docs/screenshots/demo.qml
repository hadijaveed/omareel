// Fictional documentation app used only as safe example recording content.
import QtQuick
import QtQuick.Window
import Quickshell

ShellRoot {
  component Copy: Text {
    textFormat: Text.PlainText
    font.family: "DejaVu Sans"
    font.pixelSize: 18
    color: "#253047"
  }
  Window {
    id: window
    width: 1280; height: 800; visible: true; color: "#f6f7fb"
    Rectangle { anchors.fill: parent; color: window.color }
    Rectangle {
      width: 242; height: parent.height; color: "#172334"
      Copy { x: 32; y: 38; text: "fieldnotes"; color: "#ffffff"; font.pixelSize: 29; font.bold: true }
      Copy { x: 32; y: 98; text: "YOUR WORKSPACE"; color: "#8fa1b9"; font.pixelSize: 12; font.letterSpacing: 1.5 }
      Repeater {
        model: ["Overview", "Documents", "Release notes", "Settings"]
        Rectangle {
          required property int index
          required property string modelData
          x: 18; y: 136 + index * 55; width: 206; height: 43; radius: 8
          color: index === 2 ? "#2e4565" : "transparent"
          Copy { x: 16; anchors.verticalCenter: parent.verticalCenter; text: modelData; color: index === 2 ? "#ffffff" : "#adbcd0"; font.pixelSize: 16 }
        }
      }
      Copy { x: 32; y: 736; text: "Example workspace"; color: "#8fa1b9"; font.pixelSize: 14 }
    }
    Copy { x: 286; y: 40; text: "Documents  /  Release notes"; color: "#69768d"; font.pixelSize: 15 }
    Rectangle { x: 1110; y: 26; width: 122; height: 42; radius: 8; color: "#e5ebf7"
      Copy { anchors.centerIn: parent; text: "Preview"; font.pixelSize: 15; color: "#355789" }
    }
    Rectangle { x: 242; y: 92; width: 1038; height: 1; color: "#e1e5ed" }
    Copy { x: 300; y: 133; text: "SEPTEMBER UPDATE"; font.pixelSize: 12; font.bold: true; font.letterSpacing: 1.6; color: "#5274ac" }
    Copy { x: 300; y: 174; text: "Small changes.\nA better place to work."; font.pixelSize: 40; font.bold: true; lineHeight: 1.15 }
    Copy { x: 302; y: 292; text: "A quick look at what's new in your workspace."; color: "#69768d"; font.pixelSize: 19 }
    Rectangle { x: 300; y: 356; width: 612; height: 326; color: "#ffffff"; radius: 14; border.color: "#e1e5ed"
      Copy { x: 28; y: 25; text: "A little less searching"; font.bold: true; font.pixelSize: 22 }
      Copy { x: 28; y: 68; text: "Keep useful things close. Get back to your work."; color: "#69768d"; font.pixelSize: 16 }
      Repeater {
        model: ["Pin the documents you reach for every day", "Find your recent work in one place", "Share a page when it's ready"]
        Row {
          required property int index
          required property string modelData
          x: 28; y: 127 + index * 55; spacing: 16
          Rectangle { width: 27; height: 27; radius: 8; color: "#e8f1ed"
            Copy { anchors.centerIn: parent; text: "✓"; color: "#3c7d61"; font.pixelSize: 16 }
          }
          Copy { text: modelData; font.pixelSize: 16; anchors.verticalCenter: parent.verticalCenter }
        }
      }
    }
    Rectangle { x: 940; y: 356; width: 292; height: 326; color: "#eaf0fb"; radius: 14
      Copy { x: 24; y: 26; text: "IN THIS UPDATE"; color: "#5274ac"; font.pixelSize: 12; font.bold: true; font.letterSpacing: 1 }
      Copy { x: 24; y: 75; text: "01   Your everyday docs\n\n02   A tidier workspace\n\n03   Ready to share"; font.pixelSize: 16; color: "#405574" }
      Rectangle { x: 24; y: 240; width: 244; height: 54; radius: 9; color: "#385c96"
        Copy { anchors.centerIn: parent; text: "Open your workspace  →"; color: "#ffffff"; font.pixelSize: 15 }
      }
    }
    Copy { x: 302; y: 726; text: "Made for the work you do every day."; font.pixelSize: 15; color: "#7b879c" }
  }
  Timer { interval: 450; running: true; onTriggered: window.contentItem.grabToImage(function(result) {
      if (!result.saveToFile(__OUTPUT__)) throw new Error("Could not save demo image")
      Qt.quit()
  }) }
}
