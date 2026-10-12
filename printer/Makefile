CXX ?= g++
CXXFLAGS ?= -std=c++11 -O2 -Wall -Wextra

# Include local cups_raster.h
INCLUDES = -Isrc

# Link with libcups: check /usr/lib64/libcups.so.2 or fallback to -lcups
LIB_CUPS = $(shell if [ -f /usr/lib64/libcups.so.2 ]; then echo /usr/lib64/libcups.so.2; else echo -lcups; fi)

TARGET = rastertokm1590mf
SRCS = src/rastertokm1590mf.cc src/job.cc src/line.cc
OBJS = $(SRCS:.cc=.o)

all: $(TARGET)

$(TARGET): $(OBJS)
	$(CXX) $(CXXFLAGS) -o $@ $(OBJS) $(LIB_CUPS)

src/%.o: src/%.cc
	$(CXX) $(CXXFLAGS) $(INCLUDES) -c $< -o $@

clean:
	rm -f $(OBJS) $(TARGET)

.PHONY: all clean
