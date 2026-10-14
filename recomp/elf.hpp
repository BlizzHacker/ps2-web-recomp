#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <utility>
#include <vector>

namespace recomp {

struct Segment {
    std::uint32_t address{};
    std::vector<std::uint8_t> bytes;
    bool executable{};
};

class Image {
public:
    static Image load(const std::string &path);
    static Image raw(std::uint32_t address, std::vector<std::uint8_t> bytes, std::pair<std::uint32_t, std::uint32_t> text);

    std::uint32_t entry() const { return entry_; }
    const std::vector<Segment> &segments() const { return segments_; }
    const std::map<std::uint32_t, std::string> &symbols() const { return symbols_; }
    std::pair<std::uint32_t, std::uint32_t> text() const { return text_; }

    // Adds a raw executable segment at a physical EE address (used to overlay
    // RAM regions recovered at run time, e.g. self-decompressing executables).
    void add_raw(std::uint32_t address, std::vector<std::uint8_t> bytes) {
        segments_.push_back(Segment{address, std::move(bytes), true});
    }

    std::optional<std::uint32_t> word(std::uint32_t address) const;
    bool executable(std::uint32_t address) const;
    void add_symbol(std::uint32_t address, std::string name) { symbols_[address] = std::move(name); }

private:
    std::uint32_t entry_{};
    std::vector<Segment> segments_;
    std::map<std::uint32_t, std::string> symbols_;
    std::pair<std::uint32_t, std::uint32_t> text_{};
};

}
