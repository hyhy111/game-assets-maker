"""Module entry point for launching the PyWebView application."""

from multiprocessing import freeze_support

if __name__ == "__main__":
    # Dispatch PyInstaller's multiprocessing helpers before importing the desktop app.
    freeze_support()

    from backend.main import main

    main()
