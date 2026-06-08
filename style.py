def apply_eve_style(app):
    app.setStyleSheet("""
    QWidget {
        background-color: transparent;
        color: #C7C9CC;
        font-family: "Segoe UI";
        font-size: 8pt;
    }

    QLabel {
        color: #C7C9CC;
        background-color: transparent;
    }

    QPushButton {
        background-color: rgba(24, 26, 30, 185);
        color: #BFC3C8;
        border: 1px solid #343840;
        padding: 1px 6px;
        min-height: 18px;
    }

    QPushButton:hover {
        background-color: rgba(42, 46, 54, 240);
        color: #FFFFFF;
        border: 1px solid #69707A;
    }

    QPushButton:pressed {
        background-color: rgba(70, 78, 92, 245);
        color: #FFFFFF;
    }

    QPushButton:checked {
        background-color: rgba(35, 60, 62, 245);
        color: #B8FFF1;
        border: 1px solid #4D8A86;
    }

    QTableWidget {
        background-color: rgba(9, 10, 12, 150);
        alternate-background-color: rgba(14, 16, 19, 110);
        color: #D0D2D5;
        gridline-color: rgba(48, 52, 58, 150);
        border: 1px solid #2D3138;
        selection-background-color: transparent;
        selection-color: #D0D2D5;
        outline: none;
    }

    QTableWidget::item {
        color: #D0D2D5;
        padding: 1px 5px;
        border: none;
    }

    QTableWidget::item:selected {
        background-color: transparent;
        color: #D0D2D5;
    }

    QHeaderView::section {
        background-color: rgba(18, 20, 24, 195);
        color: #AEB4BC;
        border-top: 1px solid #3F444C;
        border-left: 1px solid #3F444C;
        border-right: 1px solid #17191D;
        border-bottom: 1px solid #17191D;
        padding: 2px 5px;
        font-size: 8pt;
        font-weight: normal;
    }

    QScrollBar:vertical {
        background: rgba(9, 10, 12, 240);
        width: 8px;
        margin: 0px;
        border: 1px solid #22262B;
    }

    QScrollBar::handle:vertical {
        background: rgba(64, 70, 78, 230);
        min-height: 18px;
    }

    QScrollBar::handle:vertical:hover {
        background: rgba(90, 98, 108, 240);
    }

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QScrollBar:horizontal {
        background: rgba(9, 10, 12, 240);
        height: 8px;
        margin: 0px;
        border: 1px solid #22262B;
    }

    QScrollBar::handle:horizontal {
        background: rgba(64, 70, 78, 230);
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
