#!/usr/bin/env python3
"""
km1590_print.py - Standalone Python Print Utility for Konica Minolta pagepro 1590MF Series
Supports:
  - pagepro 1590MF (132B:20EA)
  - pagepro 1580MF (132B:20EC)
  - bizhub 16 (132B:20EB)
  - bizhub 15 (132B:20ED)

Can be executed on any Linux system, Raspberry Pi, or Android (inside Termux / Pydroid 3).
Connects directly to the printer via:
  - Network RAW Port 9100 (--host <PRINTER_IP>)
  - USB OTG / Direct USB (--usb)
  - Output binary file (--output <FILE>)
"""

import sys
import os
import argparse
import socket
import subprocess
import tempfile
from typing import List, Tuple, Optional

# Supported USB devices (VID:PID)
SUPPORTED_DEVICES = {
    (0x132B, 0x20EA): "Konica Minolta pagepro 1590MF",
    (0x132B, 0x20EC): "Konica Minolta pagepro 1580MF",
    (0x132B, 0x20EB): "Konica Minolta bizhub 16",
    (0x132B, 0x20ED): "Konica Minolta bizhub 15",
}

# --- 1030 Raster Compression Algorithm ---

def _write_overflow(val: int, out: bytearray):
    if val >= 0:
        if val < 255:
            out.append(val)
        else:
            out.extend([255] * (val // 255))
            out.append(val % 255)

def _write_substitute(offset: int, chunk: bytes, out: bytearray):
    offset_max = 15
    count_max = 7
    count = len(chunk) - 1

    offset_low = min(offset, offset_max)
    count_low = min(count, count_max)
    out.append((offset_low << 3) | count_low)
    _write_overflow(offset - offset_max, out)
    _write_overflow(count - count_max, out)
    out.extend(chunk)

def _write_repeat(offset: int, count: int, val: int, out: bytearray):
    offset_max = 3
    count_max = 31
    count -= 2
    offset_low = min(offset, offset_max)
    count_low = min(count, count_max)
    out.append(128 | (offset_low << 5) | count_low)
    _write_overflow(offset - offset_max, out)
    _write_overflow(count - count_max, out)
    out.append(val)

def encode_line(line: bytes, reference: Optional[bytes] = None) -> bytes:
    """Encode a single scanline using Brother 1030 compression."""
    if not any(line):
        return bytes([0xFF])
    
    if reference is None:
        out = bytearray([1])
        _write_substitute(0, line, out)
        return bytes(out)

    out = bytearray([0]) # Placeholder for edit count
    max_edits = 254
    num_edits = 0

    end_idx = len(line)
    while end_idx > 0 and line[end_idx - 1] == reference[end_idx - 1]:
        end_idx -= 1

    idx = 0
    while idx < end_idx:
        start_mismatch = idx
        while start_mismatch < end_idx and line[start_mismatch] == reference[start_mismatch]:
            start_mismatch += 1

        offset = start_mismatch - idx
        idx = start_mismatch
        if idx >= end_idx:
            break

        num_edits += 1
        if num_edits == max_edits:
            _write_substitute(offset, line[idx:end_idx], out)
            break

        val = line[idx]
        run_len = 1
        while idx + run_len < end_idx and line[idx + run_len] == val:
            run_len += 1

        if run_len >= 3:
            _write_repeat(offset, run_len, val, out)
            idx += run_len
        else:
            sub_end = idx + 1
            while sub_end < end_idx:
                if sub_end + 1 < end_idx and line[sub_end] == reference[sub_end] and line[sub_end + 1] == reference[sub_end + 1]:
                    break
                if sub_end + 2 < end_idx and line[sub_end] == line[sub_end + 1] == line[sub_end + 2]:
                    break
                sub_end += 1
            _write_substitute(offset, line[idx:sub_end], out)
            idx = sub_end

    out[0] = num_edits
    return bytes(out)

class RasterBlock:
    """Buffers lines and flushes in chunks of %dw\0<lines><data>."""
    def __init__(self):
        self.lines: List[bytes] = []

    def add_line(self, data: bytes):
        self.lines.append(data)

    def flush(self) -> bytes:
        if not self.lines:
            return b""
        total_data = b"".join(self.lines)
        num_lines = len(self.lines)
        header = f"{len(total_data) + 2}w\x00".encode("ascii")
        blk = header + bytes([num_lines]) + total_data
        self.lines = []
        return blk

# --- PJL & Page Framing ---

def build_pjl_header(job_name: str, resolution: int = 600, economode: bool = False,
                     paper: str = "A4", duplex: bool = False, copies: int = 1) -> bytes:
    pjl = bytearray()
    pjl.extend(b"\x00" * 128)
    pjl.extend(b"\033%-12345X@PJL\n")
    clean_name = "".join(c for c in job_name if 32 <= ord(c) < 127 and c not in '"\\')[:32]
    pjl.extend(f'@PJL JOB NAME="{clean_name}"\n'.encode("ascii"))
    pjl.extend(b"\033%-12345X@PJL\n")
    
    if resolution == 1200:
        pjl.extend(b"@PJL SET RAS1200MODE = TRUE\n")
        pjl.extend(b"@PJL SET RESOLUTION = 600\n")
    else:
        pjl.extend(b"@PJL SET RAS1200MODE = FALSE\n")
        pjl.extend(f"@PJL SET RESOLUTION = {resolution}\n".encode("ascii"))

    pjl.extend(f"@PJL SET ECONOMODE = {'ON' if economode else 'OFF'}\n".encode("ascii"))
    pjl.extend(b"@PJL SET SOURCETRAY = AUTO\n")
    pjl.extend(b"@PJL SET MEDIATYPE = REGULAR\n")
    pjl.extend(f"@PJL SET PAPER = {paper.upper()}\n".encode("ascii"))
    pjl.extend(b"@PJL SET PAGEPROTECT = AUTO\n")
    pjl.extend(b"@PJL SET ORIENTATION = PORTRAIT\n")
    pjl.extend(b"@PJL ENTER LANGUAGE = PCL\n")
    pjl.extend(b"\033E")
    pjl.extend(f"\033&l{max(1, copies)}X".encode("ascii"))
    if duplex:
        pjl.extend(b"\033&l2S")
    return bytes(pjl)

def build_pjl_footer(job_name: str) -> bytes:
    pjl = bytearray()
    pjl.extend(b"\033%-12345X@PJL\n")
    clean_name = "".join(c for c in job_name if 32 <= ord(c) < 127 and c not in '"\\')[:32]
    pjl.extend(f'@PJL EOJ NAME="{clean_name}"\n'.encode("ascii"))
    pjl.extend(b"\033%-12345X\n")
    return bytes(pjl)

def encode_image_page(img, resolution: int = 600) -> bytes:
    """Converts a PIL image (monochrome) into Brother 1030 raster bytes."""
    # Ensure monochrome 1-bit
    if img.mode != '1':
        img = img.convert('1')

    width, height = img.size
    line_bytes_len = (width + 7) // 8

    # Brother expects 1 = black, 0 = white. Standard PIL '1' has 0 = black, 255 = white.
    # We invert bytes
    raw_bitmap = img.tobytes()

    page_data = bytearray()
    page_data.extend(b"\033*b1030m")

    blk = RasterBlock()
    lines_per_band = 64
    prev_line = None

    for y in range(height):
        start = y * line_bytes_len
        line_slice = raw_bitmap[start:start + line_bytes_len]
        # Invert bits: PIL 0=black, 1=white -> printer 1=black, 0=white
        line = bytes(~b & 0xFF for b in line_slice)

        if y % lines_per_band == 0:
            page_data.extend(blk.flush())
            enc = encode_line(line)
        else:
            enc = encode_line(line, prev_line)

        blk.add_line(enc)
        prev_line = line

    page_data.extend(blk.flush())
    page_data.extend(b"\014") # Form Feed
    return bytes(page_data)

# --- Document Rendering Helpers ---

def render_document_to_images(file_path: str, resolution: int = 600):
    """Renders PDF or opens image, yielding PIL Image objects."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        # 1. Try pdftoppm (standard on Linux and Termux poppler)
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                prefix = os.path.join(tmpdir, "page")
                cmd = ["pdftoppm", "-r", str(resolution), "-mono", file_path, prefix]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res.returncode == 0:
                    from PIL import Image
                    pages = sorted([os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.startswith("page-")])
                    for p in pages:
                        with Image.open(p) as img:
                            yield img.copy()
                    return
        except FileNotFoundError:
            pass

        # 2. Try pypdfium2
        try:
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(file_path)
            for page in pdf:
                pil_img = page.render(scale=resolution/72.0).to_pil().convert('1')
                yield pil_img
            return
        except ImportError:
            pass

        # 3. Try fitz (PyMuPDF)
        try:
            import fitz
            doc = fitz.open(file_path)
            zoom = resolution / 72.0
            mat = fitz.Matrix(zoom, zoom)
            from PIL import Image
            for page in doc:
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
                img = Image.frombytes("L", [pix.width, pix.height], pix.samples).convert('1')
                yield img
            return
        except ImportError:
            pass

        raise RuntimeError(
            "PDF rendering requires either 'pdftoppm' (install with: pkg install poppler or apt install poppler-utils) "
            "or 'pypdfium2' (pip install pypdfium2)."
        )
    else:
        # Standard image (PNG, JPG, TIFF, BMP)
        try:
            from PIL import Image
            with Image.open(file_path) as img:
                yield img.copy()
        except ImportError:
            raise RuntimeError("Image printing requires Pillow: install with 'pip install Pillow' or 'pkg install python-pillow'.")

# --- Transports ---

def send_via_network(host: str, port: int, payload: bytes):
    print(f"Connecting to printer at {host}:{port}...")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(15.0)
        s.connect((host, port))
        print(f"Transmitting {len(payload)} bytes...")
        s.sendall(payload)
        print("Job sent successfully!")

def send_via_usb(payload: bytes):
    try:
        import usb.core
        import usb.util
    except ImportError:
        raise RuntimeError("USB printing requires pyusb: install with 'pip install pyusb' or 'pkg install libusb'.")

    dev = None
    for (vid, pid), desc in SUPPORTED_DEVICES.items():
        dev = usb.core.find(idVendor=vid, idProduct=pid)
        if dev is not None:
            print(f"Found {desc} (USB {vid:04x}:{pid:04x})")
            break

    if dev is None:
        raise RuntimeError("No supported Konica Minolta printer detected on USB.")

    # Claim printer interface 0
    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except Exception:
        pass

    dev.set_configuration()
    cfg = dev.get_active_configuration()
    intf = cfg[(0, 0)] # Interface 0, Alternate 0

    ep_out = None
    for ep in intf:
        if usb.util.endpoint_direction(ep.bEndpointAddress) == usb.util.ENDPOINT_OUT:
            ep_out = ep
            break

    if ep_out is None:
        raise RuntimeError("Printer bulk OUT endpoint not found.")

    print(f"Sending {len(payload)} bytes via USB Bulk OUT endpoint 0x{ep_out.bEndpointAddress:02x}...")
    chunk_size = 16384
    for i in range(0, len(payload), chunk_size):
        ep_out.write(payload[i:i + chunk_size], timeout=10000)
    print("Job sent successfully over USB!")

# --- Main CLI ---

def main():
    parser = argparse.ArgumentParser(
        description="Standalone Printer CLI for Konica Minolta pagepro 1590MF / 1580MF & bizhub 15 / 16"
    )
    parser.add_argument("file", help="Document or image file to print (PDF, PNG, JPG, BMP)")
    parser.add_argument("--host", help="Printer IP address (connects via RAW Port 9100)")
    parser.add_argument("--port", type=int, default=9100, help="Printer port (default 9100)")
    parser.add_argument("--usb", action="store_true", help="Print directly via USB / USB OTG cable")
    parser.add_argument("--output", "-o", help="Write raw printer byte stream to output file instead of sending")
    parser.add_argument("--resolution", type=int, choices=[300, 600, 1200], default=600, help="Print resolution (DPI)")
    parser.add_argument("--paper", choices=["A4", "LETTER", "LEGAL"], default="A4", help="Paper size")
    parser.add_argument("--copies", type=int, default=1, help="Number of copies")
    parser.add_argument("--economode", action="store_true", help="Enable Toner Save mode")
    parser.add_argument("--duplex", action="store_true", help="Enable two-sided duplex printing")

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    if not args.host and not args.usb and not args.output:
        print("Notice: No destination specified (--host, --usb, or -o). Defaulting to --host 192.168.1.50 or specify -o out.prn")
        # If running in Termux with environment variable PRINTER_IP
        env_ip = os.environ.get("PRINTER_IP")
        if env_ip:
            args.host = env_ip
        else:
            args.output = "print_job.prn"
            print(f"Writing output to {args.output}")

    job_name = os.path.basename(args.file)
    print(f"Processing job '{job_name}' at {args.resolution} DPI ({args.paper})...")

    # Build print job
    job_stream = bytearray()
    job_stream.extend(build_pjl_header(
        job_name=job_name,
        resolution=args.resolution,
        economode=args.economode,
        paper=args.paper,
        duplex=args.duplex,
        copies=args.copies
    ))

    page_count = 0
    for page_img in render_document_to_images(args.file, resolution=args.resolution):
        page_count += 1
        print(f"  Rasterizing & compressing page {page_count} ({page_img.width}x{page_img.height})...")
        job_stream.extend(encode_image_page(page_img, resolution=args.resolution))

    if page_count == 0:
        print("Error: No pages were rendered from the document.", file=sys.stderr)
        sys.exit(1)

    job_stream.extend(build_pjl_footer(job_name))
    print(f"Total job payload: {len(job_stream)} bytes ({page_count} page(s)).")

    if args.output:
        with open(args.output, "wb") as f:
            f.write(job_stream)
        print(f"Saved printer payload to {args.output}")

    if args.host:
        send_via_network(args.host, args.port, bytes(job_stream))

    if args.usb:
        send_via_usb(bytes(job_stream))

if __name__ == "__main__":
    main()
