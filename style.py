from app_fonts import APP_FONT_FAMILY


def apply_eve_style(app):
    # Do not use an f-string for the whole QSS block: Qt CSS uses { } braces,
    # and Python would try to treat them as f-string expressions.
    font_family = str(APP_FONT_FAMILY or "Georgia").replace('"', "").replace("'", "")

    qss = """
    QWidget {
        color: #d6d6d6;
        font-family: "__APP_FONT_FAMILY__";
        font-size: 10pt;
    }

    QLabel {
        color: #d6d6d6;
        background-color: transparent;
    }

    QPushButton {
        background-color: rgba(24, 26, 30, 180);
        color: #d6d6d6;
        border: 1px solid #161616;
        padding: 1px 6px;
        min-height: 18px;
    }

    QTableWidget {
        background-color: transparent;
        alternate-background-color: transparent;
        color: #d6d6d6;
        gridline-color: transparent;
        border: none;
        selection-background-color: transparent;
        outline: none;
    }

    QTableWidget::item {
        color: #d6d6d6;
        padding: 1px 3px;
        border: none;
    }

    QHeaderView,
    QHeaderView::section {
        background: transparent;
        border: none;
    }

    QScrollBar:vertical {
        background: rgba(9, 10, 12, 120);
        width: 8px;
        margin: 0px;
        border: none;
    }

    QScrollBar::handle:vertical {
        background: rgba(64, 70, 78, 210);
        min-height: 18px;
    }

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QScrollBar:horizontal {
        background: rgba(9, 10, 12, 120);
        height: 8px;
        margin: 0px;
        border: none;
    }

    QScrollBar::handle:horizontal {
        background: rgba(64, 70, 78, 210);
        min-width: 18px;
    }

    QScrollBar::add-line:horizontal,
    QScrollBar::sub-line:horizontal {
        width: 0px;
    }

    QSizeGrip {
        background: transparent;
        width: 10px;
        height: 10px;
    }
    """

    app.setStyleSheet(qss.replace("__APP_FONT_FAMILY__", font_family))
