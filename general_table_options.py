"""Dialog for General table column visibility."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout

COLUMN_LABELS = {
    "3": "Danger",
    "4": "Gang",
    "5": "Corp/Ally",
    "6": "Last Ships",
}


def show_general_table_options_dialog(
    parent,
    current_visible: dict[str, bool],
    *,
    font_size: int,
    text_color: str,
    frame_color: str,
) -> dict[str, bool] | None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("General Table")
    dialog.setModal(True)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)

    title = QLabel("Show columns:")
    layout.addWidget(title)

    checks = {key: QCheckBox(label) for key, label in COLUMN_LABELS.items()}
    for key in COLUMN_LABELS:
        checks[key].setChecked(bool(current_visible.get(key, True)))
        layout.addWidget(checks[key])

    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    layout.addWidget(buttons)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)

    dialog.setStyleSheet(f"""
        QDialog {{
            background-color: rgba(11, 11, 11, 235);
            color: {text_color};
            border: 1px solid {frame_color};
        }}
        QLabel, QCheckBox {{
            color: {text_color};
            font-size: {font_size}pt;
        }}
        QPushButton {{
            background-color: rgba(20, 24, 26, 210);
            color: {text_color};
            border: 1px solid {frame_color};
            padding: 3px 10px;
        }}
        QPushButton:hover {{
            color: #9ffff2;
            border-color: #39c7b5;
        }}
    """)

    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None

    return {key: checks[key].isChecked() for key in COLUMN_LABELS}
