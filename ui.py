

import sys
from pathlib import Path

from PyQt6.QtCore import QPoint, Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config import FONT_SIZE, WINDOW_HEIGHT, WINDOW_OPACITY, WINDOW_WIDTH
from settings import DEFAULT_SYSTEM_PROMPT, extract_cv_text, save_settings


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
    # Émis lorsque l'utilisateur sauvegarde de nouveaux paramètres ;
    # main.py écoute ce signal pour relancer la connexion Gemini.
    restart_requested = pyqtSignal(dict)


# ---------------------------------------------------------------------------
# Styles partagés
# ---------------------------------------------------------------------------

_DARK_DIALOG_STYLE = """
    QDialog {
        background-color: #12121c;
    }
    QLabel {
        color: #bec8ff;
        background: transparent;
    }
    QLabel#section_title {
        color: rgba(190, 200, 255, 0.9);
        font-weight: bold;
        font-size: 12px;
    }
    QLineEdit, QTextEdit {
        background-color: #1e1e32;
        color: #e1e6ff;
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 6px;
        padding: 6px;
        selection-background-color: rgba(80, 100, 255, 0.6);
    }
    QLineEdit:focus, QTextEdit:focus {
        border: 1px solid rgba(80, 100, 255, 0.8);
    }
    QPushButton {
        background: rgba(80, 100, 255, 0.75);
        color: white;
        border: none;
        border-radius: 6px;
        padding: 6px 14px;
        font-size: 12px;
    }
    QPushButton:hover {
        background: rgba(80, 100, 255, 1.0);
    }
    QPushButton:disabled {
        background: rgba(80, 100, 255, 0.3);
        color: rgba(255, 255, 255, 0.4);
    }
    QPushButton#danger_btn {
        background: rgba(220, 60, 60, 0.75);
    }
    QPushButton#danger_btn:hover {
        background: rgba(220, 60, 60, 1.0);
    }
    QPushButton#secondary_btn {
        background: rgba(60, 65, 100, 0.75);
    }
    QPushButton#secondary_btn:hover {
        background: rgba(60, 65, 100, 1.0);
    }
    QScrollBar:vertical {
        width: 6px;
        background: transparent;
        margin: 2px 0;
    }
    QScrollBar::handle:vertical {
        background: rgba(255, 255, 255, 0.25);
        border-radius: 3px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QFrame#separator {
        color: rgba(255, 255, 255, 0.12);
    }
"""


# ---------------------------------------------------------------------------
# Boîte de dialogue de configuration
# ---------------------------------------------------------------------------


class SettingsDialog(QDialog):
    """
    Dialogue de configuration de l'assistant.

    Permet à l'utilisateur de saisir :
    * Sa clé API Gemini.
    * Son CV (PDF ou TXT) pour personnaliser les réponses.
    * Un prompt système personnalisé.

    Les paramètres sont passés en entrée (``current_settings``) pour
    pré-remplir les champs et récupérés via ``get_settings()`` après
    validation.
    """

    def __init__(self, current_settings: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = dict(current_settings)
        self.setWindowTitle("⚙  Configuration – Interview Assistant")
        self.setMinimumWidth(520)
        self.setStyleSheet(_DARK_DIALOG_STYLE)
        self._build_ui()

    # ------------------------------------------------------------------
    # Construction de l'UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        layout.addWidget(self._build_api_section())
        layout.addWidget(self._make_separator())
        layout.addWidget(self._build_cv_section())
        layout.addWidget(self._make_separator())
        layout.addWidget(self._build_prompt_section())
        layout.addStretch()
        layout.addWidget(self._build_button_row())

    def _make_separator(self) -> QFrame:
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        return sep

    def _build_api_section(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("🔑  Clé API Gemini")
        title.setObjectName("section_title")
        layout.addWidget(title)

        hint = QLabel(
            "Obtenez votre clé gratuitement sur "
            "<a href='https://aistudio.google.com/app/apikey' "
            "style='color:#7090ff;'>aistudio.google.com</a>."
        )
        hint.setOpenExternalLinks(True)
        hint.setStyleSheet("color: rgba(180,190,220,0.75); font-size: 11px; background: transparent;")
        layout.addWidget(hint)

        key_row = QHBoxLayout()
        self._api_key_edit = QLineEdit()
        self._api_key_edit.setPlaceholderText("AIza…")
        self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_edit.setText(self._settings.get("api_key", ""))
        self._api_key_edit.textChanged.connect(self._update_start_button)

        toggle_btn = QPushButton("👁")
        toggle_btn.setObjectName("secondary_btn")
        toggle_btn.setFixedWidth(36)
        toggle_btn.setToolTip("Afficher / masquer la clé")
        toggle_btn.clicked.connect(self._toggle_key_visibility)

        key_row.addWidget(self._api_key_edit)
        key_row.addWidget(toggle_btn)
        layout.addLayout(key_row)

        return widget

    def _build_cv_section(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel("📄  CV / Resume  (optionnel)")
        title.setObjectName("section_title")
        layout.addWidget(title)

        hint = QLabel("Importez votre CV pour que Gemini adapte ses réponses à votre profil.")
        hint.setStyleSheet("color: rgba(180,190,220,0.75); font-size: 11px; background: transparent;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        browse_btn = QPushButton("📂  Parcourir…")
        browse_btn.clicked.connect(self._browse_cv)

        self._cv_clear_btn = QPushButton("✕  Supprimer")
        self._cv_clear_btn.setObjectName("danger_btn")
        self._cv_clear_btn.clicked.connect(self._clear_cv)
        self._cv_clear_btn.setEnabled(bool(self._settings.get("cv_path")))

        btn_row.addWidget(browse_btn)
        btn_row.addWidget(self._cv_clear_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._cv_path_label = QLabel(
            self._settings.get("cv_path") or "Aucun fichier sélectionné"
        )
        self._cv_path_label.setStyleSheet(
            "color: rgba(160,170,200,0.80); font-size: 11px; background: transparent;"
        )
        self._cv_path_label.setWordWrap(True)
        layout.addWidget(self._cv_path_label)

        # Aperçu du texte extrait (read-only, collapsible)
        self._cv_preview = QTextEdit()
        self._cv_preview.setReadOnly(True)
        self._cv_preview.setPlaceholderText("Le texte extrait de votre CV s'affichera ici…")
        self._cv_preview.setFixedHeight(90)
        self._cv_preview.setPlainText(self._settings.get("cv_text", ""))
        layout.addWidget(self._cv_preview)

        return widget

    def _build_prompt_section(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title_row = QHBoxLayout()
        title = QLabel("✏️  Prompt système")
        title.setObjectName("section_title")
        title_row.addWidget(title)
        title_row.addStretch()

        reset_btn = QPushButton("↺  Réinitialiser")
        reset_btn.setObjectName("secondary_btn")
        reset_btn.setToolTip("Rétablir le prompt par défaut")
        reset_btn.clicked.connect(self._reset_prompt)
        title_row.addWidget(reset_btn)
        layout.addLayout(title_row)

        hint = QLabel("Instructions envoyées à Gemini avant chaque session.")
        hint.setStyleSheet("color: rgba(180,190,220,0.75); font-size: 11px; background: transparent;")
        layout.addWidget(hint)

        self._prompt_edit = QTextEdit()
        self._prompt_edit.setPlainText(
            self._settings.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
        )
        self._prompt_edit.setMinimumHeight(100)
        self._prompt_edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._prompt_edit)

        return widget

    def _build_button_row(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addStretch()

        cancel_btn = QPushButton("✕  Annuler")
        cancel_btn.setObjectName("danger_btn")
        cancel_btn.clicked.connect(self.reject)

        self._start_btn = QPushButton("✓  Sauvegarder && Démarrer")
        self._start_btn.clicked.connect(self._on_accept)
        self._update_start_button()

        layout.addWidget(cancel_btn)
        layout.addWidget(self._start_btn)
        return widget

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _toggle_key_visibility(self) -> None:
        if self._api_key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
        else:
            self._api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)

    def _update_start_button(self) -> None:
        self._start_btn.setEnabled(bool(self._api_key_edit.text().strip()))

    def _browse_cv(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Sélectionner votre CV",
            str(Path.home()),
            "Documents (*.pdf *.txt);;PDF (*.pdf);;Texte (*.txt);;Tous (*.*)",
        )
        if not path:
            return
        text = extract_cv_text(path)
        self._settings["cv_path"] = path
        self._settings["cv_text"] = text
        self._cv_path_label.setText(path)
        self._cv_preview.setPlainText(text)
        self._cv_clear_btn.setEnabled(True)

    def _clear_cv(self) -> None:
        self._settings["cv_path"] = ""
        self._settings["cv_text"] = ""
        self._cv_path_label.setText("Aucun fichier sélectionné")
        self._cv_preview.setPlainText("")
        self._cv_clear_btn.setEnabled(False)

    def _reset_prompt(self) -> None:
        self._prompt_edit.setPlainText(DEFAULT_SYSTEM_PROMPT)

    def _on_accept(self) -> None:
        self._settings["api_key"] = self._api_key_edit.text().strip()
        self._settings["system_prompt"] = self._prompt_edit.toPlainText().strip()
        self.accept()

    # ------------------------------------------------------------------
    # Données résultantes
    # ------------------------------------------------------------------

    def get_settings(self) -> dict:
        """Renvoie le dictionnaire de paramètres mis à jour par l'utilisateur."""
        return dict(self._settings)


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
    - Bouton ⚙ pour ouvrir la boîte de dialogue de configuration
    """

    def __init__(self, bridge: TextBridge, settings: dict) -> None:
        super().__init__()
        self._bridge = bridge
        self._settings = dict(settings)
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

        # Bouton "Paramètres"
        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(22, 22)
        settings_btn.setToolTip("Paramètres")
        settings_btn.setStyleSheet(
            self._btn_style("rgba(60, 80, 180, 0.75)", "rgba(60, 80, 180, 1.0)")
        )
        settings_btn.clicked.connect(self._open_settings)

        # Bouton "Effacer le texte"
        clear_btn = QPushButton("🗑")
        clear_btn.setFixedSize(22, 22)
        clear_btn.setToolTip("Effacer le texte")
        clear_btn.setStyleSheet(
            self._btn_style("rgba(80, 100, 255, 0.75)", "rgba(80, 100, 255, 1.0)")
        )
        clear_btn.clicked.connect(self._clear_text)

        # Bouton "Fermer"
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setToolTip("Fermer")
        close_btn.setStyleSheet(
            self._btn_style("rgba(220, 60, 60, 0.80)", "rgba(220, 60, 60, 1.0)")
        )
        close_btn.clicked.connect(QApplication.instance().quit)

        layout.addWidget(title)
        layout.addStretch()
        layout.addWidget(settings_btn)
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
    def _btn_style(base_color: str, hover_color: str) -> str:
        return (
            f"QPushButton {{"
            f"  background: {base_color}; color: white;"
            f"  border-radius: 11px; font-size: 10px; border: none;"
            f"}}"
            f"QPushButton:hover {{ background: {hover_color}; }}"
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

    def _open_settings(self) -> None:
        """Ouvre la boîte de dialogue de configuration."""
        dialog = SettingsDialog(self._settings, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_settings = dialog.get_settings()
            self._settings = new_settings
            save_settings(new_settings)
            # Demande à main.py de relancer la connexion avec les nouveaux paramètres
            self._bridge.restart_requested.emit(new_settings)
            self._on_status_changed("⏳ Reconnexion avec les nouveaux paramètres…")
            self._clear_text()

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

