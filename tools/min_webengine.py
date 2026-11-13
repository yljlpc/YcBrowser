"""最小 QtWebEngine 加载用例：不涉及项目代码，用于判定环境能力。"""
import sys

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import QApplication

app = QApplication(sys.argv)
v = QWebEngineView()
v.resize(800, 600)
v.show()

R = {}


def done(ok):
    R["ok"] = ok
    v.page().runJavaScript("document.title", 0, lambda x: (R.update(title=x), app.quit()))


v.loadFinished.connect(done)
QTimer.singleShot(20000, app.quit)
v.load(QUrl("data:text/html,<html><head><title>MIN</title></head><body>min</body></html>"))
app.exec()
print("MINIMAL RESULT:", R)
sys.exit(0 if R.get("title") == "MIN" else 1)