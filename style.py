def apply_eve_style(app):
    app.setStyleSheet("""
    QWidget {
        background-color: rgba(16, 18, 20, 210);
        color: #D0D0D0;
        font-family: "Segoe UI";
        font-size: 10pt;
    }

    QLabel {
        color: #D0D0D0;
        background-color: transparent;
    }

    QCheckBox {
        color: #D0D0D0;
        spacing: 6px;
        background-color: transparent;
    }

    QPushButton {
        background-color: rgba(37, 42, 49, 220);
        color: #D0D0D0;
        border: 1px solid #3A4048;
        padding: 6px;
    }

    QPushButton:hover {
        background-color: rgba(48, 55, 68, 230);
        border: 1px solid #FF9900;
    }

    QPushButton:pressed {
        background-color: #FF9900;
        color: #000000;
    }

    QTableWidget {
        background-color: rgba(26, 29, 33, 210);
        color: #FFFFFF;
        gridline-color: #303744;
        border: 1px solid #3A4048;
        selection-background-color: #FF9900;
        selection-color: #000000;
    }

    QTableWidget::item {
        background-color: transparent;
        color: #FFFFFF;
    }

    QHeaderView::section {
        background-color: rgba(37, 42, 49, 230);
        color: #FF9900;
        border: 1px solid #3A4048;
        padding: 5px;
        font-weight: bold;
    }
    """)
