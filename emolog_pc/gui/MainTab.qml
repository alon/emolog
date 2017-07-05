import QtQuick 2.0

Item
{
    Column {
        id: column1
        x: 0
        y: 0
        width: 640
        height: 480
    }

    Text {
        id: start
        x: 37
        y: 41
        width: 57
        height: 39
        text: qsTr("START")
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        color: "red"
        font.pixelSize: 20
    }

}
