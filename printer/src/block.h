#ifndef _KM1590MF_BLOCK_H_
#define _KM1590MF_BLOCK_H_

#include <assert.h>
#include <stdio.h>
#include <vector>
#include <cstdint>

class block {
public:
    block() : line_bytes_(0) {}

    bool empty() const {
        return line_bytes_ == 0;
    }

    void add_line(std::vector<uint8_t> &&line) {
        assert(!line.empty());
        assert(line_fits(line.size()));
        line_bytes_ += line.size();
        lines_.emplace_back(std::move(line));
    }

    bool line_fits(unsigned size) const {
        return line_bytes_ + size < max_block_size_;
    }

    void flush(FILE *f) {
        if (!empty()) {
            // Format: <byte_count>w\x00<num_lines><data>
            fprintf(f, "%dw%c%c",
                    line_bytes_ + 2, 0,
                    static_cast<int>(lines_.size()));
            for (auto &line : lines_) {
                fwrite(line.data(), 1, line.size(), f);
            }
            line_bytes_ = 0;
            lines_.clear();
        }
    }

private:
    static const unsigned max_block_size_ = 16350;
    std::vector<std::vector<uint8_t>> lines_;
    int line_bytes_;
};

#endif // _KM1590MF_BLOCK_H_
