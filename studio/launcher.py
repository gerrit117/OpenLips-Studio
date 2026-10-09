"""Desktop and explicit headless entry points, including frozen Windows builds."""
import sys


def main():
    mode = next((flag for flag in ('--server', '--server-job', '--server-init', '--ai-worker')
                 if flag in sys.argv), None)
    if mode:
        sys.argv.remove(mode)
    if mode == '--server':
        from studio.server import main as entry
    elif mode == '--server-job':
        from studio.server_job import main as entry
    elif mode == '--server-init':
        from studio.server_config import main as entry
    elif mode == '--ai-worker':
        from tools.create_ai_chart import main as entry
    else:
        from studio.app import main as entry
    if mode in ('--server', '--server-job', '--server-init') and getattr(sys, 'frozen', False):
        # A windowed PyInstaller executable has no standard streams. Headless
        # failures must go to a local log, not a bootloader error dialog.
        from contextlib import redirect_stdout, redirect_stderr
        from pathlib import Path
        import traceback
        option = '--library' if mode == '--server-job' else '--config'
        try:
            value = Path(sys.argv[sys.argv.index(option) + 1]).resolve()
            folder = value if option == '--library' else value.parent
            folder.mkdir(parents=True, exist_ok=True)
            with (folder / 'headless.log').open('a', encoding='utf-8', buffering=1) as log:
                with redirect_stdout(log), redirect_stderr(log):
                    try:
                        return entry()
                    except Exception:
                        traceback.print_exc()
                        return 1
        except (OSError, ValueError, IndexError):
            return 1
    return entry()


if __name__ == '__main__':
    raise SystemExit(main())
