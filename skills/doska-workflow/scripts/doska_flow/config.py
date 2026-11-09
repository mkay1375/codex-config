"""Machine-local configuration; no global configuration is written implicitly."""
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
from .model import FlowError

def codex_home():
    return Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser()

def local_settings_path():
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/com.deck.desktop/local-mcp.json'
    if sys.platform == 'win32':
        return Path(os.environ.get('APPDATA', str(Path.home() / 'AppData/Roaming'))) / 'com.deck.desktop/local-mcp.json'
    return Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'com.deck.desktop/local-mcp.json'

@dataclass(frozen=True)
class Config:
    mode: str
    workspace: str
    endpoint: str = ''
    token_env: str = ''
    token_file: str = ''
    settings_file: str = ''
    web_url: str = ''
    project_key: str = ''
    sync_verified: bool = False
    timeout: float = 3

    def __post_init__(self):
        if self.mode not in ('local', 'remote'):
            raise FlowError('Configure mode as local or remote')
        if not self.workspace or any(c.isspace() for c in self.workspace):
            raise FlowError('Set a stable, nonempty workspace identifier')
        if not 0 < self.timeout <= 10:
            raise FlowError('Timeout must be greater than zero and at most ten seconds')
        if self.mode == 'remote' and not self.endpoint:
            raise FlowError('Remote tracking needs an explicit HTTPS MCP endpoint')
        if self.endpoint:
            self.validate_url(self.endpoint)
        if self.web_url:
            u=urlsplit(self.web_url)
            if u.scheme!='https' or not u.hostname or u.username or u.password or u.query or u.fragment:
                raise FlowError('web_url must be HTTPS without credentials, query strings, or fragments')
            try:u.port
            except ValueError:raise FlowError('Invalid web_url port') from None

    def validate_url(self, value):
        u = urlsplit(value)
        if u.username or u.password or u.fragment or u.query:
            raise FlowError('Endpoint must not contain credentials, query strings, or fragments')
        if self.mode == 'local':
            if u.scheme != 'http' or u.hostname != '127.0.0.1':
                raise FlowError('Local MCP must use http://127.0.0.1')
        elif u.scheme != 'https' or not u.hostname:
            raise FlowError('Remote MCP must use HTTPS')
        try:
            u.port
        except ValueError:
            raise FlowError('Invalid endpoint port') from None

def load_config(home=None):
    path = Path(home or codex_home()) / 'doska.local.toml'
    try:
        raw = tomllib.loads(path.read_text())
        allowed = set(Config.__dataclass_fields__)
        if set(raw) - allowed:
            raise FlowError('Unknown configuration keys: ' + ', '.join(sorted(set(raw) - allowed)))
        return Config(**raw)
    except (OSError, tomllib.TOMLDecodeError, TypeError, ValueError):
        raise FlowError('Doska is not configured correctly; run setup/doctor or explicitly continue without it') from None
