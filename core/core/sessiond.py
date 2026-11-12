#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sessiond —— NasDSH 的后端服务（纯标准库）。

职责：
  1. 提供 tab 管理界面与静态资源（/srv/www）
  2. 混合会话管理：
       cli = 一个 tmux 会话（直接运行 dsh-TUI），每 tab 一个项目
       web = 一个共享 dsh web 实例，项目在 dsh UI 内用 Workspace 切换
  3. Web 反代：把 /w/ 前缀剥离后转发到 127.0.0.1:<随机端口> 的 dsh web，
     包括 /api/remote.mux 的 WebSocket 升级。
     dsh web 的前端使用 <base href="./"> 与相对路径，因此前缀反代无需
     改写 HTML/JS；Cookie 的 host/port 绑定也因 Host 头原样透传而成立。
  4. CLI 会话：WebSocket → PTY → `tmux new -A -s <name>`；浏览器断开只杀
     tmux client，会话保留；dsh-TUI 退出即会话结束。

约定：
  - 会话名：[A-Za-z0-9][A-Za-z0-9._-]{0,39}
  - 工作目录：必须位于 /volume* 或 /home 下（compose 已按原路径挂载）
  - 可选访问口令：/data/.term_pin（0600），challenge-response 登录 +
    HttpOnly Cookie 会话；WebSocket 握手自动携带。
"""

import base64
import fcntl
import hashlib
import http.client
import json
import os
import pty
import re
import secrets
import select
import shutil
import signal
import socket
import struct
import subprocess
import sys
import threading
import time
import termios
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WWW_DIR = os.environ.get("NASDSH_WWW") or os.path.join(APP_DIR, "www")
DATA_DIR = os.environ.get("NASDSH_DATA", "/data")
PORT = int(os.environ.get("NASDSH_PORT", "8080"))

PIN_FILE = os.path.join(DATA_DIR, ".term_pin")
HOME_DIR = os.path.join(DATA_DIR, "home")
DSH_HOME_DIR = os.path.join(DATA_DIR, "dsh-home")
LOG_DIR = os.path.join(DATA_DIR, "logs")

DSH_BIN = os.environ.get("NASDSH_DSH_BIN") or shutil.which("dsh") or "/usr/local/bin/dsh"
DSH_TUI_BIN = (os.environ.get("NASDSH_DSH_TUI_BIN")
               or shutil.which("dsh-tui") or "/usr/local/bin/dsh-tui")
UPGRADE_BIN = os.environ.get("NASDSH_UPGRADE_BIN", "/usr/local/bin/nasdsh-update")

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
AUTHORITY_RE = re.compile(r"^[A-Za-z0-9\[][A-Za-z0-9._:\[\]-]{0,254}$")
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
WEB_START_TIMEOUT = int(os.environ.get("NASDSH_WEB_START_TIMEOUT", "90"))
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "transfer-encoding", "upgrade",
}

ALLOWED_ROOTS = []


def _load_pin():
    """访问口令：优先读 0600 私有文件，回退 TERM_PIN 环境变量（本地调试）。"""
    try:
        with open(PIN_FILE, "r", encoding="utf-8") as f:
            pin = f.read().strip()
        if pin:
            return pin
    except OSError:
        pass
    return os.environ.get("TERM_PIN", "").strip()


TERM_PIN = _load_pin()
PIN_HASH = hashlib.sha256(TERM_PIN.encode("utf-8")).hexdigest() if TERM_PIN else ""


def _resolve_roots():
    override = [p for p in os.environ.get("NASDSH_ROOTS", "").split(":") if p]
    if override:
        return override
    roots = []
    try:
        for name in os.listdir("/"):
            if re.match(r"^volume\d+$", name):
                roots.append("/" + name)
    except OSError:
        pass
    if os.path.isdir("/home"):
        roots.append("/home")
    return roots


ALLOWED_ROOTS = _resolve_roots()
REAL_ROOTS = []
for _r in ALLOWED_ROOTS:
    _real = os.path.realpath(_r)
    if _real not in REAL_ROOTS:
        REAL_ROOTS.append(_real)


def _root_re(roots):
    if not roots:
        return re.compile(r"$^")
    return re.compile(
        r"^/(" + "|".join(sorted((r.strip("/") for r in roots), reverse=True))
        + r")(/|$)")


PATH_RE_REAL = _root_re(REAL_ROOTS)


class ClientError(Exception):
    pass


def _read_version(binary, timeout=8):
    try:
        p = subprocess.run([binary, "--version"], capture_output=True, timeout=timeout)
        out = (p.stdout or p.stderr).decode("utf-8", "replace").strip()
        return out.splitlines()[0] if p.returncode == 0 and out else "unknown"
    except Exception:
        return "unknown"


def _package_version(package, binary=None):
    """读取 npm 全局包版本（避免执行可能挂起的 TUI 进程）。"""
    candidates = []
    if binary:
        real = os.path.realpath(binary)
        parts = real.split(os.sep)
        for i in range(len(parts), 0, -1):
            p = os.sep.join(parts[:i] + ["package.json"])
            if parts[i - 1] == "dsh-tui" and os.path.isfile(p):
                candidates.append(p)
                break
    candidates += [
        "/usr/local/lib/node_modules/%s/package.json" % package,
        "/usr/lib/node_modules/%s/package.json" % package,
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "unknown")
        except (OSError, ValueError):
            continue
    return "unknown"


# ----------------------------------------------------------------------------
# tmux 封装（CLI 会话）
# ----------------------------------------------------------------------------

CLI_CREATE_LOCK = threading.Lock()


def tmux(*args, timeout=10):
    try:
        p = subprocess.run(["tmux", *args], capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 1, ""


def list_tmux_sessions():
    rc, out = tmux("list-sessions", "-F",
                   "#{session_name}\t#{session_path}\t#{session_created}\t"
                   "#{session_attached}\t#{session_windows}")
    sessions = []
    if rc == 0:
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 5:
                name, path, created, attached, windows = parts[:5]
                sessions.append({
                    "name": name,
                    "path": path,
                    "created": int(created) if created.isdigit() else 0,
                    "attached": attached not in ("0", ""),
                    "windows": int(windows) if windows.isdigit() else 1,
                    "type": "cli",
                    "alive": True,
                })
    return sessions


def session_exists(name):
    return any(s["name"] == name for s in list_tmux_sessions())


def create_cli_session(name, path):
    """在 tmux 里直接拉起 dsh-TUI；找不到 TUI 时退化为普通 shell。"""
    if os.path.isfile(DSH_TUI_BIN) and os.access(DSH_TUI_BIN, os.X_OK):
        cmd = [DSH_TUI_BIN]
    else:
        cmd = ["/bin/bash", "-l"]
    # tmux server 可能由其他进程先启动、环境不同；显式带上 HOME/DSH_HOME
    cmd = ["/usr/bin/env", "HOME=%s" % HOME_DIR, "DSH_HOME=%s" % DSH_HOME_DIR] + cmd
    env = os.environ.copy()
    env.setdefault("HOME", HOME_DIR)
    env.setdefault("DSH_HOME", DSH_HOME_DIR)
    try:
        p = subprocess.run(["tmux", "new-session", "-d", "-s", name, "-c", path, *cmd],
                           capture_output=True, timeout=15, env=env)
    except subprocess.TimeoutExpired:
        raise ClientError("tmux new-session 超时")
    except FileNotFoundError:
        raise ClientError("容器内未找到 tmux")
    if p.returncode != 0:
        raise ClientError("tmux new-session 失败: %s"
                          % p.stderr.decode("utf-8", "replace").strip())


def kill_tmux_session(name):
    tmux("kill-session", "-t", name)


def capture_pane(name, lines=300):
    if not session_exists(name):
        return ""
    rc, out = tmux("capture-pane", "-p", "-e", "-S", "-%d" % lines, "-t", name,
                   timeout=5)
    return out if rc == 0 else ""


def validate_name(name):
    if not NAME_RE.match(name):
        raise ClientError("会话名只能包含字母/数字/./_/-，且以字母或数字开头")
    if name.startswith("."):
        raise ClientError("会话名不能以 . 开头")


def validate_path(path):
    if "\x00" in path:
        raise ClientError("目录路径非法")
    real = os.path.realpath(path)
    # 以 realpath 判定，防止项目目录里的符号链接指向 /etc 等容器内其他位置；
    # 白名单根的 realpath 也纳入匹配，以支持 /tmp → /private/tmp 这类别名。
    if not PATH_RE_REAL.match(real):
        raise ClientError("目录必须在 %s 下" % "、".join(ALLOWED_ROOTS))
    if not os.path.isdir(real):
        raise ClientError("目录不存在: %s" % real)
    return real


def list_dirs(path):
    path = validate_path(path)
    dirs = []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            try:
                if entry.is_dir(follow_symlinks=True) and not entry.name.startswith("."):
                    dirs.append(entry.name)
            except OSError:
                continue
    except OSError:
        pass
    return {"path": path, "dirs": dirs[:500]}


def _default_root():
    for root in ALLOWED_ROOTS:
        if os.path.isdir(root):
            return root
    return "/"


# ----------------------------------------------------------------------------
# dsh web 进程管理
# ----------------------------------------------------------------------------

WEB_NAME = "@web"
WEB_START_LOCK = threading.Lock()


class WebApp:
    """共享 dsh web 单实例。

    所有项目都在 dsh 自己的 UI 里作为 Workspace 切换，sessiond 只负责：
      - 首次打开时启动一个 dsh web 进程（cwd 为默认根目录）
      - 把 /w/ 前缀剥离后反代到 127.0.0.1:<随机端口>（含 WebSocket）
      - 进程/browser token 只存内存；容器重启后重新启动，dsh 会话仍在
        $DSH_HOME/sessions 里。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.proc = None
        self.port = 0
        self.token = ""
        self.authority = ""
        self.started_at = 0
        self.log_path = os.path.join(LOG_DIR, "web.log")
        self.cwd = os.environ.get("NASDSH_WEB_CWD", "").strip()
        if self.cwd:
            try:
                self.cwd = validate_path(self.cwd)
            except ClientError:
                self.cwd = ""
        if not self.cwd:
            self.cwd = _default_root()
        try:
            self.cwd = validate_path(self.cwd)
        except ClientError:
            self.cwd = "/"

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    @staticmethod
    def _free_port():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
        finally:
            s.close()

    def _trusted_hosts(self):
        """dsh 的 browser-trust fence 在启动时固定；尽量把本机地址都放进去，
        这样换 LAN IP/端口访问时不必重启进程。只放能通过 AUTHORITY_RE 的形式，
        避免 dsh 因 malformed authority 启动失败。"""
        hosts = []

        def add(h):
            h = (h or "").strip()
            if h and h not in hosts and AUTHORITY_RE.match(h) and "%" not in h:
                hosts.append(h)

        add(self.authority)
        for h in os.environ.get("NASDSH_TRUSTED_HOSTS", "").split(","):
            add(h)
        add("127.0.0.1")
        add("localhost")
        try:
            out = subprocess.run(["hostname", "-I"], capture_output=True,
                                 timeout=3).stdout.decode("utf-8", "replace")
            for token in out.split():
                if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", token) and token != "0.0.0.0":
                    add(token)
        except Exception:
            pass
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None,
                                           socket.AF_INET):
                add(info[4][0])
        except Exception:
            pass
        return hosts[:20]

    def _cmd(self, port):
        cmd = [DSH_BIN, "--profile", "web", "--no-open",
               "--host", "127.0.0.1", "--port", str(port)]
        for h in self._trusted_hosts():
            cmd += ["--trusted-host", h]
        if self.authority:
            cmd += ["--public-url", "http://%s/w/" % self.authority]
        return cmd

    def start(self):
        if self.running():
            return
        os.makedirs(LOG_DIR, exist_ok=True)
        os.makedirs(HOME_DIR, exist_ok=True)
        os.makedirs(DSH_HOME_DIR, exist_ok=True)
        env = os.environ.copy()
        env["HOME"] = HOME_DIR
        env["DSH_HOME"] = DSH_HOME_DIR
        env["TERM"] = "xterm-256color"
        env.pop("TERM_PIN", None)

        last_error = ""
        for _ in range(3):
            port = self._free_port()
            try:
                self.proc = subprocess.Popen(
                    self._cmd(port), cwd=self.cwd, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, start_new_session=True)
            except OSError as e:
                raise ClientError("无法启动 dsh web: %s" % e)

            deadline = time.time() + WEB_START_TIMEOUT
            url = ""
            early = []
            try:
                while time.time() < deadline:
                    if self.proc.poll() is not None:
                        break
                    ready, _, _ = select.select([self.proc.stdout], [], [], 0.5)
                    if not ready:
                        continue
                    line = self.proc.stdout.readline()
                    if not line:
                        break
                    early.append(line.rstrip("\n"))
                    m = re.search(r"dsh web:\s+(https?://\S+)", line)
                    if m:
                        url = m.group(1)
                        break
            except Exception:
                pass

            proc = self.proc
            if url:
                self.port = port
                parsed = urllib.parse.urlsplit(url)
                q = urllib.parse.parse_qs(parsed.query)
                self.token = (q.get("token") or [""])[0]
                self.started_at = int(time.time())
                self._write_log(early + ["[nasdsh] ready: %s" % url])
                threading.Thread(target=self._drain, args=(proc, []),
                                 daemon=True).start()
                if not self.token:
                    self.stop()
                    raise ClientError("dsh web 未返回启动 token")
                return

            last_error = "dsh web 启动失败（退出码 %s），详见 %s" % (
                proc.poll(), self.log_path)
            self._write_log(early)
            self.stop()
        raise ClientError(last_error or "dsh web 启动失败")

    def _write_log(self, lines):
        try:
            fd = os.open(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                for line in lines:
                    f.write(line + "\n")
        except OSError:
            pass

    def _drain(self, proc, early):
        self._write_log(early)
        try:
            for line in proc.stdout:
                self._write_log([line.rstrip("\n")])
        except Exception:
            pass

    def stop(self):
        proc = self.proc
        self.proc = None
        self.port = 0
        self.token = ""
        self.started_at = 0
        if proc is None:
            return
        try:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            pass

    def ensure_started(self, authority=None):
        with self._lock:
            if authority and not self.running():
                self.authority = authority
            if not self.running():
                with WEB_START_LOCK:
                    if not self.running():
                        self.start()

    def restart(self, authority=None):
        with self._lock:
            self.stop()
            if authority:
                self.authority = authority
        self.ensure_started(authority)

    def info(self):
        return {
            "name": WEB_NAME,
            "path": self.cwd,
            "created": self.started_at,
            "attached": False,
            "windows": 1,
            "type": "web",
            "alive": self.running(),
            "singleton": True,
            "port": self.port if self.running() else 0,
        }


WEB = WebApp()


# ----------------------------------------------------------------------------
# WebSocket（RFC6455 服务端，够用实现）
# ----------------------------------------------------------------------------

class WebSocket:
    def __init__(self, sock):
        self.sock = sock
        self._send_lock = threading.Lock()
        self.closed = False

    def recv_frame(self):
        hdr = self._read_exact(2)
        if hdr is None:
            return None, b""
        fin = hdr[0] & 0x80
        opcode = hdr[0] & 0x0F
        masked = hdr[1] & 0x80
        length = hdr[1] & 0x7F
        if length == 126:
            ext = self._read_exact(2)
            if ext is None:
                return None, b""
            length = struct.unpack(">H", ext)[0]
        elif length == 127:
            ext = self._read_exact(8)
            if ext is None:
                return None, b""
            length = struct.unpack(">Q", ext)[0]
        mask = self._read_exact(4) if masked else b"\x00\x00\x00\x00"
        if mask is None:
            return None, b""
        payload = self._read_exact(length) if length else b""
        if payload is None:
            return None, b""
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if not fin:
            while True:
                op2, p2 = self.recv_frame()
                if op2 is None:
                    return None, b""
                if op2 == 0:
                    payload += p2
                    if len(payload) > 1 << 20:
                        return None, b""
                    continue
                return op2, p2
        return opcode, payload

    def _read_exact(self, n):
        data = b""
        while len(data) < n:
            try:
                chunk = self.sock.recv(n - len(data))
            except OSError:
                return None
            if not chunk:
                return None
            data += chunk
        return data

    def send_frame(self, opcode, payload):
        if self.closed:
            return False
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([n])
        elif n < 1 << 16:
            header += bytes([126]) + struct.pack(">H", n)
        else:
            header += bytes([127]) + struct.pack(">Q", n)
        try:
            with self._send_lock:
                self.sock.sendall(header + payload)
            return True
        except OSError:
            self.closed = True
            return False

    def send_text(self, text):
        return self.send_frame(0x1, text.encode("utf-8"))

    def send_binary(self, data):
        return self.send_frame(0x2, data)

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.send_frame(0x8, b"")
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass


# ----------------------------------------------------------------------------
# CLI PTY 会话桥
# ----------------------------------------------------------------------------

class PtyBridge(threading.Thread):
    """一个 WS 连接 ↔ 一个 tmux client PTY"""

    def __init__(self, ws, name, path):
        super().__init__(daemon=True)
        self.ws = ws
        self.name = name
        self.path = path
        self.master_fd = None
        self.pid = None

    def spawn(self, cols, rows):
        pid, fd = pty.fork()
        if pid == 0:
            try:
                os.environ["TERM"] = "xterm-256color"
                os.environ["COLORTERM"] = "truecolor"
                os.chdir(self.path)
                os.execvp("tmux", ["tmux", "new-session", "-A", "-s",
                                   self.name, "-c", self.path])
            except Exception:
                os._exit(127)
        self.pid, self.master_fd = pid, fd
        self.set_size(cols, rows)

    def set_size(self, cols, rows):
        if self.master_fd is None:
            return
        try:
            winsize = struct.pack("HHHH", max(rows, 2), max(cols, 2), 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def run(self):
        stop = threading.Event()

        def pump_output():
            while not stop.is_set():
                try:
                    r, _, _ = select.select([self.master_fd], [], [], 0.5)
                except OSError:
                    break
                if self.master_fd not in r:
                    continue
                try:
                    data = os.read(self.master_fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                if not self.ws.send_binary(data):
                    break
            stop.set()
            try:
                self.ws.close()
            except Exception:
                pass

        out_thread = threading.Thread(target=pump_output, daemon=True)
        out_thread.start()

        try:
            while not stop.is_set():
                opcode, payload = self.ws.recv_frame()
                if opcode is None or opcode == 0x8:
                    break
                if opcode == 0x9:
                    self.ws.send_frame(0xA, payload)
                    continue
                if opcode == 0x1:
                    text = payload.decode("utf-8", "replace")
                    if text.startswith('{"resize"'):
                        try:
                            msg = json.loads(text)
                            self.set_size(msg["resize"][0], msg["resize"][1])
                        except (ValueError, KeyError, TypeError):
                            pass
                    continue
                if opcode != 0x2:
                    continue
                try:
                    os.write(self.master_fd, payload)
                except OSError:
                    break
        except Exception:
            pass
        finally:
            stop.set()
            try:
                self.ws.close()
            except Exception:
                pass
            if self.master_fd is not None:
                try:
                    os.close(self.master_fd)
                except OSError:
                    pass
            if self.pid:
                try:
                    os.kill(self.pid, signal.SIGHUP)
                except OSError:
                    pass
                try:
                    os.waitpid(self.pid, os.WNOHANG)
                except OSError:
                    pass
            out_thread.join(timeout=2)


# ----------------------------------------------------------------------------
# 访问口令鉴权
# ----------------------------------------------------------------------------

AUTH_COOKIE = "nasdsh_pin"
TOKEN_TTL = 30 * 24 * 3600
CHALLENGE_TTL = 60
_auth_lock = threading.Lock()
_tokens = {}
_challenges = {}


def _prune_locked(now):
    for d in (_tokens, _challenges):
        for k in [k for k, exp in d.items() if exp < now]:
            d.pop(k, None)


def hash_pin(raw):
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def issue_challenge():
    now = time.time()
    nonce = secrets.token_hex(16)
    with _auth_lock:
        _prune_locked(now)
        _challenges[nonce] = now + CHALLENGE_TTL
    return nonce


def login(resp_hash, nonce):
    if not TERM_PIN:
        return None
    with _auth_lock:
        exp = _challenges.pop(nonce if isinstance(nonce, str) else "", 0)
    if not exp or exp < time.time():
        time.sleep(0.6)
        return None
    expect = hashlib.sha256((nonce + PIN_HASH).encode("utf-8")).hexdigest()
    if not secrets.compare_digest(str(resp_hash).lower(), expect):
        time.sleep(0.6)
        return None
    token = secrets.token_hex(32)
    with _auth_lock:
        _prune_locked(time.time())
        _tokens[token] = time.time() + TOKEN_TTL
    return token


def token_valid(token):
    if not token:
        return False
    with _auth_lock:
        exp = _tokens.get(token, 0)
        if exp and exp >= time.time():
            return True
        _tokens.pop(token, None)
    return False


# ----------------------------------------------------------------------------
# HTTP 服务
# ----------------------------------------------------------------------------

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".woff2": "font/woff2",
    ".md": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "nasdsh/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # -- 工具 --

    def check_pin(self):
        if not TERM_PIN:
            return True
        header_pin = self.headers.get("X-OC-PIN", "")
        if header_pin:
            return secrets.compare_digest(hash_pin(header_pin), PIN_HASH)
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == AUTH_COOKIE:
                return token_valid(v)
        return False

    def send_json(self, obj, code=200, headers=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_html(self, html, code=200):
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def redirect(self, location):
        self.send_response(302)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def send_file(self, rel):
        root = os.path.realpath(WWW_DIR)
        path = os.path.realpath(os.path.join(root, rel))
        if not (path == root or path.startswith(root + os.sep)):
            self.send_json({"error": "forbidden"}, 403)
            return
        if not os.path.isfile(path):
            self.send_json({"error": "not found"}, 404)
            return
        ctype = CONTENT_TYPES.get(os.path.splitext(path)[1], "application/octet-stream")
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

    def read_body_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 1 << 20:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise ClientError("请求体不是合法 JSON")

    def _authority(self):
        host = (self.headers.get("Host") or "").strip()
        if host and AUTHORITY_RE.match(host):
            return host
        return "127.0.0.1:%d" % PORT

    # -- 路由 --

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, query = parsed.path, urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/health":
                self.send_json({"ok": True, "ts": int(time.time())})
            elif path == "/api/pin-challenge":
                if not TERM_PIN:
                    self.send_json({"error": "未启用访问口令"}, 404)
                    return
                self.send_json({"nonce": issue_challenge()})
            elif path == "/api/info":
                self.send_json({
                    "pinRequired": bool(TERM_PIN),
                    "valid": self.check_pin() if TERM_PIN else None,
                    "dshVersion": _read_version(DSH_BIN),
                    "tuiVersion": _package_version(
                        "@deepseek-harness-tui/dsh-tui", DSH_TUI_BIN),
                    "dataDir": DATA_DIR,
                    "upgradeAvailable": os.path.isfile(UPGRADE_BIN),
                    "webAlive": WEB.running(),
                    "webCwd": WEB.cwd,
                })
            elif path == "/api/sessions":
                if not self.check_pin():
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                self.send_json({"sessions": self._all_sessions()})
            elif path == "/api/browse":
                if not self.check_pin():
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                target = (query.get("path") or [""])[0] or _default_root()
                self.send_json(list_dirs(target))
            elif path == "/api/web/launch":
                self._web_launch()
            elif path == "/api/web/status":
                if not self.check_pin():
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                self.send_json(WEB.info())
            elif path == "/w":
                self.redirect("/w/")
            elif path.startswith("/w/"):
                self._web_proxy(path, parsed.query)
            elif path == "/ws/" or path.startswith("/ws/"):
                if not self.check_pin():
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                self._cli_ws(path[len("/ws/"):], query)
            elif path in ("/", "/index.html"):
                self.send_file("index.html")
            elif path == "/term.html":
                self.send_file("term.html")
            elif path == "/privacy.md":
                self.send_file("docs/privacy.md")
            elif path == "/terms.md":
                self.send_file("docs/terms.md")
            elif path == "/license.txt":
                self.send_file("docs/license.txt")
            elif path.startswith("/vendor/") or path.startswith("/app/"):
                self.send_file(path.lstrip("/"))
            else:
                self.send_json({"error": "not found"}, 404)
        except ClientError as e:
            try:
                self.send_json({"error": str(e)}, 400)
            except OSError:
                pass
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/pin-login":
                if not TERM_PIN:
                    self.send_json({"error": "未启用访问口令"}, 404)
                    return
                body = self.read_body_json()
                token = login(body.get("response", ""), body.get("nonce", ""))
                if not token:
                    self.send_json({"error": "口令不对，再试试"}, 401)
                    return
                cookie = ("%s=%s; Path=/; HttpOnly; SameSite=Strict; Max-Age=%d"
                          % (AUTH_COOKIE, token, TOKEN_TTL))
                self.send_json({"ok": True}, headers={"Set-Cookie": cookie})
            elif parsed.path == "/api/sessions":
                if not self.check_pin():
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                body = self.read_body_json()
                name = str(body.get("name", "")).strip()
                path = str(body.get("path", "")).strip()
                kind = str(body.get("type", "cli")).strip().lower()
                if kind not in ("web", "cli"):
                    raise ClientError("type 只能是 web 或 cli")
                if kind == "web":
                    # 共享 Web 实例：直接打开 /api/web/launch，不需要创建会话
                    raise ClientError("Web 为共享实例，直接打开即可（项目在 dsh UI 内切 Workspace）")
                validate_name(name)
                path = validate_path(path)
                with CLI_CREATE_LOCK:
                    if session_exists(name):
                        raise ClientError("会话已存在: %s" % name)
                    create_cli_session(name, path)
                self.send_json({"ok": True, "name": name, "path": path,
                                "type": "cli"})
            elif parsed.path == "/api/web/stop":
                if not self.check_pin():
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                WEB.stop()
                self.send_json({"ok": True})
            elif parsed.path == "/api/web/restart":
                if not self.check_pin():
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                try:
                    WEB.restart(self._authority())
                except ClientError as e:
                    self.send_json({"error": str(e)}, 502)
                    return
                self.send_json({"ok": True})
            elif parsed.path == "/api/upgrade-dsh":
                if not self.check_pin():
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                self._upgrade()
            elif parsed.path == "/w" or parsed.path.startswith("/w/"):
                self._web_proxy(parsed.path, parsed.query)
            else:
                self.send_json({"error": "not found"}, 404)
        except ClientError as e:
            self.send_json({"error": str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_PUT(self):
        self._proxy_write()

    def do_PATCH(self):
        self._proxy_write()

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/web":
                if not self.check_pin():
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                WEB.stop()
                self.send_json({"ok": True})
            elif parsed.path.startswith("/api/sessions/"):
                if not self.check_pin():
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                name = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
                if name == WEB_NAME:
                    WEB.stop()
                    self.send_json({"ok": True, "web": True})
                    return
                validate_name(name)
                kill_tmux_session(name)
                self.send_json({"ok": True, "web": False})
            elif parsed.path == "/w" or parsed.path.startswith("/w/"):
                self._web_proxy(parsed.path, parsed.query)
            else:
                self.send_json({"error": "not found"}, 404)
        except ClientError as e:
            self.send_json({"error": str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_OPTIONS(self):
        self._proxy_write()

    def _proxy_write(self):
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path.startswith("/w/"):
                self._web_proxy(parsed.path, parsed.query)
            else:
                self.send_json({"error": "not found"}, 404)
        except ClientError as e:
            self.send_json({"error": str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass

    # -- 会话列表 --

    def _all_sessions(self):
        sessions = list_tmux_sessions()
        sessions.append(WEB.info())
        return sessions

    # -- Web 会话启动与反代 --

    def _web_launch(self):
        if not self.check_pin():
            self.send_json({"error": "需要访问口令"}, 401)
            return
        try:
            WEB.ensure_started(self._authority())
        except ClientError as e:
            self.send_html(self._error_page(str(e)), 502)
            return
        self.redirect("/w/?token=%s" % urllib.parse.quote(WEB.token))

    def _error_page(self, msg):
        safe = (msg.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))
        return ("<!doctype html><meta charset='utf-8'>"
                "<title>NasDSH</title>"
                "<body style='background:#101014;color:#e6e6ea;font:14px sans-serif;"
                "display:flex;align-items:center;justify-content:center;height:100vh'>"
                "<div style='max-width:520px;text-align:center'>"
                "<h3 style='color:#e05555'>dsh web 启动失败</h3>"
                "<p style='color:#8a8a96;white-space:pre-wrap'>%s</p>"
                "<p><a style='color:#4da3ff' href=''>重试</a></p></div></body>"
                % safe)

    def _web_proxy(self, path, query):
        if not self.check_pin():
            self.send_json({"error": "需要访问口令"}, 401)
            return
        rest = path[len("/w/"):] if path.startswith("/w/") else ""
        backend_path = "/" + rest
        if query:
            backend_path += "?" + query
        if not WEB.running():
            try:
                WEB.ensure_started(self._authority())
            except ClientError as e:
                self.send_html(self._error_page(str(e)), 502)
                return

        upgrade = (self.headers.get("Upgrade") or "").lower()
        if upgrade == "websocket":
            self._ws_proxy(backend_path)
        else:
            self._http_proxy(backend_path)

    def _read_request_body(self):
        """读取请求体；同时支持 Content-Length 与 chunked（大文件上传）。"""
        if (self.headers.get("Transfer-Encoding") or "").lower().strip() == "chunked":
            chunks = []
            total = 0
            while True:
                line = self.rfile.readline(65536).strip()
                if not line:
                    break
                try:
                    size = int(line.split(b";", 1)[0], 16)
                except ValueError:
                    raise ClientError("非法 chunked 请求体")
                if size == 0:
                    # 跳过 trailer
                    while True:
                        trailer = self.rfile.readline(65536)
                        if trailer in (b"\r\n", b"\n", b""):
                            break
                    break
                data = self.rfile.read(size)
                if len(data) != size:
                    raise ClientError("chunked 请求体不完整")
                chunks.append(data)
                total += size
                if total > (512 << 20):
                    raise ClientError("请求体过大")
                self.rfile.read(2)  # CRLF
            return b"".join(chunks)
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0:
            return b""
        if length > (512 << 20):
            raise ClientError("请求体过大")
        return self.rfile.read(length)

    def _http_proxy(self, backend_path):
        headers = {}
        for k, v in self.headers.items():
            if k.lower() in HOP_BY_HOP or k.lower() == "host":
                continue
            headers[k] = v
        # Host 必须原样保留：dsh 的 Cookie audience 与 browser-trust fence
        # 都按浏览器看到的 authority 校验。
        headers["Host"] = self._authority()
        body = None
        if self.command not in ("GET", "HEAD"):
            body = self._read_request_body()

        conn = None
        headers_sent = False
        try:
            conn = http.client.HTTPConnection("127.0.0.1", WEB.port, timeout=600)
            conn.request(self.command, backend_path, body=body, headers=headers)
            resp = conn.getresponse()
            self.send_response_only(resp.status, resp.reason)
            has_len = False
            for k, v in resp.getheaders():
                lk = k.lower()
                if lk in HOP_BY_HOP:
                    continue
                if lk == "content-length":
                    has_len = True
                elif lk == "location":
                    v = self._rewrite_location(v)
                self.send_header(k, v)
            if not has_len:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            headers_sent = True
            if self.command != "HEAD":
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except (OSError, http.client.HTTPException):
            if not headers_sent:
                try:
                    self.send_html(self._error_page("无法连接 dsh web（进程可能已退出）"), 502)
                except OSError:
                    pass
            else:
                self.close_connection = True
        finally:
            if conn is not None:
                conn.close()

    def _rewrite_location(self, value):
        """把 dsh 吐出的后端绝对地址改写到 /w/ 前缀。"""
        parsed = urllib.parse.urlsplit(value)
        if not parsed.scheme or not parsed.netloc:
            return value
        backend = {"127.0.0.1:%d" % WEB.port, "localhost:%d" % WEB.port,
                   "127.0.0.1", "localhost"}
        if parsed.netloc in backend:
            path = "/w%s" % (parsed.path or "/")
            return urllib.parse.urlunsplit(
                ("http", self._authority(), path, parsed.query, parsed.fragment))
        return value

    def _ws_proxy(self, backend_path):
        """原样转发 WebSocket 握手与帧（dsh 自己计算 Sec-WebSocket-Accept）。"""
        try:
            backend = socket.create_connection(("127.0.0.1", WEB.port), timeout=15)
        except OSError:
            self.send_json({"error": "无法连接 dsh web"}, 502)
            return
        backend.settimeout(None)
        try:
            lines = ["GET %s HTTP/1.1" % backend_path]
            for k, v in self.headers.items():
                lines.append("%s: %s" % (k, v))
            backend.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("utf-8"))
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = backend.recv(65536)
                if not chunk:
                    raise OSError("backend closed during handshake")
                data += chunk
                if len(data) > 65536:
                    raise OSError("handshake too large")
            head, _, extra = data.partition(b"\r\n\r\n")
            status = head.split(b"\r\n", 1)[0]
            self.connection.sendall(head + b"\r\n\r\n")
            self.close_connection = True
            if extra:
                self.connection.sendall(extra)
            if b" 101 " not in status and not status.endswith(b" 101"):
                backend.close()
                return
            self.wfile.flush()
            self.connection.settimeout(None)
            self._relay(self.connection, backend)
        except OSError:
            pass
        finally:
            try:
                backend.close()
            except OSError:
                pass

    @staticmethod
    def _relay(a, b):
        socks = [a, b]
        try:
            while True:
                r, _, _ = select.select(socks, [], [], 1.0)
                if not r:
                    continue
                for src in r:
                    dst = b if src is a else a
                    try:
                        data = src.recv(65536)
                    except OSError:
                        return
                    if not data:
                        return
                    dst.sendall(data)
        except OSError:
            return

    # -- CLI WebSocket --

    def _cli_ws(self, encoded, query):
        name = urllib.parse.unquote(encoded.split("/")[0])
        try:
            validate_name(name)
        except ClientError as e:
            self.send_json({"error": str(e)}, 400)
            return
        path = (query.get("path") or [""])[0]
        try:
            path = validate_path(path) if path else _default_root()
        except ClientError:
            path = _default_root()
        if name == WEB_NAME:
            self.send_json({"error": "该名称保留给共享 Web 实例"}, 400)
            return
        with CLI_CREATE_LOCK:
            if not session_exists(name):
                try:
                    create_cli_session(name, path)
                except ClientError as e:
                    self.send_json({"error": str(e)}, 400)
                    return

        if not hasattr(self, "connection"):
            return
        self.close_connection = True
        key = self.headers.get("Sec-WebSocket-Key", "")
        if not key:
            self.send_json({"error": "缺少 Sec-WebSocket-Key"}, 400)
            return
        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        self.send_response_only(101, "Switching Protocols")
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", accept)
        self.end_headers()
        self.wfile.flush()

        ws = WebSocket(self.connection)
        try:
            cols = int((query.get("cols") or ["120"])[0])
        except ValueError:
            cols = 120
        try:
            rows = int((query.get("rows") or ["32"])[0])
        except ValueError:
            rows = 32
        cols = min(max(cols, 20), 500)
        rows = min(max(rows, 5), 300)
        bridge = PtyBridge(ws, name, path)
        bridge.spawn(cols, rows)
        replay = capture_pane(name, lines=200)
        if replay:
            ws.send_binary(replay.encode("utf-8"))
        bridge.run()

    # -- 升级 dsh --

    def _upgrade(self):
        if not os.path.isfile(UPGRADE_BIN):
            self.send_json({"error": "升级脚本不存在"}, 501)
            return
        before = _read_version(DSH_BIN)
        try:
            env = os.environ.copy()
            env["CI"] = "1"
            p = subprocess.run([UPGRADE_BIN], capture_output=True, timeout=1200,
                               stdin=subprocess.DEVNULL, env=env)
            out = (p.stdout.decode("utf-8", "replace")
                   + p.stderr.decode("utf-8", "replace")).strip()
            rc = p.returncode
        except subprocess.TimeoutExpired:
            out, rc = "升级超时（20 分钟）", 1
        self.send_json({"ok": rc == 0, "before": before,
                        "after": _read_version(DSH_BIN),
                        "output": out[-6000:]})


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(HOME_DIR, exist_ok=True)
    os.makedirs(DSH_HOME_DIR, exist_ok=True)

    def shutdown(*_):
        WEB.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    print("[sessiond] listening on :%d (pin=%s, roots=%s)"
          % (PORT, "on" if TERM_PIN else "off", ",".join(ALLOWED_ROOTS) or "none"),
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
