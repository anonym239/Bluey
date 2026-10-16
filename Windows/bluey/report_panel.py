"""Die Recherchekarte. Sie erscheint, während er recherchiert, und zeigt dann die ersten Zeilen.
Klick drauf zum Aufklappen; sie bleibt, bis du auf Minus drückst. Oben rechts auf dem Hauptbildschirm."""
import sys

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from .palette import BERRY2, INK, color

SOFT = "#5D5873"


class ReportPanel(QWidget):
    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Bluey-Recherche")
        self.question, self.report, self.error, self.expanded = "", None, None, False
        self._drag = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 20)
        outer.setSpacing(10)
        head = QHBoxLayout()
        self.icon = QLabel("🔍")
        self.icon.setStyleSheet(f"color: #{BERRY2:06x}; font-size: 15px;")
        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setStyleSheet(f"color: #{INK:06x}; font-family: Fredoka; font-size: 20px; font-weight: 600;")
        self.collapse = self._circle("⌃", self.toggle)
        self.close_button = self._circle("–", self.hide)
        head.addWidget(self.icon, 0, Qt.AlignTop)
        head.addWidget(self.title, 1)
        head.addWidget(self.collapse, 0, Qt.AlignTop)
        head.addWidget(self.close_button, 0, Qt.AlignTop)
        outer.addLayout(head)

        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self.body.setOpenExternalLinks(True)
        self.body.setStyleSheet(f"color: #{INK:06x}; font-family: 'IBM Plex Sans'; font-size: 14px;")
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setStyleSheet("background: transparent;")
        self.scroll.viewport().setStyleSheet("background: transparent;")
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)
        self.more = QLabel("Klicken für mehr")
        self.more.setStyleSheet(f"color: #{BERRY2:06x}; font-family: 'IBM Plex Mono'; font-size: 11px;")
        outer.addWidget(self.more)

    def _circle(self, text, action):
        button = QPushButton(text)
        button.setFixedSize(26, 26)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(f"QPushButton {{ background: #{BERRY2:06x}; color: white; border-radius: 13px; "
                             "font-weight: 900; font-size: 14px; border: none; }")
        button.clicked.connect(action)
        return button

    def showEvent(self, event):
        super().showEvent(event)
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), 0x11)
            except Exception:
                pass

    # Inhalt

    def show_loading(self, question):
        self.question, self.report, self.error, self.expanded = question, None, None, False
        self._render()

    def show(self, report=None):
        if report is None:
            return super().show()
        self.report, self.error = report, None
        self._render()

    def show_error(self, message):
        self.error = message
        self._render()

    def toggle(self):
        if self.report:
            self.expanded = not self.expanded
            self._render()

    def _render(self):
        report = self.report
        self.collapse.setVisible(bool(report) and self.expanded)
        if report:
            self.title.setText(report.title)
            if self.expanded:
                html = "".join(f"<p style='margin-bottom:10px'>{_escape(p)}</p>" for p in report.paragraphs)
                if report.sources:
                    html += f"<p style='color:{SOFT}; font-family:\"IBM Plex Mono\"; font-size:11px'>QUELLEN</p>"
                    html += "".join(f"<p style='margin:2px'><a style='color:#{BERRY2:06x}; text-decoration:none' "
                                    f"href='{_escape(url)}'>{_escape(title)}</a></p>" for title, url in report.sources)
                self.body.setText(html)
                self.more.hide()
            else:
                text = " ".join(report.paragraphs)
                self.body.setText(_escape(text[:260] + ("…" if len(text) > 260 else "")))
                self.more.show()
            self.icon.setText("📄")
        elif self.error:
            self.title.setText("Recherche")
            self.body.setText(_escape(self.error))
            self.more.hide()
            self.icon.setText("📄")
        else:
            self.title.setText("Recherchiere")
            self.body.setText(f"<span style='color:{SOFT}'>Recherchiere zu „{_escape(self.question)}“ …</span>")
            self.more.hide()
            self.icon.setText("🔍")
        self._layout()
        super().show()
        self.raise_()

    def _layout(self):
        screen = QGuiApplication.primaryScreen().availableGeometry()
        width = 520 if self.expanded else 400
        if self.expanded and self.report:
            lines = sum(len(p) // 58 + 1 for p in self.report.paragraphs)
            content = lines * 21 + len(self.report.paragraphs) * 12 + (30 + len(self.report.sources) * 22 if self.report.sources else 0)
            height = min(int(screen.height() * 0.75), 120 + content)
        else:
            height = 150 if self.report is None else 200
        self.setGeometry(screen.right() - width - 24, screen.top() + 24, width, height)

    def mousePressEvent(self, event):
        self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        self._moved = False

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)
            self._moved = True

    def mouseReleaseEvent(self, event):
        if not getattr(self, "_moved", False) and self.report and not self.expanded:
            self.toggle()
        self._drag = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        path = QPainterPath()
        path.addRoundedRect(rect, 22, 22)
        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        gradient.setColorAt(0, QColor("white"))
        gradient.setColorAt(1, QColor("#EEF0FF"))
        p.fillPath(path, QBrush(gradient))
        p.setPen(QPen(color(BERRY2), 2.5))
        p.drawPath(path)
        p.end()


def _escape(text):
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;")
