#ifndef _KM1590MF_CUPS_RASTER_H_
#define _KM1590MF_CUPS_RASTER_H_

#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum cups_bool_e {
    CUPS_FALSE = 0,
    CUPS_TRUE = 1
} cups_bool_t;

typedef enum cups_adv_e {
    CUPS_ADVANCE_NONE = 0,
    CUPS_ADVANCE_FILE = 1,
    CUPS_ADVANCE_JOB = 2,
    CUPS_ADVANCE_SET = 3,
    CUPS_ADVANCE_PAGE = 4
} cups_adv_t;

typedef enum cups_cut_e {
    CUPS_CUT_NONE = 0,
    CUPS_CUT_FILE = 1,
    CUPS_CUT_JOB = 2,
    CUPS_CUT_SET = 3,
    CUPS_CUT_PAGE = 4
} cups_cut_t;

typedef enum cups_jog_e {
    CUPS_JOG_NONE = 0,
    CUPS_JOG_FILE = 1,
    CUPS_JOG_JOB = 2,
    CUPS_JOG_SET = 3
} cups_jog_t;

typedef enum cups_edge_e {
    CUPS_EDGE_TOP = 0,
    CUPS_EDGE_RIGHT = 1,
    CUPS_EDGE_BOTTOM = 2,
    CUPS_EDGE_LEFT = 3
} cups_edge_t;

typedef enum cups_order_e {
    CUPS_ORDER_CHUNKED = 0,
    CUPS_ORDER_BANDED = 1,
    CUPS_ORDER_PLANAR = 2
} cups_order_t;

typedef enum cups_orient_e {
    CUPS_ORIENT_0 = 0,
    CUPS_ORIENT_90 = 1,
    CUPS_ORIENT_180 = 2,
    CUPS_ORIENT_270 = 3
} cups_orient_t;

typedef enum cups_cspace_e {
    CUPS_CSPACE_W = 0,
    CUPS_CSPACE_RGB = 1,
    CUPS_CSPACE_RGBA = 2,
    CUPS_CSPACE_K = 3,
    CUPS_CSPACE_CMY = 4,
    CUPS_CSPACE_YMC = 5,
    CUPS_CSPACE_CMYK = 6
} cups_cspace_t;

typedef struct cups_page_header2_s {
    char MediaClass[64];
    char MediaColor[64];
    char MediaType[64];
    char OutputType[64];
    unsigned AdvanceDistance;
    cups_adv_t AdvanceMedia;
    cups_bool_t Collate;
    cups_cut_t CutMedia;
    cups_bool_t Duplex;
    unsigned HWResolution[2];
    unsigned ImagingBoundingBox[4];
    cups_bool_t InsertSheet;
    cups_jog_t Jog;
    cups_edge_t LeadingEdge;
    unsigned Margins[2];
    cups_bool_t ManualFeed;
    unsigned MediaPosition;
    unsigned MediaWeight;
    cups_bool_t MirrorPrint;
    cups_bool_t NegativePrint;
    unsigned NumCopies;
    cups_orient_t Orientation;
    cups_bool_t OutputFaceUp;
    unsigned PageSize[2];
    cups_bool_t Separations;
    cups_bool_t TraySwitch;
    cups_bool_t Tumble;
    unsigned cupsWidth;
    unsigned cupsHeight;
    unsigned cupsMediaType;
    unsigned cupsBitsPerColor;
    unsigned cupsBitsPerPixel;
    unsigned cupsBytesPerLine;
    cups_order_t cupsColorOrder;
    cups_cspace_t cupsColorSpace;
    unsigned cupsCompression;
    unsigned cupsRowCount;
    unsigned cupsRowFeed;
    unsigned cupsRowStep;
    unsigned cupsNumColors;
    float cupsBorderlessScalingFactor;
    float cupsPageSize[2];
    float cupsImagingBBox[4];
    unsigned cupsInteger[16];
    float cupsReal[16];
    char cupsString[16][64];
    char cupsMarkerType[64];
    char cupsRenderingIntent[64];
    char cupsPageSizeName[64];
} cups_page_header2_t;

typedef struct _cups_raster_s cups_raster_t;

typedef enum cups_raster_mode_e {
    CUPS_RASTER_READ = 0,
    CUPS_RASTER_WRITE = 1,
    CUPS_RASTER_WRITE_COMPRESSED = 2,
    CUPS_RASTER_WRITE_PWG = 3
} cups_raster_mode_t;

cups_raster_t *cupsRasterOpen(int fd, cups_raster_mode_t mode);
void cupsRasterClose(cups_raster_t *r);
unsigned cupsRasterReadHeader2(cups_raster_t *r, cups_page_header2_t *h);
unsigned cupsRasterReadPixels(cups_raster_t *r, unsigned char *p, unsigned len);

#ifdef __cplusplus
}
#endif

#endif // _KM1590MF_CUPS_RASTER_H_
