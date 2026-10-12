# Android Integration Guide: Konica Minolta pagepro 1590MF Series

This guide explains how to use and integrate the **Konica Minolta pagepro 1590MF / 1580MF** and **bizhub 15 / 16** printers and scanners on **Android devices**, utilizing the reverse-engineered source code in this repository.

---

## 1. Overview of Android Printing Options

Because we have full reverse-engineered source code for the printer's raster engine (Brother 1030 compression) and the scanner's USB protocol, there are **three primary ways** to use this printer from Android:

| Method | Setup Effort | Root Needed? | How It Works |
|---|---|---|---|
| **Option 1: Local Network Gateway (Recommended)** | **Zero install on Android** | ❌ No | Share the printer from a Linux PC or Raspberry Pi via CUPS. Android's built-in **Default Print Service (Mopria)** discovers it over Wi-Fi automatically. |
| **Option 2: Native Android Print Plugin (APK)** | Development required | ❌ No | An Android App implementing `android.printservice.PrintService`, compiling our C++ compression engine with the Android NDK, printing over Wi-Fi (Port 9100) or USB OTG. |
| **Option 3: Termux on Android** | 5 minutes | ❌ No | Run our C++ and Python tools directly on Android inside the Termux terminal emulator. |

---

## 2. Option 1: Zero-Install Network Printing (Mopria / AirPrint)

This is the easiest and most practical approach. No apps, drivers, or APKs are needed on any Android device on your network.

### How it works:
1. Modern Android devices (Android 8.0 Oreo and newer) have the **Default Print Service** pre-installed in the OS, which natively supports **Mopria / IPP Everywhere**.
2. When our open-source driver is installed on any Linux computer or Raspberry Pi on your local network:
   ```bash
   # Enable network printer sharing in CUPS
   sudo cupsctl --share-printers --remote-any
   sudo lpadmin -p KM_pagepro_1590MF -o printer-is-shared=true
   ```
3. CUPS broadcasts the printer via mDNS / DNS-SD (Avahi / Bonjour).

### On your Android Phone:
1. Ensure your phone is connected to the same Wi-Fi network.
2. Go to **Settings** → **Connected devices** → **Connection preferences** → **Printing** → **Default Print Service** (make sure it is toggled **ON**).
3. Open any app on Android (Chrome, Google Docs, Gmail, WhatsApp, Photo Gallery).
4. Tap **Share / Menu** → **Print**.
5. Tap the printer dropdown at the top: `KM_pagepro_1590MF` will appear automatically!
6. Select your paper size and tap **Print**. The Linux CUPS server will render the PDF with our native `rastertokm1590mf` engine and feed it to the printer.

---

## 3. Option 2: Building a Native Android Print Service App (No PC Required)

If you want to print **directly from Android without a computer or Raspberry Pi**, you can wrap our C++ raster engine into a native Android Print Service APK.

### Architecture of an Android Print Service
Android provides the **Android Print Framework** (`android.printservice.PrintService`):
```
[Android App (e.g. Chrome)]
         │  (User taps "Print")
         ▼
[Android Print Framework]
         │  (Generates PDF: ParcelFileDescriptor)
         ▼
[Our KM1590 PrintService APK]
         ├── 1. Render PDF pages to Bitmap (android.graphics.pdf.PdfRenderer)
         ├── 2. Brother 1030 Raster Compression (C++ via Android NDK / JNI)
         └── 3. Transmit bytes:
                 ├── Over Wi-Fi: TCP Socket to Port 9100 (RAW) or Port 631 (IPP)
                 └── Over USB OTG: UsbManager bulkTransfer (Interface 0)
```

### Step 1: Declare the Print Service in `AndroidManifest.xml`
```xml
<service
    android:name=".KM1590PrintService"
    android:permission="android.permission.BIND_PRINT_SERVICE">
    <intent-filter>
        <action android:name="android.printservice.PrintService" />
    </intent-filter>
    <meta-data
        android:name="android.printservice"
        android:resource="@xml/printservice" />
</service>
```

### Step 2: Render PDF to Bitmap in Android
Using Android's built-in `PdfRenderer`:
```kotlin
val pfd = printJob.document.data ?: return
val renderer = PdfRenderer(pfd)

for (i in 0 until renderer.pageCount) {
    val page = renderer.openPage(i)
    // 600 DPI rendering (A4: 4960 x 7016 pixels)
    val widthPx = (page.width * 600 / 72)
    val heightPx = (page.height * 600 / 72)
    val bitmap = Bitmap.createBitmap(widthPx, heightPx, Bitmap.Config.ARGB_8888)
    
    page.render(bitmap, null, null, PdfRenderer.Page.RENDER_MODE_FOR_PRINT)
    page.close()
    
    // Pass bitmap to 1030 compression engine
    val compressedPageBytes = compressBitmapTo1030(bitmap)
}
renderer.close()
```

### Step 3: Integrate C++ Compression via Android NDK / JNI
Include our C++ source files in your Android Studio project:
* `printer/src/line.cc`
* `printer/src/job.cc`
* `printer/src/line.h`
* `printer/src/job.h`
* `printer/src/block.h`

In `CMakeLists.txt`:
```cmake
cmake_minimum_required(VERSION 3.18.1)
project("km1590ndk")

add_library(km1590ndk SHARED
    native-lib.cpp
    printer/src/line.cc
    printer/src/job.cc)

find_library(log-lib log)
target_link_libraries(km1590ndk ${log-lib})
```

### Step 4: Transmitting Bytes from Android

#### Over Wi-Fi / Ethernet (Port 9100):
```kotlin
val socket = java.net.Socket(printerIpAddress, 9100)
val outStream = socket.getOutputStream()
outStream.write(pjlAnd1030Bytes)
outStream.flush()
socket.close()
```

#### Over USB OTG Cable (Direct USB Connection):
Using Android's `UsbManager`:
1. Connect the Android device to the printer using a USB OTG adapter.
2. Query the device:
   ```kotlin
   val usbManager = getSystemService(Context.USB_SERVICE) as UsbManager
   val device = usbManager.deviceList.values.firstOrNull { 
       it.vendorId == 0x132B && it.productId == 0x20EA 
   }
   ```
3. Claim **Interface 0** (`USBPRINT`) and write bytes to the Bulk OUT endpoint:
   ```kotlin
   val intf = device.getInterface(0)
   val endpoint = intf.getEndpoint(0) // Bulk OUT
   val connection = usbManager.openDevice(device)
   connection.claimInterface(intf, true)
   connection.bulkTransfer(endpoint, pjlAnd1030Bytes, pjlAnd1030Bytes.size, 10000)
   ```

---

## 4. Option 3: Running inside Termux & Integrating Android Apps

Because Termux runs in userspace on Android, users often ask:
> *"How do standard Android apps (like Chrome, WhatsApp, Gmail, Adobe Reader) actually send documents to Termux to print?"*

Here are the **three seamless integration methods** to connect regular Android apps to Termux:

---

### Workflow A: The Android "Share Sheet" Hook (Recommended & Easiest)
Android allows any app to "Share" files to Termux. Termux has a built-in handler (`~/bin/termux-file-editor`) that runs automatically when a file is shared with it!

#### 1. Setup in Termux (one-time setup):
```bash
# Update and install tools in Termux
pkg update
pkg install python python-pillow poppler git
git clone https://github.com/akbar-npj/KonicMinolta1590MF.git ~/KonicMinolta1590MF

# Create the Termux Share hook
mkdir -p ~/bin
cat << 'EOF' > ~/bin/termux-file-editor
#!/data/data/com.termux/files/usr/bin/bash
# Set your printer's IP address (or leave empty if using USB OTG)
PRINTER_IP="192.168.1.50"
SHARED_FILE="$1"

echo "=== Konica Minolta 1590MF Print ==="
echo "Document: $SHARED_FILE"
python3 ~/KonicMinolta1590MF/printer/km1590_print.py --host "$PRINTER_IP" "$SHARED_FILE"

# Optional: show Android pop-up notification if termux-api is installed
command -v termux-toast >/dev/null && termux-toast "Document printed successfully!"
EOF
chmod +x ~/bin/termux-file-editor
```

#### 2. How you print from ANY Android app:
1. Open any PDF, photo, or document in **Chrome, WhatsApp, Gmail, Google Drive, or Gallery**.
2. Tap the Android **Share** button (or 3-dots menu → Share).
3. Tap **Termux** in the share dialog.
4. Termux immediately executes `km1590_print.py` in the background and sends the document straight to your printer over Wi-Fi! No command typing needed.

---

### Workflow B: Android System "Print" Button (via Local CUPS Daemon)
If you prefer using the official Android **Print** menu option instead of the Share sheet:

1. **Install and start CUPS inside Termux**:
   ```bash
   pkg install cups
   cupsd
   ```
2. **Add the Konica Minolta printer to the local CUPS queue**:
   ```bash
   lpadmin -p KM_pagepro_1590MF -E \
     -v "ipp://192.168.1.50/ipp/port1" \
     -P ~/KonicMinolta1590MF/printer/ppd/km-pagepro1590mf.ppd
   ```
3. **Register Termux CUPS with Android**:
   * On your phone, go to **Settings** → **Printing** → **Default Print Service** → **Add printer**.
   * Enter IP address: `127.0.0.1` (or your phone's Wi-Fi IP address).
   * Android will connect to the local CUPS server running inside Termux!
4. Whenever you tap **Print** from any app, Android submits the print job directly to the Termux CUPS instance on loopback.

---

### Workflow C: Hot-Folder Auto-Print (Background Watcher)
You can set up an automatic folder watcher so any file saved into a specific directory is immediately printed:

1. Grant Termux storage access:
   ```bash
   termux-setup-storage
   mkdir -p ~/storage/shared/Download/Print
   ```
2. Run a background watcher script in Termux:
   ```bash
   cat << 'EOF' > ~/watch_print.sh
   #!/data/data/com.termux/files/usr/bin/bash
   PRINTER_IP="192.168.1.50"
   WATCH_DIR="$HOME/storage/shared/Download/Print"
   mkdir -p "$WATCH_DIR/Done"

   echo "Watching $WATCH_DIR for files to print..."
   while true; do
       for f in "$WATCH_DIR"/*.*; do
           if [ -f "$f" ]; then
               echo "Printing $f..."
               python3 ~/KonicMinolta1590MF/printer/km1590_print.py --host "$PRINTER_IP" "$f"
               mv "$f" "$WATCH_DIR/Done/"
           fi
       done
       sleep 3
   done
   EOF
   chmod +x ~/watch_print.sh
   ```
3. Whenever you download a ticket, invoice, or PDF into the `Download/Print` folder, it prints automatically!

---

### Using `km1590_print.py` via Command Line in Termux
You can also run the standalone print CLI directly:
```bash
# Print a PDF over Wi-Fi
python3 printer/km1590_print.py --host 192.168.1.50 document.pdf

# Print with duplex and toner save
python3 printer/km1590_print.py --host 192.168.1.50 --duplex --economode report.pdf

# Print via USB OTG cable directly plugged into your Android phone
python3 printer/km1590_print.py --usb document.pdf
```

---

## 5. Mobile Scanning from Android

The scanner operates on USB **Interface 1** (`MI_01`).

1. **Via Linux Server**: Run a web scan service (such as `scanserv-js` or a lightweight Flask web UI) on the Linux machine connected to the scanner using `km1590-scan`. You can open the web UI in Chrome on your Android phone and scan directly to PDF/JPEG.
2. **Via Android USB OTG**: An Android app with USB OTG permissions can claim Interface 1 (`MI_01`), send the Brother `\x1bX\n` scan command packet, receive the raw chunks, decompress PackBits / JPEG, and save the scanned image to Android's `MediaStore` or `Downloads` folder!
