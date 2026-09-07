import QtQuick
import QtQuick.Controls
import QtTest

Item {
  id: root
  width: 1200
  height: 900
  property string message: ""
  property bool working: true
  property string payload: __PAYLOAD__
  property string baseUrl: __BASE__
  QtObject { id: testOut; property string text: __STDOUT__ }
  QtObject { id: testErr; property string text: __STDERR__ }
  function completeUploadTest(code) { __HANDLER__ }

  // Production Hint and production process-exit handler are extracted verbatim.
  Hint { id: hint; text: root.message }
  Hint { id: expected; y: 180; text: "Test failed\nUpload failed: " + root.payload; textFormat: Text.PlainText }
  PlainToggle { id: toggle; y: 350; width: 800; onClicked: checked = !checked }
  PlainDropdown {
    id: dropdown
    y: 450
    width: 1000
    property string selected: ""
    onChanged: function(value) { selected = value }
  }
  Text { id: vulnerable; y: 700; textFormat: Text.AutoText }

  TestCase {
    name: "UntrustedText"
    when: windowShown

    function assertPlainTree(item) {
      if (item.textFormat !== undefined) compare(item.textFormat, Text.PlainText)
      for (var i = 0; i < item.children.length; ++i) assertPlainTree(item.children[i])
    }

    function test_01_real_error_is_literal() {
      root.completeUploadTest(1)
      compare(root.working, false)
      compare(root.message, "Test failed\nUpload failed: " + root.payload)
      compare(hint.text, expected.text)
      compare(hint.textFormat, Text.PlainText)
      wait(250)
      verify(grabImage(hint).equals(grabImage(expected)), "Error glyphs match a literal plain-text reference")
    }

    function test_02_device_controls_and_interaction() {
      toggle.label = root.payload
      toggle.description = root.payload
      assertPlainTree(toggle)
      mouseClick(toggle, 10, 10)
      compare(toggle.checked, true)

      dropdown.label = root.payload
      dropdown.options = [{value: "device-one", label: root.payload}, {value: "device-two", label: "Other device"}]
      dropdown.value = "device-one"
      compare(dropdown.currentLabel(), root.payload)
      assertPlainTree(dropdown)
      dropdown.open()
      tryCompare(dropdown, "popupOpen", true)
      wait(250) // exercise lazy popup delegates containing hostile labels
      assertPlainTree(Overlay.overlay)
      keyClick(Qt.Key_Down)
      keyClick(Qt.Key_Return)
      compare(dropdown.selected, "device-two")
      tryCompare(dropdown, "popupOpen", false)
      dropdown.value = root.payload // missing-device/config fallback must also be literal
      compare(dropdown.currentLabel(), root.payload)
      assertPlainTree(dropdown)
      wait(500)
    }

    function test_03_autotext_positive_control() {
      vulnerable.text = '<img src="' + root.baseUrl + '/control-image">'
      wait(1000)
    }
  }
}
