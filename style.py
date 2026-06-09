def apply_eve_style(app):
    app.setStyleSheet("""
    QWidget {
        color: #d6d6d6;
        font-family: "Segoe UI";
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
    """)
