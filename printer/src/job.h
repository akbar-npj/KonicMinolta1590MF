#ifndef _KM1590MF_JOB_H_
#define _KM1590MF_JOB_H_

#include <stdio.h>
#include <string>
#include <vector>
#include <functional>
#include <cstdint>

struct page_params {
    int resolution = 600;
    std::string papersize = "A4";
    std::string sourcetray = "AUTO";
    std::string mediatype = "REGULAR";
    bool economode = false;
    bool duplex = false;
    int num_copies = 1;

    bool operator==(const page_params &o) const {
        return resolution == o.resolution &&
               papersize == o.papersize &&
               sourcetray == o.sourcetray &&
               mediatype == o.mediatype &&
               economode == o.economode &&
               duplex == o.duplex &&
               num_copies == o.num_copies;
    }
};

class job {
public:
    using nextline_fn = std::function<bool(std::vector<uint8_t>&)>;

    job(FILE *out, const std::string &job_name);
    ~job();

    void encode_page(const page_params &params,
                     int lines,
                     int linesize,
                     nextline_fn nextline);

    int pages() const { return pages_; }

private:
    void begin_job();
    void end_job();
    void write_page_header();

    FILE *out_;
    std::string job_name_;
    page_params page_params_;
    int pages_;
};

#endif // _KM1590MF_JOB_H_
