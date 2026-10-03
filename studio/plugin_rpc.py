"""Persistent plugin pipes managed outside the UI thread."""
import json
import os
from queue import Queue, Empty
import subprocess
from threading import Thread

from PySide6.QtCore import QThread, Signal


class PluginRPC(QThread):
    line = Signal(str)
    failed = Signal(str)

    def __init__(self, command, environment, parent=None):
        super().__init__(parent)
        self.command, self.environment = command, environment
        self.requests = Queue()

    def submit(self, request):
        self.requests.put(json.dumps(request, ensure_ascii=True) + '\n')

    def run(self):
        process = None
        reader = None
        try:
            process = subprocess.Popen(self.command, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                encoding='utf-8', errors='replace', env=self.environment,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                start_new_session=os.name != 'nt')
            def read():
                while line := process.stdout.readline(2 * 1024 * 1024):
                    if line.startswith('OPENLIPS_RPC:'):
                        self.line.emit(line.rstrip('\r\n'))
            reader = Thread(target=read, daemon=True)
            reader.start()
            while not self.isInterruptionRequested():
                if process.poll() is not None:
                    raise RuntimeError('Downloader stopped unexpectedly')
                try:
                    value = self.requests.get(timeout=.1)
                except Empty:
                    continue
                process.stdin.write(value)
                process.stdin.flush()
        except Exception as error:
            if not self.isInterruptionRequested():
                self.failed.emit(str(error))
        finally:
            if process:
                if process.poll() is None:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=10, check=False)
                    else:
                        import signal
                        os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                if reader:
                    reader.join(timeout=2)
                for stream in (process.stdin, process.stdout):
                    stream.close()

    def stop(self):
        self.requestInterruption()
        self.wait(15000)
