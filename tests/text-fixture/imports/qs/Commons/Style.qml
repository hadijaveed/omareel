pragma Singleton
import QtQml
QtObject {
  property int cornerRadius: 4
  property int normalBorderWidth: 1
  property var font: ({family: "sans-serif", body: 14, bodySmall: 12, subtitle: 16, caption: 12})
  property var spacing: ({huge: 16, rowPaddingX: 8, xs: 4, controlHeight: 32,
    popupRowHeight: 32, dropdownWidth: 300, labelGap: 4, controlPaddingX: 8,
    md: 8, controlGap: 4, xxs: 2, hairline: 1})
  function space(value) { return value }
  function controlFill() { return "#222222" }
  function hoverFillFor() { return "#333333" }
  function hoverStateColor() { return "#eeeeee" }
}
