#include <iostream>
#include <vector>
#include <cassert>
#include "../printer/src/line.h"
#include "../printer/src/block.h"

int main() {
    std::cout << "Testing Line & Block Encoders..." << std::endl;

    // Test 1: All zero line should produce 1 byte 0xFF
    std::vector<uint8_t> zeros(600, 0);
    auto enc_zeros = encode_line(zeros);
    assert(enc_zeros.size() == 1);
    assert(enc_zeros[0] == 0xFF);
    std::cout << "Test 1 Passed: All-zero line encoded as 0xFF." << std::endl;

    // Test 2: First line with content
    std::vector<uint8_t> line1(600, 0);
    line1[10] = 0xAA;
    line1[11] = 0x55;
    auto enc1 = encode_line(line1);
    assert(enc1.size() > 1);
    assert(enc1[0] == 1); // 1 edit command
    std::cout << "Test 2 Passed: Content line encoded with substitute." << std::endl;

    // Test 3: Difference against reference line
    std::vector<uint8_t> line2 = line1;
    auto enc2 = encode_line(line2, line1);
    assert(enc2.size() == 1); // 0 edits, only edit count byte
    assert(enc2[0] == 0);
    std::cout << "Test 3 Passed: Identical reference produced 0 edits." << std::endl;

    // Test 4: Block buffering
    block blk;
    assert(blk.empty());
    blk.add_line(std::move(enc1));
    assert(!blk.empty());
    std::cout << "Test 4 Passed: Block buffering works." << std::endl;

    std::cout << "ALL PRINTER ENCODER TESTS PASSED!" << std::endl;
    return 0;
}
