def apply_eve_style(app):
    app.setStyleSheet("""
    QWidget {
        background-color: #101214;
        color: #D0D0D0;
        font-family: "Segoe UI";
        font-size: 10pt;
    }

    QLabel {
        color: #D0D0D0;
    }

    QCheckBox {
        color: #D0D0D0;
        spacing: 6px;
    }

    QPushButton {
        background-color: #252A31;
        color: #D0D0D0;
        border: 1px solid #3A4048;
        padding: 6px;
    }

    QPushButton:hover {
        background-color: #303744;
        border: 1px solid #FF9900;
    }

    QPushButton:pressed {
        background-color: #FF9900;
        color: #000000;
    }

    QTableWidget {
        background-color: #1A1D21;
        color: #D0D0D0;
        gridline-color: #303744;
        border: 1px solid #3A4048;
        selection-background-color: #FF9900;
        selection-color: #000000;
    }

    QHeaderView::section {
        background-color: #252A31;
        color: #FF9900;
        border: 1px solid #3A4048;
        padding: 5px;
        font-weight: bold;
    }
    """)

