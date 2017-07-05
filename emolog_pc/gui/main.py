import sys
from PyQt5.QtCore import QUrl
from PyQt5.QtWidgets import QApplication
from PyQt5.QtQuick import QQuickView
from PyQt5.QtQml import QQmlApplicationEngine


# Main Function
if __name__ == '__main__':
    # Create main app
    app = QApplication(sys.argv)
    engine = QQmlApplicationEngine()
    engine.load(QUrl('gui.qml'))

    window = engine.rootObjects()[0]
    window.show()

    # Execute the Application and Exit
    sys.exit(app.exec_())
