#!/usr/bin/env python3
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scanner")))
from km1590_scan import decompress_packbits, KMScannerDevice

def test_packbits():
    print("Test 1: PackBits Decompression...")
    # Reference data: run of 128 + 16 of 0xFF
    # 0x81 (run 128), 0xFF -> 128 times 0xFF
    ref_run = bytes([0x81, 0xFF, 0x81, 0xFF, 0x81, 0xFF, 0xF1, 0xFF])
    decomp = decompress_packbits(ref_run, 400)
    assert len(decomp) == 400, f"Expected 400 bytes, got {len(decomp)}"
    assert all(b == 0xFF for b in decomp), "Expected all 0xFF bytes"

    # Test literal run: 0x03, 1, 2, 3, 4 -> 4 literal bytes
    lit_run = bytes([0x03, 0x10, 0x20, 0x30, 0x40])
    decomp_lit = decompress_packbits(lit_run, 4)
    assert decomp_lit == bytes([0x10, 0x20, 0x30, 0x40]), f"Got {decomp_lit}"
    print("Test 1 Passed: PackBits decompression verified.")

def test_command_generation():
    print("Test 2: Scanner Command Generation...")
    dev = KMScannerDevice()
    cmd = dev.build_scan_command(resolution=300, mode="color", source="flatbed", brightness=50, contrast=50)
    assert cmd.startswith(b"\x1bX\n"), "Command must start with ESC X"
    assert b"R=300,300\n" in cmd, "Resolution must be in command"
    assert b"M=CGRAY\n" in cmd, "Color mode must be CGRAY"
    assert b"D=SIN\n" in cmd, "Flatbed must use simplex"
    assert cmd.endswith(b"\x80"), "Command must end with 0x80"

    # Test ADF B&W command
    cmd_adf = dev.build_scan_command(resolution=600, mode="lineart", source="adf", brightness=60, contrast=40)
    assert b"R=600,600\n" in cmd_adf
    assert b"M=TEXT\n" in cmd_adf
    assert b"C=RLENGTH\n" in cmd_adf
    assert b"D=ADF\n" in cmd_adf
    print("Test 2 Passed: Scan command strings verified.")

if __name__ == "__main__":
    test_packbits()
    test_command_generation()
    print("ALL SCANNER TESTS PASSED!")
