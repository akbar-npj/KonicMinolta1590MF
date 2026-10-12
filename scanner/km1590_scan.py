#!/usr/bin/env python3
"""
Open Source Scanner Driver & CLI for Konica Minolta pagepro 1590MF / 1580MF / bizhub 15 / bizhub 16
Reverse engineered from Brother/Konica Minolta BRTWAIN protocol.

Supports:
- Flatbed and ADF (Automatic Document Feeder)
- Resolutions: 100, 150, 200, 300, 600 DPI
- Modes: Lineart (1-bit B&W), Gray (8-bit Grayscale), Color (24-bit RGB)
- Multi-page ADF scanning to single PDF or sequence of images
"""

import sys
import os
import time
import argparse
import io
from typing import Optional, List, Tuple

try:
    import usb.core
    import usb.util
except ImportError:
    usb = None

try:
    from PIL import Image
except ImportError:
    Image = None

# Known USB Hardware IDs for Konica Minolta OEM Multifunction Devices
VENDOR_KM = 0x132B
SUPPORTED_DEVICES = {
    0x20EA: {
        "name": "KONICA MINOLTA pagepro 1590MF",
        "has_adf": True,
        "max_width_dpi600": 5100,
        "max_height_dpi600": 7000,
    },
    0x20EC: {
        "name": "KONICA MINOLTA pagepro 1580MF",
        "has_adf": False,
        "max_width_dpi600": 5100,
        "max_height_dpi600": 7000,
    },
    0x20EB: {
        "name": "KONICA MINOLTA bizhub 16",
        "has_adf": True,
        "max_width_dpi600": 5100,
        "max_height_dpi600": 7000,
    },
    0x20ED: {
        "name": "KONICA MINOLTA bizhub 15",
        "has_adf": False,
        "max_width_dpi600": 5100,
        "max_height_dpi600": 7000,
    },
}

# Scanner USB Interface is Interface 1 (Interface 0 is Printer, Interface 2 is Serial/Remote)
SCANNER_INTERFACE_NUMBER = 1


def decompress_packbits(data: bytes, expected_length: int) -> bytes:
    """Decompress Apple/Brother PackBits RLE data."""
    out = bytearray()
    i = 0
    data_len = len(data)
    while i < data_len and len(out) < expected_length:
        n = data[i]
        i += 1
        if n <= 127:
            # Copy next n + 1 literal bytes
            count = n + 1
            out.extend(data[i : i + count])
            i += count
        else:
            # Repeat next byte (257 - n) times (n is signed negative: 1 - signed)
            count = 257 - n
            if i < data_len:
                val = data[i]
                i += 1
                out.extend([val] * count)
    return bytes(out[:expected_length])


class KMScannerDevice:
    def __init__(self, dev=None):
        self.dev = dev
        self.info = None
        self.ep_out = None
        self.ep_in = None
        self.interface = None

    @classmethod
    def find_devices(cls) -> List["KMScannerDevice"]:
        if usb is None:
            raise RuntimeError("pyusb library is not installed. Run: pip install pyusb")

        devices = []
        for pid, info in SUPPORTED_DEVICES.items():
            found = usb.core.find(find_all=True, idVendor=VENDOR_KM, idProduct=pid)
            for d in found:
                dev_obj = cls(d)
                dev_obj.info = info
                devices.append(dev_obj)
        return devices

    def open(self):
        if not self.dev:
            devs = self.find_devices()
            if not devs:
                raise RuntimeError("No Konica Minolta 1590MF/1580MF/bizhub scanner found on USB.")
            self.dev = devs[0].dev
            self.info = devs[0].info

        # Detach kernel driver on interface 1 if attached
        try:
            if self.dev.is_kernel_driver_active(SCANNER_INTERFACE_NUMBER):
                self.dev.detach_kernel_driver(SCANNER_INTERFACE_NUMBER)
        except (usb.core.USBError, NotImplementedError):
            pass

        # Set configuration
        try:
            self.dev.set_configuration()
        except usb.core.USBError:
            pass

        # Claim scanner interface (Interface 1)
        usb.util.claim_interface(self.dev, SCANNER_INTERFACE_NUMBER)

        # Find Bulk IN and Bulk OUT endpoints on Interface 1
        cfg = self.dev.get_active_configuration()
        intf = None
        for i in cfg:
            if i.bInterfaceNumber == SCANNER_INTERFACE_NUMBER:
                intf = i
                break

        if intf is None:
            raise RuntimeError("Scanner interface 1 not found on device.")

        self.interface = intf
        for ep in intf:
            ep_dir = usb.util.endpoint_direction(ep.bEndpointAddress)
            ep_type = usb.util.endpoint_type(ep.bEndpointAddress)
            if ep_type == usb.util.ENDPOINT_TYPE_BULK:
                if ep_dir == usb.util.ENDPOINT_IN:
                    self.ep_in = ep
                elif ep_dir == usb.util.ENDPOINT_OUT:
                    self.ep_out = ep

        if not self.ep_in or not self.ep_out:
            raise RuntimeError("Could not find Bulk IN and OUT endpoints on scanner interface.")

    def close(self):
        if self.dev:
            try:
                usb.util.release_interface(self.dev, SCANNER_INTERFACE_NUMBER)
            except Exception:
                pass

    def build_scan_command(
        self,
        resolution: int = 300,
        mode: str = "color",
        source: str = "flatbed",
        brightness: int = 50,
        contrast: int = 50,
        width_dots: Optional[int] = None,
        height_dots: Optional[int] = None,
    ) -> bytes:
        cmd = bytearray(b"\x1bX\n")

        # Resolution
        cmd.extend(f"R={resolution},{resolution}\n".encode("ascii"))

        # Color mode
        mode_upper = mode.lower()
        if mode_upper in ("lineart", "bw", "1bit"):
            cmd.extend(b"M=TEXT\n")
            cmd.extend(b"C=RLENGTH\n") # PackBits
        elif mode_upper in ("gray", "grayscale", "gray256"):
            cmd.extend(b"M=GRAY256\n")
            cmd.extend(b"C=RLENGTH\n")
        elif mode_upper in ("color", "rgb", "truecolor"):
            cmd.extend(b"M=CGRAY\n")
            # In color mode, Brother/KM uses JPEG streaming
            cmd.extend(b"C=JPEG\n")
        else:
            raise ValueError(f"Unknown scan mode: {mode}")

        # Brightness & Contrast (0..100 -> percentage)
        b_val = max(-50, min(50, brightness - 50))
        n_val = max(-50, min(50, contrast - 50))
        cmd.extend(f"B={b_val:+d}\n".encode("ascii") if b_val != 0 else b"B=0\n")
        cmd.extend(f"N={n_val:+d}\n".encode("ascii") if n_val != 0 else b"N=0\n")

        # Business / Photo mode
        cmd.extend(b"U=OFF\n")
        cmd.extend(b"P=OFF\n")

        # Scan Area: A=left,top,right,bottom
        # A4 at resolution:
        # Standard A4 width = 8.27 in, height = 11.69 in
        w = width_dots if width_dots else int(resolution * 8.27)
        h = height_dots if height_dots else int(resolution * 11.69)
        cmd.extend(f"A=0,0,{w},{h}\n".encode("ascii"))

        # Document source
        if source.lower() == "adf":
            cmd.extend(b"D=ADF\n")
        else:
            cmd.extend(b"D=SIN\n")

        # Terminator
        cmd.extend(b"\x80")
        return bytes(cmd)

    def scan_page(
        self,
        resolution: int = 300,
        mode: str = "color",
        source: str = "flatbed",
        brightness: int = 50,
        contrast: int = 50,
        page_num: int = 1,
    ) -> Optional["Image.Image"]:
        if Image is None:
            raise RuntimeError("Pillow library is not installed. Run: pip install Pillow")

        if page_num == 1:
            cmd = self.build_scan_command(
                resolution=resolution,
                mode=mode,
                source=source,
                brightness=brightness,
                contrast=contrast,
            )
        else:
            # Next page command for ADF
            cmd = b"\x1bX\n\x80"

        # Send scan start command
        self.ep_out.write(cmd, timeout=5000)

        # Allow mechanical movement initialization
        time.sleep(0.5)

        # Read response data stream
        is_color = mode.lower() in ("color", "rgb", "truecolor")
        is_gray = mode.lower() in ("gray", "grayscale", "gray256")
        is_bw = not (is_color or is_gray)

        jpeg_buffer = io.BytesIO() if is_color else None
        pixel_rows = [] if not is_color else None

        line_width_pixels = int(resolution * 8.27)
        bytes_per_line = (line_width_pixels + 7) // 8 if is_bw else line_width_pixels

        stream_ended = False
        empty_reads = 0
        read_buf = bytearray()

        while not stream_ended:
            try:
                data = self.ep_in.read(32768, timeout=6000)
                if not data:
                    empty_reads += 1
                    if empty_reads > 5:
                        break
                    continue
                empty_reads = 0
                read_buf.extend(data)
            except usb.core.USBError as e:
                # Timeout may signify scan end
                if "timed out" in str(e).lower():
                    if len(read_buf) == 0:
                        break
                else:
                    raise

            # Parse brscan4 frames from read_buf
            idx = 0
            while idx < len(read_buf):
                header = read_buf[idx]

                # Status / boundary byte
                if header == 0x80 or header > 0xC1:
                    idx += 1
                    if header == 0x80:
                        stream_ended = True
                        break
                    elif header == 0x82: # ADF empty / paper end
                        stream_ended = True
                        break
                    continue

                # Data frame: 0x81..0xC1
                # Format: [header][wrapper_len:2 LE][wrapper:wrapper_len][payload_len:2 LE][payload:payload_len]
                if idx + 3 > len(read_buf):
                    break

                wrapper_len = read_buf[idx + 1] | (read_buf[idx + 2] << 8)
                payload_hdr_offset = idx + 3 + wrapper_len
                if payload_hdr_offset + 2 > len(read_buf):
                    break

                payload_len = read_buf[payload_hdr_offset] | (read_buf[payload_hdr_offset + 1] << 8)
                payload_offset = payload_hdr_offset + 2
                total_record_len = payload_offset + payload_len - idx

                if idx + total_record_len > len(read_buf):
                    # Incomplete record in buffer, wait for more USB data
                    break

                payload = bytes(read_buf[payload_offset : payload_offset + payload_len])
                idx += total_record_len

                if is_color:
                    # Color mode: JPEG stream chunk
                    jpeg_buffer.write(payload)
                else:
                    # Mono / Gray mode: PackBits compressed line
                    decomp = decompress_packbits(payload, bytes_per_line)
                    pixel_rows.append(decomp)

            # Keep unparsed residue in buffer
            read_buf = read_buf[idx:]

        # Construct image
        if is_color:
            jpeg_bytes = jpeg_buffer.getvalue()
            if len(jpeg_bytes) < 100:
                return None
            try:
                img = Image.open(io.BytesIO(jpeg_bytes))
                img.load()
                return img
            except Exception as e:
                raise RuntimeError(f"Failed to decode color JPEG scan: {e}")
        else:
            if not pixel_rows:
                return None
            height = len(pixel_rows)
            raw_data = b"".join(pixel_rows)
            if is_gray:
                img = Image.frombytes("L", (line_width_pixels, height), raw_data)
            else:
                img = Image.frombytes("1", (line_width_pixels, height), raw_data)
            return img


def main():
    parser = argparse.ArgumentParser(
        description="Open Source Scanner Driver & CLI for Konica Minolta pagepro 1590MF / 1580MF / bizhub"
    )
    parser.add_argument("--mode", choices=["lineart", "gray", "color"], default="color",
                        help="Scan mode (default: color)")
    parser.add_argument("--resolution", type=int, choices=[100, 150, 200, 300, 600], default=300,
                        help="Scan resolution in DPI (default: 300)")
    parser.add_argument("--source", choices=["flatbed", "adf"], default="flatbed",
                        help="Document source: flatbed or adf (default: flatbed)")
    parser.add_argument("--brightness", type=int, default=50,
                        help="Brightness 0-100 (default: 50)")
    parser.add_argument("--contrast", type=int, default=50,
                        help="Contrast 0-100 (default: 50)")
    parser.add_argument("--output", "-o", default="scan_output.pdf",
                        help="Output file path (.pdf, .png, .jpg) (default: scan_output.pdf)")
    parser.add_argument("--list-devices", action="store_true",
                        help="List connected supported devices")

    args = parser.parse_args()

    if args.list_devices:
        devs = KMScannerDevice.find_devices()
        print(f"Found {len(devs)} supported device(s):")
        for i, d in enumerate(devs):
            print(f"  [{i+1}] {d.info['name']} (USB ID {VENDOR_KM:04x}:{d.dev.idProduct:04x})")
        return

    devs = KMScannerDevice.find_devices()
    if not devs:
        print("ERROR: No Konica Minolta 1590MF / 1580MF / bizhub scanner detected on USB.", file=sys.stderr)
        print("Please check USB connection and permissions (udev rules).", file=sys.stderr)
        sys.exit(1)

    scanner = devs[0]
    print(f"Found scanner: {scanner.info['name']} (USB ID {VENDOR_KM:04x}:{scanner.dev.idProduct:04x})")
    print(f"Connecting to scanner interface...")

    scanner.open()
    try:
        pages = []
        page_num = 1
        print(f"Starting scan: Mode={args.mode}, Resolution={args.resolution} DPI, Source={args.source}...")

        while True:
            print(f"Scanning page {page_num}...")
            img = scanner.scan_page(
                resolution=args.resolution,
                mode=args.mode,
                source=args.source,
                brightness=args.brightness,
                contrast=args.contrast,
                page_num=page_num,
            )

            if img is None:
                if page_num == 1:
                    print("ERROR: No image data returned by scanner.", file=sys.stderr)
                    sys.exit(1)
                else:
                    # ADF has finished all pages
                    break

            pages.append(img)
            print(f"Page {page_num} acquired: {img.width}x{img.height} pixels.")

            if args.source == "flatbed":
                break
            page_num += 1

        # Save output
        out_ext = os.path.splitext(args.output)[1].lower()
        if out_ext == ".pdf":
            # Save multi-page PDF
            first_page = pages[0]
            if len(pages) > 1:
                first_page.save(args.output, save_all=True, append_images=pages[1:], resolution=args.resolution)
            else:
                first_page.save(args.output, resolution=args.resolution)
        elif len(pages) == 1:
            pages[0].save(args.output)
        else:
            base, ext = os.path.splitext(args.output)
            for i, p in enumerate(pages):
                fn = f"{base}_{i+1}{ext}"
                p.save(fn)
                print(f"Saved: {fn}")

        print(f"Successfully saved scan to '{args.output}'!")

    finally:
        scanner.close()


if __name__ == "__main__":
    main()
