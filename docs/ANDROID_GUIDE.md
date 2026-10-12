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

## 4. Option 3: Running inside Termux on Android

Android is built on top of the Linux kernel, and the C++ raster filter is 100% standard C++11 with no GUI dependencies. You can run it inside **Termux** (terminal emulator for Android):

1. Install **Termux** from F-Droid.
2. Open Termux and install the compilation toolchain:
   ```bash
   pkg update
   pkg install clang make python git libusb
   ```
3. Clone this repository:
   ```bash
   git clone https://github.com/akbar-npj/KonicMinolta1590MF.git
   cd KonicMinolta1590MF
   ```
4. Build the C++ tests and tools:
   ```bash
   cd tests
   clang++ -std=c++11 -O2 -I../printer/src test_raster_encoder.cc ../printer/src/line.cc -o test_raster
   ./test_raster
   ```
   *Result: `ALL PRINTER ENCODER TESTS PASSED!` on Android ARM64!*

---

## 5. Mobile Scanning from Android

The scanner operates on USB **Interface 1** (`MI_01`).

1. **Via Linux Server**: Run a web scan service (such as `scanserv-js` or a lightweight Flask web UI) on the Linux machine connected to the scanner using `km1590-scan`. You can open the web UI in Chrome on your Android phone and scan directly to PDF/JPEG.
2. **Via Android USB OTG**: An Android app with USB OTG permissions can claim Interface 1 (`MI_01`), send the Brother `\x1bX\n` scan command packet, receive the raw chunks, decompress PackBits / JPEG, and save the scanned image to Android's `MediaStore` or `Downloads` folder!
