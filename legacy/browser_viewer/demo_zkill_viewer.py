#!/usr/bin/env python3
"""Demo script to test the new zkill compact viewer without browser."""

import sys
from PySide6.QtWidgets import QApplication
from zkill_viewer import ZKillViewer


def main():
    app = QApplication(sys.argv)
    
    # Create viewer
    viewer = ZKillViewer()
    
    # Demo: open a character (replace with real character ID)
    # Example: Miner for demo purposes
    demo_character_id = 92845175  # You can replace with any character ID
    viewer.open_character(demo_character_id, "Test Character")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
