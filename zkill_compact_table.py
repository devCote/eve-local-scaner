"""Compact PyQt table for displaying kills/losses with ship icons."""

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtWidgets import (
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QVBoxLayout,
    QLabel,
    QAbstractItemView,
)

from zkill_table_model import get_ship_icon_url

ICON_SIZE = 24


class ShipIconWidget(QWidget):
    """Widget to display ship icon in table cell."""
    
    def __init__(self, ship_type_id: int, ship_name: str, parent=None):
        super().__init__(parent)
        self.ship_type_id = ship_type_id
        self.ship_name = ship_name
        
        layout = QVBoxLayout()
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        
        # Try to load ship icon
        icon_url = get_ship_icon_url(ship_type_id)
        try:
            # For now, use placeholder or cached icon
            # TODO: Download and cache ship icons from EVE image server
            icon_label = QLabel("🛸")  # Placeholder emoji
            icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        except Exception:
            icon_label = QLabel("?")
            icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        
        layout.addWidget(icon_label)
        
        self.setLayout(layout)
        self.setFixedHeight(ICON_SIZE + 4)


class KillsLossesTable(QTableWidget):
    """Compact table showing kills or losses with ship icons."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Setup table
        self.setColumnCount(4)
        self.setHorizontalHeaderLabels(["Date", "Ship", "Location", "Opponent"])
        
        self.horizontalHeader().setStretchLastSection(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(True)
        
        self.setStyleSheet("""
            QTableWidget {
                gridline-color: #2a2d31;
                background-color: #0a0b0d;
                alternate-background-color: #0f1113;
            }
            QTableWidget::item {
                padding: 2px;
                color: #b5bac1;
            }
            QHeaderView::section {
                background-color: #1e1f22;
                color: #b5bac1;
                padding: 4px;
                border: none;
            }
        """)
    
    def load_data(self, data_rows: list):
        """
        Load data into table.
        
        Args:
            data_rows: List of dicts with keys:
                - date: str (YYYY-MM-DD HH:MM)
                - ship_name: str
                - ship_type_id: int
                - location: str
                - opponent: str
        """
        self.setRowCount(len(data_rows))
        
        for row_idx, row_data in enumerate(data_rows):
            date_item = QTableWidgetItem(row_data.get("date", ""))
            date_item.setFlags(date_item.flags() & ~Qt.ItemIsEditable)
            self.setItem(row_idx, 0, date_item)
            
            ship_name = row_data.get("ship_name", "Unknown")
            ship_type_id = row_data.get("ship_type_id", 0)
            
            # Ship with icon
            ship_item = QTableWidgetItem(f"  {ship_name}")
            ship_item.setFlags(ship_item.flags() & ~Qt.ItemIsEditable)
            self.setItem(row_idx, 1, ship_item)
            
            location = row_data.get("location", "")
            location_item = QTableWidgetItem(location)
            location_item.setFlags(location_item.flags() & ~Qt.ItemIsEditable)
            self.setItem(row_idx, 2, location_item)
            
            opponent = row_data.get("opponent", "Unknown")
            opponent_item = QTableWidgetItem(opponent)
            opponent_item.setFlags(opponent_item.flags() & ~Qt.ItemIsEditable)
            self.setItem(row_idx, 3, opponent_item)
        
        # Auto-resize columns
        self.resizeColumnsToContents()
    
    def clear_data(self):
        """Clear all rows from table."""
        self.setRowCount(0)
