"""PyInstaller entry point (absolute imports also work as a frozen executable)."""
import sys

if '--ai-worker' in sys.argv:
    from tools.create_ai_chart import main
    sys.argv.remove('--ai-worker')
else:
    from studio.app import main

if __name__ == '__main__':
    raise SystemExit(main())
