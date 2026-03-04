"""
ui.py – Fenêtre overlay PyQt6 : sans bordures, semi-transparente, always-on-top.

Design
------
* Fond sombre arrondi avec légère transparence.
* Barre de titre avec boutons Fermer (✕) et Effacer (🗑).
* Zone de texte défilante pour les réponses Gemini.
* Indicateur de statut en bas (connexion, live, erreur).
* Déplaçable par glisser-déposer sur la barre de titre ou n'importe où.

Thread safety
-------------
La classe ``TextBridge`` utilise un signal Qt pour transmettre le texte
depuis la boucle asyncio vers le thread principal Qt.
Émettre un signal Qt est toujours thread-safe.
"""

import sys

from PyQt6.QtCore import QPoint, Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config import FONT_SIZE, WINDOW_HEIGHT, WINDOW_OPACITY, WINDOW_WIDTH


# ---------------------------------------------------------------------------
# Bridge asyncio → Qt
# ---------------------------------------------------------------------------


class TextBridge(QObject):
    """
    Pont entre la boucle asyncio et le thread principal Qt.

    Utilisé ainsi dans la boucle asyncio::

        bridge.text_received.emit(texte)  # thread-safe

    Et connecté dans l'UI::

        bridge.text_received.connect(window.append_text)
    """

    text_received = pyqtSignal(str)
    status_changed = pyqtSignal(str)


# ---------------------------------------------------------------------------
# Fenêtre overlay
# ---------------------------------------------------------------------------


class OverlayWindow(QWidget):
    """
    Fenêtre principale de l'assistant :
    - Sans bordures (FramelessWindowHint)
    - Toujours au premier plan (WindowStaysOnTopHint)
    - Fond semi-transparent
    - Déplaçable à la souris
    """

    def __init__(self, bridge: TextBridge) -> None:
        super().__init__()
        self._bridge = bridge
        self._drag_pos: QPoint = QPoint()
        self._full_text: str = ""  # historique complet des réponses
        self._init_window_flags()
        self._build_ui()
        # Connexions signal→slot (thread-safe)
        bridge.text_received.connect(self._on_text_received)
        bridge.status_changed.connect(self._on_status_changed)

    # ------------------------------------------------------------------
    # Initialisation de la fenêtre
    # ------------------------------------------------------------------

    def _init_window_flags(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            # Tool masque la fenêtre de la barre des tâches
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowOpacity(WINDOW_OPACITY)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowTitle("Interview Assistant")

    def _build_ui(self) -> None:
        """Construit le layout complet de la fenêtre."""
        # Conteneur principal (fond sombre arrondi)
        container = QWidget(self)
        container.setObjectName("container")
        container.setStyleSheet(
            "#container {"
            "  background-color: rgba(18, 18, 28, 225);"
            "  border-radius: 14px;"
            "  border: 1px solid rgba(255, 255, 255, 0.12);"
            "}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        main = QVBoxLayout(container)
        main.setContentsMargins(14, 10, 14, 10)
        main.setSpacing(8)

        main.addLayout(self._build_title_bar())
        main.addWidget(self._build_scroll_area())
        main.addWidget(self._build_status_bar())

    def _build_title_bar(self) -> QHBoxLayout:
        """Barre de titre draggable avec boutons de contrôle."""
        layout = QHBoxLayout()
        layout.setSpacing(6)

        title = QLabel("🎙 Interview Assistant")
        title.setStyleSheet(
            "color: rgba(190, 200, 255, 0.9);"
            "font-weight: bold;"
            "font-size: 11px;"
            "background: transparent;"
        )

        # Bouton "Effacer le texte"
        clear_btn = QPushButton("🗑")
        clear_btn.setFixedSize(22, 22)
        clear_btn.setToolTip("Effacer le texte")
        clear_btn.setStyleSheet(self._btn_style("rgba(80, 100, 255, 0.75)"))
        clear_btn.clicked.connect(self._clear_text)

        # Bouton "Fermer"
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setToolTip("Fermer")
        close_btn.setStyleSheet(self._btn_style("rgba(220, 60, 60, 0.80)"))
        close_btn.clicked.connect(QApplication.instance().quit)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(clear_btn)
        layout.addWidget(close_btn)
        return layout

    def _build_scroll_area(self) -> QScrollArea:
        """Zone de texte défilante pour les réponses Gemini."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical {"
            "  width: 6px; background: transparent; margin: 2px 0;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: rgba(255,255,255,0.25); border-radius: 3px;"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "  height: 0px;"
            "}"
        )

        self._text_label = QLabel("")
        self._text_label.setWordWrap(True)
        self._text_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self._text_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._text_label.setStyleSheet(
            "color: rgba(225, 230, 255, 0.95); background: transparent;"
        )
        if sys.platform == "win32":
            font = QFont("Segoe UI", FONT_SIZE)
        elif sys.platform == "darwin":
            font = QFont("SF Pro Text", FONT_SIZE)
        else:
            font = QFont("Ubuntu", FONT_SIZE)
        self._text_label.setFont(font)

        scroll.setWidget(self._text_label)
        self._scroll_area = scroll
        return scroll

    def _build_status_bar(self) -> QLabel:
        self._status_label = QLabel("⏳ Connexion en cours…")
        self._status_label.setStyleSheet(
            "color: rgba(160, 170, 190, 0.75);"
            "font-size: 10px;"
            "background: transparent;"
        )
        return self._status_label

    # ------------------------------------------------------------------
    # Helpers styles
    # ------------------------------------------------------------------

    @staticmethod
    def _btn_style(base_color: str) -> str:
        return (
            f"QPushButton {{"
            f"  background: {base_color}; color: white;"
            f"  border-radius: 11px; font-size: 10px; border: none;"
            f"}}"
            f"QPushButton:hover {{ background: {base_color.replace('0.7', '1.0').replace('0.75', '1.0').replace('0.80', '1.0')}; }}"
        )

    # ------------------------------------------------------------------
    # Slots Qt
    # ------------------------------------------------------------------

    def _on_text_received(self, text: str) -> None:
        """Ajoute le texte reçu de Gemini à l'affichage."""
        self._full_text += text
        self._text_label.setText(self._full_text)
        # Scroll automatique vers le bas
        vsb = self._scroll_area.verticalScrollBar()
        vsb.setValue(vsb.maximum())
        self._status_label.setText("🟢 Live")

    def _on_status_changed(self, msg: str) -> None:
        self._status_label.setText(msg)

    def _clear_text(self) -> None:
        self._full_text = ""
        self._text_label.setText("")

    # ------------------------------------------------------------------
    # Déplacement de la fenêtre à la souris
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
