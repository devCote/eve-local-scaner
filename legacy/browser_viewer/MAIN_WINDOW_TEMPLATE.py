"""Template: How to integrate compact zkill viewer into your main application.

Copy this pattern into your main window class.
"""

from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
from PySide6.QtCore import Qt

from zkill_panel import ZkillPanel


class MainWindowTemplate:
    """Template for integrating compact zkill viewer."""
    
    def __init__(self):
        # Create zkill panel with compact viewer support
        self.zkill_panel = ZkillPanel()
        
        # Your intel table
        self.intel_table = self.create_intel_table()
        
        # Connect table interactions to viewer
        self.intel_table.itemDoubleClicked.connect(self.on_character_double_clicked)
        self.intel_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.intel_table.customContextMenuRequested.connect(self.on_table_context_menu)
    
    def create_intel_table(self) -> QTableWidget:
        """Create your intel table with characters."""
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Character", "Status", "Danger", "Location"])
        return table
    
    def add_character_to_table(self, character_id: int, character_name: str):
        """Add a character to the intel table."""
        row = self.intel_table.rowCount()
        self.intel_table.insertRow(row)
        
        # Store character ID in the row for later lookup
        self.intel_table.item(row, 0).setText(character_name)
        self.intel_table.item(row, 0).setData(Qt.UserRole, character_id)
    
    def on_character_double_clicked(self, item: QTableWidgetItem):
        """Handle double-click on character in table."""
        row = item.row()
        char_id = self.intel_table.item(row, 0).data(Qt.UserRole)
        char_name = self.intel_table.item(row, 0).text()
        
        # COMPACT MODE (New!) - No browser, fast!
        self.zkill_panel.open_character_in_compact(char_id, char_name)
    
    def on_table_context_menu(self, position):
        """Right-click context menu with multiple options."""
        from PySide6.QtWidgets import QMenu
        
        item = self.intel_table.itemAt(position)
        if not item:
            return
        
        row = item.row()
        char_id = self.intel_table.item(row, 0).data(Qt.UserRole)
        char_name = self.intel_table.item(row, 0).text()
        
        menu = QMenu()
        
        # Option 1: Compact viewer (NEW - recommended)
        action_compact = menu.addAction("📊 View in Compact Mode")
        action_compact.triggered.connect(
            lambda: self.zkill_panel.open_character_in_compact(char_id, char_name)
        )
        
        # Option 2: Browser (OLD)
        action_browser = menu.addAction("🌐 View in Browser")
        action_browser.triggered.connect(
            lambda: self.zkill_panel.load_url(
                f"https://zkillboard.com/character/{char_id}/"
            )
        )
        
        menu.addSeparator()
        
        # Option 3: Copy character name
        action_copy = menu.addAction("📋 Copy Name")
        action_copy.triggered.connect(
            lambda: self.copy_to_clipboard(char_name)
        )
        
        menu.exec_(self.intel_table.mapToGlobal(position))
    
    def copy_to_clipboard(self, text: str):
        """Copy text to clipboard."""
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
    
    def on_character_entered_local(self, character_id: int, character_name: str):
        """Called when a character enters local (from scanner)."""
        # Automatically show compact viewer for new pilots
        self.zkill_panel.open_character_in_compact(character_id, character_name)
    
    # ... rest of your main window code ...


# QUICK START CHECKLIST:
# 
# 1. ✅ Create ZkillPanel instance in __init__:
#    self.zkill_panel = ZkillPanel()
#
# 2. ✅ Connect double-click to open_character_in_compact:
#    table.itemDoubleClicked.connect(self.on_character_double_clicked)
#
# 3. ✅ Use this method in double-click handler:
#    self.zkill_panel.open_character_in_compact(char_id, char_name)
#
# 4. ✅ (Optional) Add context menu for more options
#
# 5. ✅ Done! Test by double-clicking a character


# USAGE IN YOUR CODE:
#
# # In your character scanning thread:
# def on_new_character_detected(char_id, char_name):
#     self.main_window.on_character_entered_local(char_id, char_name)
#
# # Or in your table handler:
# def on_pilot_in_local(char_id, char_name):
#     self.main_window.on_character_double_clicked(...)  # Simulates double-click
#     # Or directly:
#     self.zkill_panel.open_character_in_compact(char_id, char_name)
