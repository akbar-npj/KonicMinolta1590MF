# Open Source Linux Driver for Konica Minolta pagepro 1590MF / 1580MF & bizhub 15 / 16

A modern, native 64-bit and ARM-compatible (aarch64 / x86_64) open-source driver suite for the **Konica Minolta pagepro 1590MF**, **pagepro 1580MF**, **bizhub 15**, and **bizhub 16** multi-function printers and scanners.

---

## 1. Executive Summary & Why This Driver Exists

Official Konica Minolta Linux support for these printers was discontinued over a decade ago and had major limitations:
- **Printer**: The vendor-provided Linux packages (`pagepro1590mfcupswrapper` and `pagepro1590mflpr`) relied on proprietary **32-bit x86 (i386)** binaries (`rawtobr3`, `brprintconflsr3`, `brcupsconfig4`) compiled in 2013 for Linux 2.2. They **fail to run on modern 64-bit distributions and ARM systems** (such as Raspberry Pi, ARM64 servers, and modern Linux workstations) without complex 32-bit multilib configurations.
- **Scanner**: Konica Minolta **never provided a Linux scanner driver** for the pagepro 1590MF series.

### Reverse Engineering Insights
By analyzing the Windows driver INF files (`KBPRMB0A.INF`, `kbimm10a.inf`, `twpp1590mfu.ini`), driver DLLs (`brscndev.dll`, `brtwds.dll`), and Linux filters with binary analysis tools:
1. **Brother OEM Engine**: The pagepro 1590MF and bizhub 16 are OEM rebrands of the **Brother MFC-7360N / DCP-7065DN** chassis, while the 1580MF and bizhub 15 correspond to the **DCP-7055** chassis.
2. **Printer Raster Protocol**: Emits PJL job control followed by Brother 1030 run-length/delta-row raster compression (`\x1b*b1030m`) packaged into blocks of `%dw\x00<num_lines><data>`.
3. **Scanner Wire Protocol**: The scanner operates on USB **Interface 1** (`MI_01`) using the Brother `brscan4` command set (`\x1bX\n...`), chunked framing (`0x81..0xC1`), PackBits decompression for B&W/Grayscale, and stream-wrapped JPEG decoding for 24-bit True Color.

---

## 2. IPP (Internet Printing Protocol) Support Analysis

### Does the Printer Hardware Support IPP Natively?
> [!IMPORTANT]
> **No.** The physical Konica Minolta pagepro 1590MF hardware does **not** feature an embedded IPP server, IPP Everywhere, AirPrint, or Mopria certification. Its network interface only supports raw AppSocket (Port 9100) and LPD/LPR (Port 515).

### How to Enable Full IPP / AirPrint with this Open Source Driver
When you install this driver on a Linux machine (or a Raspberry Pi print server) connected to the printer via USB or Ethernet LPR, **CUPS automatically exposes the printer over IPP and AirPrint**:
```bash
# Enable IPP network sharing in CUPS
sudo cupsctl --share-printers --remote-any
sudo lpadmin -p KM_pagepro_1590MF -o printer-is-shared=true
```
Once enabled, any device on your local network—including **iPhones (AirPrint), Android devices (Mopria), macOS, Windows, and Linux laptops**—can print to the pagepro 1590MF seamlessly over IPP without needing any vendor drivers!

---

## 3. Supported Hardware

| Model | Type | USB VID:PID | Scanner Type | Duplex |
|---|---|---|---|---|
| **pagepro 1590MF** | Laser MFP | `132B:20EA` | Flatbed + ADF | Automatic / Built-in |
| **pagepro 1580MF** | Laser MFP | `132B:20EC` | Flatbed | Manual |
| **bizhub 16** | Laser MFP | `132B:20EB` | Flatbed + ADF | Automatic / Built-in |
| **bizhub 15** | Laser MFP | `132B:20ED` | Flatbed | Manual |

USB Interface Map:
- **Interface 0** (`MI_00`): USB Printer (`USBPRINT`)
- **Interface 1** (`MI_01`): USB Scanner (Bulk IN/OUT)
- **Interface 2** (`MI_02`): USB Serial / Remote Configuration Port

---

## 4. Components

```
km1590mf-driver/
├── printer/
│   ├── src/
│   │   ├── rastertokm1590mf.cc   # Native CUPS filter (C++)
│   │   ├── job.cc / job.h        # PJL / PCL 1030 job framing
│   │   ├── line.cc / line.h      # 1030 compression algorithm
│   │   ├── block.h               # Block chunk serializer
│   │   └── cups_raster.h         # Portable CUPS raster definitions
│   ├── ppd/
│   │   ├── km-pagepro1590mf.ppd  # PPD for pagepro 1590MF
│   │   ├── km-pagepro1580mf.ppd  # PPD for pagepro 1580MF
│   │   ├── km-bizhub16.ppd       # PPD for bizhub 16
│   │   └── km-bizhub15.ppd       # PPD for bizhub 15
│   ├── km1590mf.drv              # CUPS driver compiler source
│   └── Makefile                  # Build script
├── scanner/
│   ├── km1590_scan.py            # Standalone scanner driver & CLI
│   ├── 99-km1590mf.rules         # udev permissions rule
│   └── km1590mf.conf             # SANE device configuration
├── tests/
│   ├── test_raster_encoder.cc    # Unit tests for raster compression
│   └── test_scanner_protocol.py  # Unit tests for PackBits and framing
├── install.sh                    # Automated one-click installer
└── README.md
```

---

## 5. Build & Installation

### Quick Build & Installation
```bash
# Clone the repository
git clone https://github.com/akbar-npj/KonicMinolta1590MF.git
cd KonicMinolta1590MF

# Build and run test suite
./build.sh

# Install driver to system (CUPS filter, PPDs, scanner CLI, udev rules)
sudo ./build.sh install
```

### Requirements
- **Build Tools**: `gcc` / `g++`, `make`, `ppdc` (CUPS PPD compiler)
- **Printing**: `cups`, `libcups`
- **Scanning**: `python3`, `python3-pyusb`, `python3-pillow`

### What build.sh Automates:
1. Validates build tools and runtime dependencies.
2. Compiles `rastertokm1590mf` natively for your CPU architecture (`aarch64`, `x86_64`, `armhf`).
3. Compiles PPD printer descriptions from `printer/km1590mf.drv` with `ppdc` and validates them with `cupstestppd`.
4. Executes the automated test suite (`test_raster_encoder` and `test_scanner_protocol.py`).
5. With `install` or `--install`:
   - Installs the filter into `/usr/lib/cups/filter/` and `/usr/libexec/cups/filter/`.
   - Installs the PPD files into `/usr/share/cups/model/km/`.
   - Installs `km1590-scan` CLI utility to `/usr/local/bin/`.
   - Configures `/etc/udev/rules.d/` permissions and SANE configuration.
   - Automatically detects connected devices and configures the CUPS queue.

---

## 6. Reverse Engineering & Architecture Documentation
For deep technical documentation on how the protocols were reverse-engineered using **REA MCP** (Ghidra decompilation of `rawtobr3` and `brscndev.dll`), wire formats, and decompression pipelines, read:
👉 **[Reverse Engineering & Compilation Guide (docs/REVERSE_ENGINEERING.md)](docs/REVERSE_ENGINEERING.md)**

---

## 6. Usage

### Printing
Print using standard Linux commands:
```bash
# Print a PDF document
lp -d KM_pagepro_1590MF document.pdf

# Print with duplex (two-sided) and toner save
lp -d KM_pagepro_1590MF -o sides=two-sided-long-edge -o brlaserEconomode=True document.pdf

# Print from tray 1 at 1200HQ resolution
lp -d KM_pagepro_1590MF -o InputSlot=Tray1 -o Resolution=1200dpi photo.pdf
```

### Scanning
Use the `km1590-scan` CLI utility:

```bash
# Scan a single page from flatbed in full color (300 DPI) to PDF
km1590-scan --mode color --output scan.pdf

# Scan multi-page document from the ADF (Automatic Document Feeder)
km1590-scan --source adf --mode color --resolution 300 -o multi_page_doc.pdf

# High-resolution 600 DPI grayscale scan saved as PNG
km1590-scan --mode gray --resolution 600 -o document.png

# Fast Black & White lineart scan at 150 DPI
km1590-scan --mode lineart --resolution 150 -o quick_text.pdf

# Check connected scanner devices
km1590-scan --list-devices
```

---

## 7. Testing & Verification

Run the included unit test suites:
```bash
# Test printer raster compression and block framing
g++ -std=c++11 -O2 -Ikm1590mf-driver/printer/src \
    km1590mf-driver/tests/test_raster_encoder.cc \
    km1590mf-driver/printer/src/line.cc -o test_raster
./test_raster

# Test scanner protocol framing and PackBits decompression
python3 km1590mf-driver/tests/test_scanner_protocol.py
```

---

## 8. License

This open source driver suite is released under the **GNU General Public License v2 (GPL-2.0)**.
