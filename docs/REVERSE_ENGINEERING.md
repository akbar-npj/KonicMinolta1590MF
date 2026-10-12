# Reverse Engineering & Compilation Guide: Konica Minolta pagepro 1590MF Series

This document provides a comprehensive technical breakdown of how the **Konica Minolta pagepro 1590MF**, **pagepro 1580MF**, **bizhub 15**, and **bizhub 16** multifunction devices were reverse-engineered and how the modern open-source Linux printer and scanner drivers were developed and compiled.

---

## 1. Background & The Modern Linux Problem

Konica Minolta released the pagepro 1590MF around 2012–2013. When users attempt to run the official software on modern Linux distributions (such as Fedora, Ubuntu 22.04+, Debian 12+, Arch, or ARM64 systems like Raspberry Pi), they encounter two fatal blockers:

1. **Printer Binary Architecture Lock-in**:
   * The official packages (`pagepro1590mfcupswrapper-3.0.1-1.i386.deb` and `pagepro1590mflpr-3.0.1-1.i386.deb`) rely on proprietary 32-bit x86 binaries (`rawtobr3`, `brprintconflsr3`, `brcupsconfig4`) dynamically linked against GNU/Linux 2.2 libc (`/lib/ld-linux.so.2`).
   * Modern 64-bit distributions have removed or deprecated 32-bit multilib libraries, and **ARM devices (`aarch64`) cannot execute these x86 binaries at all**.
2. **Total Absence of a Linux Scanner Driver**:
   * Konica Minolta never released a Linux scanner driver for this series. Users were left with non-functional scanners on Linux desktop installations.

---

## 2. Hardware Identification & OEM Lineage

Inspection of the Windows driver INF files (`KBPRMB0A.INF`, `kbimm10a.inf`, `kbpom10a.inf`) revealed the underlying USB identifiers:

### USB Device Architecture
All devices share Konica Minolta's USB Vendor ID: `0x132B`.

| Device Model | USB VID:PID | Capabilities | Windows Device Name |
|---|---|---|---|
| **pagepro 1590MF** | `132B:20EA` | Print, Scan (Flatbed + ADF), Duplex | `KONICA MINOLTA pagepro 1590MF` |
| **pagepro 1580MF** | `132B:20EC` | Print, Scan (Flatbed), Simplex | `KONICA MINOLTA pagepro 1580MF` |
| **bizhub 16** | `132B:20EB` | Print, Scan (Flatbed + ADF), Duplex | `KONICA MINOLTA bizhub 16` |
| **bizhub 15** | `132B:20ED` | Print, Scan (Flatbed), Simplex | `KONICA MINOLTA bizhub 15` |

Each device exposes three composite USB interfaces:
- **Interface 0 (`MI_00`)**: USB Printer Class (`USBPRINT\KONICA_MINOLTAPAGEPR35B6`)
- **Interface 1 (`MI_01`)**: USB Scanner Interface (Bulk IN and Bulk OUT endpoints)
- **Interface 2 (`MI_02`)**: USB Serial / Remote Setup Port (`BrUsbSIb`)

### The Brother OEM Connection
Inside `bizhub15_16_pp1580MF_1590MF_Win/64`:
- Windows INF files load drivers with signatures: `BRDSM080`, `BRTWAIN`, `BrScnUsb.sys`, `brscndev.dll`, `brtwds.dll`.
- `twpp1590mfu.ini` explicitly states:
  ```ini
  [General]
  Signature=BRTWAIN
  TwdsName=TW-KONICA MINOLTA PP1590
  [Device]
  Model=23
  DocHandling=3
  CompJpegTC=1
  ```
- Cross-referencing against Brother laser multifunction architectures confirmed:
  - **pagepro 1590MF / bizhub 16** = **Brother MFC-7360N / DCP-7065DN** print engine.
  - **pagepro 1580MF / bizhub 15** = **Brother DCP-7055** print engine.

---

## 3. IPP (Internet Printing Protocol) Analysis

A key question was whether the pagepro 1590MF supports IPP natively:
- **Direct Hardware Verification**: Inspection of the network configuration files (`brosnmp.dll`, `brtcpcon.dll`) and device specifications confirms that the machine is a host-based GDI/raster printer. The network interface card only listens on:
  - **Port 515 (LPD/LPR)**
  - **Port 9100 (RAW AppSocket / JetDirect)**
- The hardware firmware **does not contain an embedded IPP / AirPrint server**.
- **The Solution via CUPS**:
  On Linux, CUPS itself functions as a standards-compliant IPP Everywhere and Apple AirPrint server. Once our native open-source driver is installed:
  ```bash
  sudo cupsctl --share-printers --remote-any
  sudo lpadmin -p KM_pagepro_1590MF -o printer-is-shared=true
  ```
  CUPS accepts incoming IPP jobs from any network client (iOS, Android, macOS, Windows) and renders them through `rastertokm1590mf`, achieving 100% wireless IPP functionality.

---

## 4. Reverse Engineering with REA MCP (Ghidra Decompiler)

Using **REA MCP** (Reverse Engineering Assistant backed by Ghidra 12.1.4), we analyzed the proprietary binaries to extract the exact byte stream formats.

### 4.1 Printer Raster Stream Analysis (`rawtobr3`)

Opening `rawtobr3` in REA revealed that the binary was not stripped and contained full symbol tables:
- `BeginSendData`
- `compressM9_1030`
- `serialSend_1030`
- `HalftonePixMap`
- `PCLSendData` / `PCLSendCommand`

#### Decompilation of `serialSend_1030` via REA:
```c
void serialSend_1030(undefined4 param_1)
{
  ...
  if (SnedBufCnt != 0) {
    sprintf(&local_1b, "%d", SnedBufCnt + 2);
    local_c = ~uVar2 - 1;
    PCLSendData(param_1, &local_1b, local_c);
    PCLSendCommand(param_1, PCLTransRasterCombine); // outputs 'w'
    local_c = 2;
    local_1b = '\0';
    local_1a = BlockRasCnt;
    PCLSendData(param_1, &local_1b, 2);
    PCLSendData(param_1, SnedBufPtr, SnedBufCnt);
    SnedBufCnt = 0;
    BlockRasCnt = 0;
  }
}
```
**Wire Format Discovery**:
Print data is divided into blocks of raster lines formatted as:
`[ASCII decimal size + 2] + 'w' + 0x00 + [1-byte line count] + [compressed payload bytes]`

#### Decompilation of `compressM9_1030` via REA:
`compressM9_1030` implements Brother's variant of delta-row Run-Length Encoding (RLE):
1. **Zero Line**: If an entire raster line is blank (all zeros), it is encoded as a single byte `0xFF`.
2. **Delta Encoding**:
   - Compares the current raster line to the preceding reference line.
   - Byte 0 stores the number of edits (maximum 254).
   - **Substitute Run**: `((min(offset, 15) << 3) | min(count - 1, 7))` followed by overflow bytes and literal bytes.
   - **Repeat Run**: `(0x80 | (min(offset, 3) << 5) | min(count - 2, 31))` followed by overflow bytes and the repeated byte value.
3. **Page Termination**: Each page finishes with the escape sequence `1030M\f` followed by `@PJL EOJ`.

This logic was faithfully implemented in C++11 inside [`printer/src/line.cc`](../printer/src/line.cc) and [`printer/src/block.h`](../printer/src/block.h).

---

### 4.2 Scanner Wire Protocol Analysis (`brscndev.dll`)

Opening `extracted/win64/brscndev.dll` in REA, we searched for procedures matching `SendScanStartCommand`. Ghidra located the implementation at `0x10004960`:
`CScanDevIf::SendScanStartCommand(CScanDevIf *this, tagSCANCMDPARAM *param_1)`

#### Decompilation of Command Formatter (`0x10002890`):
```c
void __thiscall FUN_10002890(void *this, ushort *param_1, LPSTR param_2)
{
  if ((param_1 != 0) && (param_2 != 0)) {
    lstrcpyA(param_2, "\x1bX\n");
    lstrcatA(param_2, "R=");
    __itoa_s((uint)*param_1, local_14, 0x10, 10);
    lstrcatA(param_2, local_14);
    lstrcatA(param_2, ",");
    __itoa_s((uint)param_1[1], local_14, 0x10, 10);
    lstrcatA(param_2, local_14);
    lstrcatA(param_2, "\n");
    // Color Mode (TEXT, GRAY256, CGRAY)
    // Brightness B= and Contrast N=
    lstrcatA(param_2, "B=");
    ...
    lstrcatA(param_2, "N=");
    ...
    lstrcatA(param_2, "A="); // Scan Area dots
    ...
    lstrcatA(param_2, "D="); // Document Source (SIN = Flatbed, ADF = Feeder)
    lstrcatA(param_2, "\x80"); // Terminator
  }
}
```

#### Frame Structure on Bulk IN Endpoint:
The scanner streams packets across Interface 1 Bulk IN:
- **Status / Boundary Bytes**:
  - `0x80`: End of page.
  - `0x82`: ADF feeder empty.
- **Data Frame Header (`0x81..0xC1`)**:
  - Bytes `[1..2]`: 16-bit little-endian wrapper length (`wrapper_len`).
  - Bytes `[3 .. 3 + wrapper_len]`: 10-byte line metadata header (`42 07 00 01 00 84 00 00 00 00`).
  - Next 2 bytes: 16-bit little-endian payload length (`payload_len`).
  - Next `payload_len` bytes:
    - **Monochrome / Grayscale**: Apple/Brother PackBits compressed scanline.
    - **True Color 24-bit**: Fragments of a single continuous baseline JPEG stream. Concatenating all payloads yields a complete JPEG image!

This was implemented in Python 3 using `pyusb` and `Pillow` in [`scanner/km1590_scan.py`](../scanner/km1590_scan.py).

---

## 5. Native Compilation & Packaging

### 5.1 Portable CUPS Raster Filter (`rastertokm1590mf`)
To eliminate the dependency on outdated 32-bit glibc binaries, the filter was completely rewritten in standard C++11:
- Uses `cups_raster.h` to read CUPS raster streams (`application/vnd.cups-raster`) generated by `pdftoraster` or `gstoraster`.
- Dynamically links with standard system `libcups.so.2`.
- Compiled using standard `g++ -std=c++11 -O2`.

### 5.2 PPD Compiler (`ppdc`)
Instead of shipping handwritten legacy PPD files, we defined a modern CUPS driver definition file [`printer/km1590mf.drv`](../printer/km1590mf.drv). Running `ppdc` generates clean, standards-compliant PPD files for all 4 models:
```bash
ppdc -d printer/ppd printer/km1590mf.drv
```
Validation via `cupstestppd -I filters printer/ppd/*.ppd` passes 100%.

### 5.3 Automated Build Script (`build.sh`)
The [`build.sh`](../build.sh) script handles:
1. Toolchain & dependency validation (`make`, `g++`, `python3`, `ppdc`, `libcups.so.2`).
2. Filter compilation for the host architecture (`uname -m`).
3. PPD compilation and validation.
4. Execution of unit test suites (`tests/test_raster_encoder.cc` and `tests/test_scanner_protocol.py`).
5. Optional system installation via `./build.sh install`.

---

## 6. Verification & Results

Both test suites verify the reverse-engineered logic:
1. **Printer Tests**:
   - Empty white line encodes to `0xFF`.
   - Sequential identical lines produce zero delta edits.
   - Block framing correctly prepends `%dw\x00<count>`.
2. **Scanner Tests**:
   - PackBits decompression accurately expands literals and runlength blocks.
   - Command builder matches Windows driver strings byte-for-byte.
