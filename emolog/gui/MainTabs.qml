import QtQuick 2.6
import QtQuick.Controls 1.2


TabView {
    Component.onCompleted: {
        addTab("Main", main_tab)
        addTab("Settings", settings_tab)
    }

    Component {
        id: main_tab
        MainTab {}
    }

    Component {
        id: settings_tab
        SettingsTab {}
    }

}
