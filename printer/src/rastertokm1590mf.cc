#include <stdio.h>
#include <signal.h>
#include <unistd.h>
#include <fcntl.h>
#include <algorithm>
#include <functional>
#include <string>
#include <array>
#include <map>
#include <vector>
#include <iostream>

#include "cups_raster.h"
#include "job.h"

#define DRIVER_NAME "rastertokm1590mf"
#define DRIVER_VERSION "1.0.0"

namespace {

cups_raster_t *ras = nullptr;
volatile sig_atomic_t interrupted = 0;

void sigterm_handler(int) {
    interrupted = 1;
}

bool next_line(std::vector<uint8_t> &buf) {
    if (interrupted || !ras) {
        return false;
    }
    return cupsRasterReadPixels(ras, buf.data(), static_cast<unsigned>(buf.size())) == buf.size();
}

bool plain_ascii_string(const char *str) {
    bool result = true;
    for (; result && *str; str++) {
        result = (*str >= 32 && *str <= 126);
    }
    return result;
}

std::string ascii_job_name(const char *job_id, const char *job_user, const char *job_name) {
    std::array<const char *, 3> parts = {{ job_id, job_user, job_name }};
    std::string result;
    for (const char *part : parts) {
        if (*part && plain_ascii_string(part)) {
            if (!result.empty()) {
                result += '/';
            }
            result += part;
        }
    }
    if (result.empty()) {
        result = "km1590mf";
    }
    const size_t max_size = 79;
    if (result.size() > max_size) {
        result.resize(max_size);
    }
    return result;
}

page_params build_page_params(const cups_page_header2_t &header) {
    static const std::array<std::string, 6> sources = {{
        "AUTO", "T1", "T2", "T3", "MP", "MANUAL"
    }};

    static const std::array<std::string, 9> media_types = {{
        "REGULAR", "THIN", "THICK", "THICK2", "BOND", "TRANSPARENCY",
        "ENVELOPES", "ENVTHICK", "ENVTHIN"
    }};

    static const std::map<std::string, std::string> sizes = {
        {"A4", "A4"},
        {"A5", "A5"},
        {"A6", "A6"},
        {"B5", "B5"},
        {"B6", "B6"},
        {"EnvC5", "C5"},
        {"EnvMonarch", "MONARCH"},
        {"EnvDL", "DL"},
        {"Executive", "EXECUTIVE"},
        {"Legal", "LEGAL"},
        {"Letter", "LETTER"},
        {"Env10", "COM10"},
        {"Postcard", "POSTCARD"}
    };

    page_params p;
    p.resolution = header.HWResolution[0];
    p.economode = (header.cupsInteger[10] != 0);
    p.duplex = (header.Duplex != 0);

    if (header.MediaPosition < sources.size()) {
        p.sourcetray = sources[header.MediaPosition];
    }
    if (header.cupsMediaType < media_types.size()) {
        p.mediatype = media_types[header.cupsMediaType];
    }

    auto size_it = sizes.find(header.cupsPageSizeName);
    if (size_it != sizes.end()) {
        p.papersize = size_it->second;
    } else {
        p.papersize = "A4";
    }

    return p;
}

} // namespace

int main(int argc, char *argv[]) {
    signal(SIGTERM, sigterm_handler);

    fprintf(stderr, "INFO: %s version %s (Konica Minolta PagePro 1590MF Series Open Source Driver)\n",
            DRIVER_NAME, DRIVER_VERSION);

    if (argc < 6 || argc > 7) {
        fprintf(stderr, "ERROR: %s job-id user title copies options [file]\n", DRIVER_NAME);
        fprintf(stderr, "INFO: This program is a CUPS raster filter.\n");
        return 1;
    }

    int fd = 0; // stdin
    if (argc == 7) {
        fd = open(argv[6], O_RDONLY);
        if (fd < 0) {
            fprintf(stderr, "ERROR: %s: Unable to open raster input file '%s'\n", DRIVER_NAME, argv[6]);
            return 1;
        }
    }

    job print_job(stdout, ascii_job_name(argv[1], argv[2], argv[3]));

    ras = cupsRasterOpen(fd, CUPS_RASTER_READ);
    if (!ras) {
        fprintf(stderr, "ERROR: %s: Cannot open raster stream from CUPS\n", DRIVER_NAME);
        if (fd != 0) close(fd);
        return 1;
    }

    cups_page_header2_t header;
    while (!interrupted && cupsRasterReadHeader2(ras, &header)) {
        if (header.cupsBitsPerPixel != 1 ||
            header.cupsBitsPerColor != 1 ||
            header.cupsNumColors != 1 ||
            header.cupsBytesPerLine > 20000) {
            fprintf(stderr, "ERROR: %s: Page %d: Unsupported raster data (bpp=%u, colors=%u, bpl=%u). Expected 1-bit mono raster.\n",
                    DRIVER_NAME, print_job.pages() + 1,
                    header.cupsBitsPerPixel, header.cupsNumColors, header.cupsBytesPerLine);
            cupsRasterClose(ras);
            if (fd != 0) close(fd);
            return 1;
        }

        page_params params = build_page_params(header);
        print_job.encode_page(params,
                              header.cupsHeight,
                              header.cupsBytesPerLine,
                              next_line);

        fprintf(stderr, "PAGE: %d %u\n", print_job.pages(), header.NumCopies);
    }

    cupsRasterClose(ras);
    if (fd != 0) close(fd);

    if (print_job.pages() == 0) {
        fprintf(stderr, "WARNING: %s: No pages were found in input.\n", DRIVER_NAME);
    } else {
        fprintf(stderr, "INFO: %s: Successfully processed %d page(s).\n", DRIVER_NAME, print_job.pages());
    }

    return 0;
}
