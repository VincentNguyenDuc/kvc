CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -Wpedantic
LDFLAGS ?=

SRC := $(wildcard src/*.c)
HDR := $(wildcard src/*.h)
FMT_FILES := $(SRC) $(HDR)
BUILD_DIR := build
OBJ := $(patsubst src/%.c,$(BUILD_DIR)/%.o,$(SRC))
BIN := $(BUILD_DIR)/kvc.o
PERF_DIR := perf
PERF_OUT_DIR := $(PERF_DIR)/output/$(shell date +%Y%m%d-%H%M%S)
PERF_DATA := $(PERF_OUT_DIR)/perf.data
PERF_FLAMEGRAPH := $(PERF_OUT_DIR)/flamegraph.svg
PROFILE_CFLAGS := -O2 -g -fno-omit-frame-pointer -Wall -Wextra -Wpedantic

.PHONY: all clean run
.PHONY: format format-check
.PHONY: profile-build perf-check perf-record perf-flamegraph perf-profile

all: $(BIN)

$(BIN): $(OBJ)
	$(CC) $(OBJ) -o $@ $(LDFLAGS)


$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: src/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

run: $(BIN)
	./$(BIN)

profile-build:
	$(MAKE) clean
	$(MAKE) CFLAGS='$(PROFILE_CFLAGS)'

perf-check:
	$(PERF_DIR)/check.sh

perf-record: perf-check $(BIN)
	mkdir -p $(PERF_OUT_DIR)
	$(PERF_DIR)/record.sh $(BIN) $(PERF_OUT_DIR) 8080

perf-flamegraph:
	$(PERF_DIR)/flamegraph.sh $(PERF_DATA) $(PERF_FLAMEGRAPH)

perf-profile: profile-build perf-record perf-flamegraph
	@echo "Profile complete: $(PERF_FLAMEGRAPH)"

clean:
	rm -rf $(BUILD_DIR)

format:
	clang-format -i $(FMT_FILES)

format-check:
	clang-format --dry-run --Werror $(FMT_FILES)
