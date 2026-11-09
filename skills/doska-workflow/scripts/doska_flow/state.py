"""Private transactional bookkeeping. Never use this directory as a sync target."""
import json
import os
import sqlite3
import time
import uuid
import threading
from contextlib import contextmanager
from pathlib import Path
from .config import codex_home
from .model import FlowError

class State:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else codex_home() / 'doska-state'
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if os.name != 'nt': self.root.chmod(0o700)
        self.path = self.root / 'state.sqlite3'
        # Create privately before SQLite opens the database.
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        if os.name != 'nt': self.path.chmod(0o600)
        self._mutex = threading.RLock()
        self._lock_depth = 0
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS kv (namespace TEXT, key TEXT, value TEXT, PRIMARY KEY(namespace,key))')
        self.db.execute('CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, task TEXT, payload TEXT, created REAL, status TEXT)')
        self.db.commit()

    @contextmanager
    def operation_lock(self, timeout=10):
        """Serialize multi-request mutations across processes on this computer."""
        if not self._mutex.acquire(timeout=timeout):
            raise FlowError('Another local task operation is still running')
        handle = None
        try:
            if self._lock_depth == 0:
                path = self.root / 'operation.lock'
                fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
                handle = os.fdopen(fd, 'r+b')
                if handle.seek(0, 2) == 0:
                    handle.write(b'0'); handle.flush()
                deadline = time.monotonic() + timeout
                while True:
                    try:
                        handle.seek(0)
                        if os.name == 'nt':
                            import msvcrt
                            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        else:
                            import fcntl
                            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise FlowError('Another local task operation is still running') from None
                        time.sleep(0.05)
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
                if handle is not None:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            if handle is not None: handle.close()
            self._mutex.release()

    def get(self, namespace, key, default=None):
        row = self.db.execute('SELECT value FROM kv WHERE namespace=? AND key=?',(namespace,key)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, namespace, key, value):
        with self.db:
            self.db.execute('INSERT INTO kv VALUES (?,?,?) ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value', (namespace,key,json.dumps(value)))

    def delete(self, namespace, key):
        with self.db: self.db.execute('DELETE FROM kv WHERE namespace=? AND key=?',(namespace,key))

    def items(self, namespace):
        return [(key,json.loads(value)) for key,value in self.db.execute('SELECT key,value FROM kv WHERE namespace=? ORDER BY key',(namespace,))]

    def enqueue(self, task, payload, event_id=None):
        event_id = event_id or str(uuid.uuid4())
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO events VALUES (?,?,?,?,?)',(event_id,task,json.dumps(payload),time.time(),'pending'))
        return event_id

    def events(self, status='pending'):
        return [{'id':r[0],'task':r[1],'payload':json.loads(r[2]),'created':r[3],'status':r[4]} for r in self.db.execute('SELECT id,task,payload,created,status FROM events WHERE status=? ORDER BY created,id',(status,))]

    def event_status(self, event_id, status):
        with self.db: self.db.execute('UPDATE events SET status=? WHERE id=?',(status,event_id))

    def machine(self):
        key = self.get('machine', 'id')
        if not key:
            key = str(uuid.uuid4()); self.set('machine','id',key)
        return key

    def close(self): self.db.close()
