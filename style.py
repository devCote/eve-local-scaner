def apply_eve_style(app):
    app.setStyleSheet("""
    QWidget {
        background-color: rgba(18, 20, 24, 235);
        color: #C8CCD2;
        font-family: "Segoe UI";
        font-size: 8.5pt;
    }

    QLabel {
        color: #C8CCD2;
        background-color: transparent;
    }

    QPushButton {
        background-color: rgba(38, 42, 48, 240);
        color: #C8CCD2;
        border: 1px solid #4A4E55;
        padding: 2px 8px;
        min-height: 20px;
    }

    QPushButton:hover {
        background-color: rgba(58, 62, 70, 245);
        border: 1px solid #8E939B;
    }

    QPushButton:pressed {
        background-color: rgba(80, 84, 92, 255);
        color: #FFFFFF;
    }

    QPushButton:checked {
        background-color: rgba(65, 70, 80, 255);
        color: #FFFFFF;
        border: 1px solid #9AA1AA;
    }

    QTableWidget {
        background-color: rgba(20, 22, 27, 245);
        color: #D6D9DE;
        gridline-color: rgba(70, 75, 82, 170);
        border: 1px solid #4A4E55;
        selection-background-color: rgba(70, 90, 130, 200);
        selection-color: #FFFFFF;
        outline: none;
    }

    QTableWidget::item {
        color: #D6D9DE;
        padding: 2px 6px;
        border: none;
    }

    QTableWidget::item:selected {
        background-color: rgba(70, 90, 130, 200);
        color: #FFFFFF;
    }

    QHeaderView::section {
        background-color: rgba(28, 30, 36, 250);
        color: #F2F2F2;
        border-top: 1px solid #585D66;
        border-left: 1px solid #585D66;
        border-right: 1px solid #2A2D33;
        border-bottom: 1px solid #2A2D33;
        padding: 3px 6px;
        font-weight: normal;
    }

    QScrollBar:vertical {
        background: rgba(24, 26, 30, 220);
        width: 10px;
        margin: 0;
        border: 1px solid #3E434B;
    }

    QScrollBar::handle:vertical {
        background: rgba(78, 84, 94, 230);
        min-height: 20px;
    }

    QScrollBar::handle:vertical:hover {
        background: rgba(100, 108, 120, 240);
    }

    QScrollBar::add-line:vertical,
    QScrollBar::sub-line:vertical {
        height: 0px;
    }

    QScrollBar:horizontal {
        background: rgba(24, 26, 30, 220);
        height: 10px;
        margin: 0;
        border: 1px solid #3E434B;
    }

    QScrollBar::handle:horizontal {
        background: rgba(78, 84, 94, 230);
        min-width: 20px;
    }

    QScrollBar::handle:horizontal:hover {
        background: rgba(100, 108, 120, 240);
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
