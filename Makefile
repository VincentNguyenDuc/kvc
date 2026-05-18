CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -Wpedantic
LDFLAGS ?=

VERSION ?= v1_baseline

SRC := $(wildcard src/$(VERSION)/*.c)
HDR := $(wildcard src/$(VERSION)/*.h)
FMT_FILES := $(wildcard src/*/*.c) $(wildcard src/*/*.h)
BUILD_DIR := build
OBJ := $(patsubst src/$(VERSION)/%.c,$(BUILD_DIR)/$(VERSION)/%.o,$(SRC))
BIN := $(BUILD_DIR)/$(VERSION)/kvc.o
PROFILE_CFLAGS := -O2 -g -fno-omit-frame-pointer -Wall -Wextra -Wpedantic

.PHONY: all clean run
.PHONY: format format-check format-py format-py-check lint-py
.PHONY: profile-build
.PHONY: bench-build bench

all: $(BIN)

$(BIN): $(OBJ)
	$(CC) $(OBJ) -o $@ $(LDFLAGS)

$(BUILD_DIR)/$(VERSION):
	mkdir -p $@

$(BUILD_DIR)/$(VERSION)/%.o: src/$(VERSION)/%.c | $(BUILD_DIR)/$(VERSION)
	$(CC) $(CFLAGS) -c $< -o $@

init:
	git submodule update --init --recursive
	uv venv
	uv pip install -e "tools/perf-orchestrator[dev]"

run: $(BIN)
	./$(BIN)

profile-build:
	$(MAKE) clean
	$(MAKE) VERSION=$(VERSION) CFLAGS='$(PROFILE_CFLAGS)'

bench-build:
	docker build --target bench -t kvc-bench .

bench:
	bash bench/run.sh $(BENCH_ARGS)

clean:
	rm -rf $(BUILD_DIR)

format:
	clang-format -i $(FMT_FILES)
	.venv/bin/ruff format bench/

format-check:
	clang-format --dry-run --Werror $(FMT_FILES)
	.venv/bin/ruff format --check bench/

format-py:
	.venv/bin/ruff format bench/

format-py-check:
	.venv/bin/ruff format --check bench/

lint-py:
	.venv/bin/ruff check bench/
