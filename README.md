# SPEXRON Buds Monitor

**SPEXRON Buds App** · Developed by **SPEXRON SOFT** · Version **1.0.0**

A modern Windows 10/11 desktop & system-tray battery and session monitor for **Xiaomi, Redmi, POCO, and Mi Bluetooth earbuds**. It reads **independent Left bud, Right bud, and Charging Case** battery levels and charging states directly over Xiaomi's native RFCOMM control protocol—not Windows' single combined HFP estimate.

- **Universal Xiaomi Auto-Detection:** Automatically recognizes Xiaomi, Redmi, POCO, and Mi wireless earbuds/headphones (excluding phones, watches, and bands) and identifies any active `0000FD2D` headset by cached SDP service even if renamed.
- **Zero-Idle Resource Architecture:** Runs an event-driven background watcher (`--watch`) consuming ~2.5 MB RAM and ~0% CPU with **no continuous Bluetooth scanning**. The Qt interface (`--gui`) only launches when your earbuds connect and exits completely from memory when disconnected.
- **True Telemetry Only:** Displays `--` whenever a hardware unit (such as a closed charging case) is not reporting—never guessed or fabricated percentages.
- **Modern Dark & Light Studio UI:** Sculpted vector hardware illustrations with `270°` radial battery gauges, animated charging shimmers, segmented `SA : DK : SN` session chronometer, disconnect reason tracking, and built-in **Find My Earbuds** acoustic ringtone controls.

---

## Features

- **Per-Unit Battery & Charging Status:** Real-time percentage and charging indicator for Left, Right, and Charging Case.
- **Automatic Model Switching:** Switching between multiple paired Xiaomi headsets automatically updates the active device, model name, firmware, and telemetry.
- **Session Chronometer & Disconnect Analytics:** Live wear-time counter (`HH : MM : SS`) and persistent last-disconnect tracking (*battery empty*, *placed in case*, *Bluetooth off*, or *link lost*).
- **Find My Earbuds (`--find`):** Plays the native high-volume alert tone on Left, Right, or Both earbuds over FD2D `SET_CONFIG (0xF2)` with auto-stop timer.
- **Dual-Source Resilience:** Uses Xiaomi **FD2D RFCOMM** (`0000FD2D`) as the primary source and falls back seamlessly to **Google Fast Pair BLE** (`0xFE2C`) broadcasts if the RFCOMM channel is busy (e.g., phone multipoint active).
- **Bluetooth Diagnostics & Log Viewer:** Built-in diagnostic suite (`--diagnose`) capturing HFP properties, SDP services, live FD2D packets, and BLE advertisements.

---

## Building and Running the Application (Required)

> **Important:** This repository distributes source code only. You **must build the Windows executable** first and run the generated `.exe` (`SPEXRON Buds Monitor.exe`) for full desktop, system-tray, and Windows auto-start integration.

### Prerequisites

- **OS:** Windows 10 (1809+) or Windows 11 (64-bit)
- **Python:** **Python 3.12 or 3.13** (`PySide6-Essentials` is required)
- **Bluetooth:** Bluetooth adapter with Classic/BR-EDR support (BLE optional for Fast Pair fallback)
- Earbuds paired in Windows Bluetooth settings

### Step 1 — Set Up Dependencies

Open PowerShell or Command Prompt in the repository root:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

### Step 2 — Build the Executable (`.exe`)

Run the automated build script from the project root:

```bat
.\build.bat
```

`build.bat` invokes `build\build.py`, generates `assets\icon.ico` and `assets\icon.png`, compiles the standalone Qt/WinRT bundle via PyInstaller, and produces:

- `dist\SPEXRON Buds Monitor\SPEXRON Buds Monitor.exe` — standalone portable application folder (includes `portable.flag`)
- `SPEXRON Buds Monitor.exe` — root launcher pointing to `dist\SPEXRON Buds Monitor\`
- `SPEXRON Buds Monitor.lnk` — Windows shortcut

### Step 3 — Run the Generated `.exe`

Once built, **launch the compiled `.exe`**:

1. Double-click **`SPEXRON Buds Monitor.exe`** in the project root (or copy the entire `dist\SPEXRON Buds Monitor\` folder anywhere such as `C:\Apps\SPEXRON Buds Monitor\` and run the `.exe` inside it).
2. On first launch:
   - The main dashboard opens immediately.
   - The lightweight background connection watcher (`--watch`) starts automatically.
   - Startup auto-launch is enabled by default (toggleable in **Settings → General & Devices**).
3. From then on, the app wakes automatically whenever any paired Xiaomi Bluetooth earbud connects, shows a live battery ring icon in the system tray, and cleanly shuts down the GUI when disconnected.

> If you move the `dist\SPEXRON Buds Monitor\` folder to a new location, run `SPEXRON Buds Monitor.exe` once from the new path to refresh the Windows startup entry.

---

## Command-Line Modes

| Command | Description |
|---|---|
| `"SPEXRON Buds Monitor.exe"` | Ensures background watcher is running and opens the main window |
| `"SPEXRON Buds Monitor.exe" --watch` | Lightweight event-driven background connection watcher (no Qt) |
| `"SPEXRON Buds Monitor.exe" --gui` | Launches tray UI silently (started automatically by `--watch` on connect) |
| `"SPEXRON Buds Monitor.exe" --diagnose` | Generates a full Bluetooth diagnostic report in `logs/` and opens it |
| `"SPEXRON Buds Monitor.exe" --stop` | Stops any running background `--watch` process cleanly |
| `"SPEXRON Buds Monitor.exe" --find [left\|right\|both]` | Plays the Find My Earbuds sound via the active tray session |
| `"SPEXRON Buds Monitor.exe" --stop-find` | Stops the Find My Earbuds tone |

---

## Architecture & Protocol Overview

```text
Windows Sign-in ──► Watcher (--watch)          ~2.5 MB RAM, 0% CPU
                     │ Listens to WinRT ConnectionStatusChanged events
                     ▼ paired Xiaomi earbuds connect
                   Tray GUI (--gui)  ──► RFCOMM 0000FD2D (Primary)
                     │                    └─ Fast Pair 0xFE2C BLE (Fallback)
                     ▼ earbuds disconnected beyond grace timeout
                   GUI exits completely from memory
```

### Xiaomi FD2D Protocol (`0000fd2d-0000-1000-8000-00805f9b34fb`)
- **Framing:** `FE DC BA | type | opcode | length(2B BE) | seq | payload | EF`
- **Authentication (`0x50` / `0x51`):** Mutual 16-byte SAFER+ challenge-response handshake (no hardcoded device secrets).
- **Device Info (`0x02`):** Returns TLV records including hardware model name (`0x00`), BCD firmware (`0x01`), VID/PID (`0x03`), and battery triplet `[left, right, case]` (`0x07`).
- **Live Push Notifications (`0x0E`):** Headsets push updated `[left, right, case]` battery bytes on change (`bit 7` = charging, `bits 0–6` = `0–100%`, `0xFF` = unknown).

### Charging Case Battery Behavior
The charging case has no independent Bluetooth radio. Earbuds learn the case battery percentage over physical charging pins while docked with the **case lid open**:
- **Both earbuds worn / outside case:** Case reports `0xFF` → UI displays `--` (or last confirmed case reading with timestamp).
- **At least one earbud docked with lid open:** Real-time case battery level is reported immediately.
- **Both earbuds docked with lid closed:** Headsets power down Bluetooth → GUI exits cleanly.

---

## Development & Tests

Run directly from source during development or run the unit test suite (`24` tests covering protocol framing, SAFER+ auth, Fast Pair decoding, Find commands, session history, and universal Xiaomi device matching):

```powershell
.venv\Scripts\python.exe main.py
.venv\Scripts\python.exe -m pytest tests -v
```

### Project Layout

```text
SPEXRON-Buds-Monitor/
├─ main.py                  Entrypoint & CLI mode dispatcher
├─ requirements.txt         Python dependencies (PySide6, WinRT, PyInstaller, pytest)
├─ build.bat                One-click Windows EXE build script
├─ build/build.py           Icon generator, PyInstaller bundler, root launcher compiler
├─ bluetooth/
│  ├─ discovery.py          Universal Xiaomi audio recognition & cached FD2D detection
│  ├─ protocol.py           FD2D framing, TLV decoding, SAFER+ challenge-response auth
│  ├─ rfcomm.py             WinRT Bluetooth Classic RFCOMM socket client
│  ├─ buds_client.py        Persistent device session, refresh & Find Earbuds commands
│  ├─ fastpair.py           Google Fast Pair BLE advertisement fallback decoder
│  ├─ windows_battery.py    Windows HFP combined battery & arrival time reader
│  └─ diagnostics.py        Hardware/protocol diagnostics collector
├─ services/
│  ├─ watcher.py            Event-driven low-overhead connection watcher
│  ├─ backend.py            Asyncio Bluetooth engine & state dispatcher for Qt
│  ├─ config.py             JSON settings persistence & legacy pattern migration
│  ├─ session_history.py    Disconnect reason inference & session persistence
│  └─ paths.py, autostart.py, single_instance.py, logging_setup.py, efficiency.py
├─ ui/                      PySide6 dashboard, vector gauges, tray icon, settings, dialogs
├─ tests/                   Unit tests (protocol, discovery, Fast Pair, find, session)
└─ config/settings.example.json
```

---

## License & Acknowledgments

Protocol knowledge for Xiaomi/Redmi FD2D framing and SAFER+ authentication builds upon the open-source [Gadgetbridge](https://codeberg.org/Freeyourgadget/Gadgetbridge) project's Redmi Buds support (Jonathan Gobbo, **AGPL-3.0**). Because `bluetooth/protocol.py` includes a Python port of that authentication logic, any public distribution must comply with **AGPL-3.0** licensing terms.

© SPEXRON SOFT
