#!/bin/bash
# ==============================================================================
# Installer for Konica Minolta pagepro 1590MF / 1580MF / bizhub 15 / bizhub 16
# Open Source Linux Driver (Printer + Scanner + IPP Network Sharing)
# Compatible with x86_64, aarch64 (ARM 64-bit), armhf, and all Linux distros
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "======================================================================"
echo "Konica Minolta pagepro 1590MF Series Open Source Driver Installer"
echo "======================================================================"

# 1. Build Printer Raster Filter
echo ""
echo "[1/5] Building native CUPS raster filter (rastertokm1590mf)..."
cd "$SCRIPT_DIR/printer"
make clean >/dev/null 2>&1 || true
make
echo "  -> rastertokm1590mf built successfully for $(uname -m)."

# 2. Check / Install Filter
echo ""
echo "[2/5] Installing CUPS filter..."
SUDO=""
if [ "$EUID" -ne 0 ]; then
    if command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        echo "Please run as root or install sudo."
        exit 1
    fi
fi

# Detect CUPS filter directory
CUPS_FILTER_DIRS=("/usr/lib/cups/filter" "/usr/libexec/cups/filter")
FILTER_INSTALLED=0

for dir in "${CUPS_FILTER_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        $SUDO cp -f "$SCRIPT_DIR/printer/rastertokm1590mf" "$dir/rastertokm1590mf"
        $SUDO chmod 755 "$dir/rastertokm1590mf"
        $SUDO chown root:root "$dir/rastertokm1590mf" 2>/dev/null || true
        echo "  -> Installed to $dir/rastertokm1590mf"
        FILTER_INSTALLED=1
    fi
done

if [ "$FILTER_INSTALLED" -eq 0 ]; then
    $SUDO mkdir -p /usr/lib/cups/filter
    $SUDO cp -f "$SCRIPT_DIR/printer/rastertokm1590mf" /usr/lib/cups/filter/rastertokm1590mf
    $SUDO chmod 755 /usr/lib/cups/filter/rastertokm1590mf
    echo "  -> Created /usr/lib/cups/filter and installed filter."
fi

# 3. Install PPD Models
echo ""
echo "[3/5] Installing CUPS PPD printer descriptions..."
PPD_DIRS=("/usr/share/cups/model/km" "/usr/share/ppd/km")
for dir in "${PPD_DIRS[@]}"; do
    $SUDO mkdir -p "$dir"
    $SUDO cp -f "$SCRIPT_DIR"/printer/ppd/*.ppd "$dir/"
    $SUDO chmod 644 "$dir"/*.ppd
    echo "  -> Installed PPDs to $dir/"
done

# 4. Install Scanner Driver & udev Rules
echo ""
echo "[4/5] Installing Scanner Driver & USB Permissions..."
$SUDO cp -f "$SCRIPT_DIR/scanner/km1590_scan.py" /usr/local/bin/km1590-scan
$SUDO chmod 755 /usr/local/bin/km1590-scan
echo "  -> Installed CLI scanner to /usr/local/bin/km1590-scan"

if [ -d "/etc/udev/rules.d" ]; then
    $SUDO cp -f "$SCRIPT_DIR/scanner/99-km1590mf.rules" /etc/udev/rules.d/99-km1590mf.rules
    $SUDO udevadm control --reload-rules 2>/dev/null || true
    $SUDO udevadm trigger 2>/dev/null || true
    echo "  -> Installed udev rules to /etc/udev/rules.d/99-km1590mf.rules"
fi

if [ -d "/etc/sane.d" ]; then
    $SUDO cp -f "$SCRIPT_DIR/scanner/km1590mf.conf" /etc/sane.d/km1590mf.conf
    echo "  -> Installed SANE config to /etc/sane.d/km1590mf.conf"
fi

# 5. Printer Queue & IPP Sharing Setup
echo ""
echo "[5/5] Checking connected printers..."
if command -v lpinfo >/dev/null 2>&1; then
    DEVICE_URI=""
    for uri in $(lpinfo -v 2>/dev/null | grep -i -E "1590|1580|bizhub" | awk '{print $2}'); do
        DEVICE_URI="$uri"
        break
    done

    if [ -n "$DEVICE_URI" ]; then
        echo "Found printer at URI: $DEVICE_URI"
        PPD_FILE="/usr/share/cups/model/km/km-pagepro1590mf.ppd"
        $SUDO lpadmin -p "KM_pagepro_1590MF" -E -v "$DEVICE_URI" -P "$PPD_FILE"
        echo "Successfully added printer 'KM_pagepro_1590MF' to CUPS!"
    else
        echo "No printer currently connected via USB. To add a printer manually:"
        echo "  - USB Connection:"
        echo "      sudo lpadmin -p KM_pagepro_1590MF -E -v usb://dev/usb/lp0 -P /usr/share/cups/model/km/km-pagepro1590mf.ppd"
        echo "  - Network IPP (IPP Option 1 / Port 631):"
        echo "      sudo lpadmin -p KM_pagepro_1590MF -E -v ipp://<PRINTER_IP>/ipp/port1 -P /usr/share/cups/model/km/km-pagepro1590mf.ppd"
        echo "  - Network RAW Port 9100:"
        echo "      sudo lpadmin -p KM_pagepro_1590MF -E -v socket://<PRINTER_IP>:9100 -P /usr/share/cups/model/km/km-pagepro1590mf.ppd"
        echo "  - Network LPD/LPR:"
        echo "      sudo lpadmin -p KM_pagepro_1590MF -E -v lpd://<PRINTER_IP>/binary_p1 -P /usr/share/cups/model/km/km-pagepro1590mf.ppd"
    fi
fi

# Enable CUPS IPP Sharing
echo ""
echo "======================================================================"
echo "INSTALLATION COMPLETE!"
echo "======================================================================"
echo ""
echo "Print Driver:"
echo "  Filter:       /usr/lib/cups/filter/rastertokm1590mf"
echo "  PPD Files:    /usr/share/cups/model/km/"
echo "                - km-pagepro1590mf.ppd"
echo "                - km-pagepro1580mf.ppd"
echo "                - km-bizhub16.ppd"
echo "                - km-bizhub15.ppd"
echo ""
echo "Scanner Driver:"
echo "  CLI Utility:  km1590-scan"
echo "  Try scanning: km1590-scan --mode color --output scan.pdf"
echo "                km1590-scan --source adf --mode gray -o document.pdf"
echo ""
echo "IPP / AirPrint Network Sharing:"
echo "  To share this printer across your network via IPP / AirPrint, run:"
echo "    cupsctl --share-printers --remote-any"
echo "    lpadmin -p KM_pagepro_1590MF -o printer-is-shared=true"
echo "======================================================================"
