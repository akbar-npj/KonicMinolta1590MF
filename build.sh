#!/usr/bin/env bash
# ==============================================================================
# build.sh - Build, Test, and Install Automation for Konica Minolta 1590MF Suite
#
# Supports:
#   pagepro 1590MF, pagepro 1580MF, bizhub 15, bizhub 16
# Compatible with:
#   Linux x86_64, aarch64 (ARM 64-bit), armhf, riscv64
# ==============================================================================

set -e

# Color definitions
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DO_INSTALL=0
DO_CLEAN=0
ONLY_TEST=0

show_help() {
    cat << EOF
Usage: ./build.sh [OPTIONS]

Options:
  --install, install    Build, run tests, and install driver to the system
  --test, test          Run unit tests only
  --clean, clean        Remove compiled binaries and generated PPDs
  -h, --help            Show this help message

Examples:
  ./build.sh            Build raster filter and compile PPDs
  sudo ./build.sh install
                        Build everything and install to CUPS & SANE
  ./build.sh --test     Run test suite
EOF
}

# Parse command line arguments
for arg in "$@"; do
    case "$arg" in
        --install|install)
            DO_INSTALL=1
            ;;
        --clean|clean)
            DO_CLEAN=1
            ;;
        --test|test)
            ONLY_TEST=1
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $arg${NC}"
            show_help
            exit 1
            ;;
    esac
done

if [ "$DO_CLEAN" -eq 1 ]; then
    echo -e "${YELLOW}==> Cleaning build artifacts...${NC}"
    make -C "$SCRIPT_DIR/printer" clean >/dev/null 2>&1 || true
    rm -f "$SCRIPT_DIR/tests/test_raster_encoder"
    rm -rf "$SCRIPT_DIR/scanner/__pycache__" "$SCRIPT_DIR/tests/__pycache__"
    echo -e "${GREEN}==> Clean complete.${NC}"
    exit 0
fi

echo -e "${BLUE}======================================================================${NC}"
echo -e "${CYAN}Konica Minolta pagepro 1590MF Series - Driver Build & Automation${NC}"
echo -e "${BLUE}======================================================================${NC}"
echo -e "Target Architecture: ${GREEN}$(uname -m)${NC}"
echo -e "Operating System:    ${GREEN}$(uname -s)${NC}"
echo ""

# 1. Dependency Checks
echo -e "${YELLOW}[1/4] Checking prerequisites and development tools...${NC}"

check_cmd() {
    local cmd="$1"
    local pkg_hint="$2"
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo -e "${RED}ERROR: Missing command '$cmd'.${NC}"
        echo -e "Please install it via your package manager ($pkg_hint)."
        exit 1
    fi
}

check_cmd "make" "make"
if ! command -v g++ >/dev/null 2>&1 && ! command -v clang++ >/dev/null 2>&1; then
    echo -e "${RED}ERROR: No C++ compiler found (g++ or clang++).${NC}"
    echo -e "Fedora/RHEL: sudo dnf install gcc-c++"
    echo -e "Debian/Ubuntu: sudo apt install g++"
    exit 1
fi
check_cmd "python3" "python3"
check_cmd "ppdc" "cups (CUPS development tools / ppdc)"

# Check libcups
if [ ! -f /usr/lib64/libcups.so.2 ] && [ ! -f /usr/lib/libcups.so.2 ] && [ ! -f /usr/lib/x86_64-linux-gnu/libcups.so.2 ] && [ ! -f /usr/lib/aarch64-linux-gnu/libcups.so.2 ]; then
    if ! ldconfig -p 2>/dev/null | grep -q "libcups.so"; then
        echo -e "${YELLOW}WARNING: libcups.so.2 not found in standard paths; build will attempt linking against -lcups.${NC}"
    fi
fi

# Check Python USB & Pillow dependencies for scanner
PYTHON_MISSING=0
if ! python3 -c "import usb.core" >/dev/null 2>&1; then
    echo -e "${YELLOW}Notice: 'pyusb' Python module is not yet installed.${NC}"
    echo -e "  Install with: sudo dnf install python3-pyusb  OR  pip install pyusb"
    PYTHON_MISSING=1
fi

if ! python3 -c "import PIL" >/dev/null 2>&1; then
    echo -e "${YELLOW}Notice: 'Pillow' Python module is not yet installed.${NC}"
    echo -e "  Install with: sudo dnf install python3-pillow  OR  pip install Pillow"
    PYTHON_MISSING=1
fi

if [ "$PYTHON_MISSING" -eq 0 ]; then
    echo -e "  ${GREEN}✓${NC} All toolchain and runtime dependencies verified."
else
    echo -e "  ${YELLOW}!${NC} Scanner tool requires python3-pyusb and python3-pillow at runtime."
fi
echo ""

# 2. Compile Native CUPS Raster Filter
if [ "$ONLY_TEST" -eq 0 ]; then
    echo -e "${YELLOW}[2/4] Compiling native CUPS raster filter (rastertokm1590mf)...${NC}"
    cd "$SCRIPT_DIR/printer"
    make clean >/dev/null 2>&1 || true
    make
    echo -e "  ${GREEN}✓${NC} Filter binary successfully built: ${CYAN}$SCRIPT_DIR/printer/rastertokm1590mf${NC}"
    file "$SCRIPT_DIR/printer/rastertokm1590mf"

    # Compile PPDs using ppdc
    echo ""
    echo -e "${YELLOW}[2b/4] Compiling PPD descriptions with ppdc...${NC}"
    mkdir -p "$SCRIPT_DIR/printer/ppd"
    ppdc -d "$SCRIPT_DIR/printer/ppd" "$SCRIPT_DIR/printer/km1590mf.drv"
    echo -e "  ${GREEN}✓${NC} Generated PPD files in ${CYAN}$SCRIPT_DIR/printer/ppd/${NC}:"
    ls -1 "$SCRIPT_DIR/printer/ppd" | sed 's/^/      - /'

    # Validate PPD files if cupstestppd is available
    if command -v cupstestppd >/dev/null 2>&1; then
        echo -e "  Validating generated PPDs with cupstestppd..."
        for p in "$SCRIPT_DIR/printer/ppd"/*.ppd; do
            cupstestppd -I filters -q "$p" && echo -e "    ${GREEN}✓${NC} $(basename "$p"): Valid"
        done
    fi
    echo ""
fi

# 3. Run Test Suite
echo -e "${YELLOW}[3/4] Running test suite...${NC}"
cd "$SCRIPT_DIR"

echo -e "  Running C++ raster encoder tests..."
${CXX:-g++} -std=c++11 -O2 -I"$SCRIPT_DIR/printer/src" \
    "$SCRIPT_DIR/tests/test_raster_encoder.cc" \
    "$SCRIPT_DIR/printer/src/line.cc" \
    -o "$SCRIPT_DIR/tests/test_raster_encoder"
"$SCRIPT_DIR/tests/test_raster_encoder"
echo -e "    ${GREEN}✓${NC} C++ raster tests passed."

echo -e "  Running Python scanner protocol tests..."
python3 "$SCRIPT_DIR/tests/test_scanner_protocol.py"
echo -e "    ${GREEN}✓${NC} Python scanner protocol tests passed."
echo ""

# 4. Installation
if [ "$DO_INSTALL" -eq 1 ]; then
    echo -e "${YELLOW}[4/4] Executing system installation...${NC}"
    if [ "$EUID" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            sudo "$SCRIPT_DIR/install.sh"
        else
            echo -e "${RED}ERROR: Root privileges required for installation.${NC}"
            echo -e "Please run: sudo ./build.sh install"
            exit 1
        fi
    else
        "$SCRIPT_DIR/install.sh"
    fi
else
    echo -e "${YELLOW}[4/4] Build and verification finished successfully!${NC}"
    echo ""
    echo -e "${GREEN}To install the driver to CUPS and SANE, run:${NC}"
    echo -e "  ${CYAN}sudo ./build.sh install${NC}"
    echo ""
    echo -e "${GREEN}To run the standalone scanner CLI directly:${NC}"
    echo -e "  ${CYAN}./scanner/km1590_scan.py --mode color -o scan.pdf${NC}"
fi
echo -e "${BLUE}======================================================================${NC}"
