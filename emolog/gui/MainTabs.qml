import QtQuick 2.6
import QtQuick.Controls 1.2
import Qt.labs.controls 1.0

TabView {
    Component.onCompleted: {
        addTab("Main", main_tab)
        addTab("Settings", settings_tab)
    }

    Component {
        id: main_tab
        Rectangle {color: "red"}
    }

    Component {
        id: settings_tab
        Rectangle {color: "blue"}
    }
}
