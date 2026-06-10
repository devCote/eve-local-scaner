"""Example: How to use compact zkill viewer from main application.

When a user clicks on a character in the local intel panel,
you can open the compact viewer instead of loading the browser.
"""

from zkill_panel import ZkillPanel

class MainWindow:
    def __init__(self):
        self.zkill_panel = ZkillPanel()
    
    def on_character_clicked(self, character_id: int, character_name: str):
        """Called when user clicks on a character in the table."""
        # Option 1: Open in compact mode (NO browser)
        self.zkill_panel.open_character_in_compact(character_id, character_name)
        
        # Option 2: Open in browser mode (old way)
        # url = f"https://zkillboard.com/character/{character_id}/"
        # self.zkill_panel.load_url(url)


# Usage example:
if __name__ == "__main__":
    window = MainWindow()
    
    # Simulate user clicking on a character
    window.on_character_clicked(92845175, "Test Pilot")
    
    print("✅ Character opened in compact viewer!")
    print("Features:")
    print("  - Shows kills/losses in compact table")
    print("  - No QtWebEngine browser loaded")
    print("  - Fast API-based data loading")
    print("  - Ship names and locations from ESI")
