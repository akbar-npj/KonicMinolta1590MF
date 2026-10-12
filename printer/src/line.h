#ifndef _KM1590MF_LINE_H_
#define _KM1590MF_LINE_H_

#include <cstdint>
#include <vector>

std::vector<uint8_t> encode_line(const std::vector<uint8_t> &line);
std::vector<uint8_t> encode_line(const std::vector<uint8_t> &line,
                                const std::vector<uint8_t> &reference);

#endif // _KM1590MF_LINE_H_
