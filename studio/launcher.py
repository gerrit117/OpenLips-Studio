"""PyInstaller entry point (absolute imports also work as a frozen executable)."""
from studio.app import main

if __name__ == '__main__':
    raise SystemExit(main())
