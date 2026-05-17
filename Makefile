CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -Wpedantic
LDFLAGS ?=

SRC := $(wildcard src/*.c)
HDR := $(wildcard src/*.h)
FMT_FILES := $(SRC) $(HDR)
BUILD_DIR := build
OBJ := $(patsubst src/%.c,$(BUILD_DIR)/%.o,$(SRC))
BIN := $(BUILD_DIR)/kvc.o
PROFILE_CFLAGS := -O2 -g -fno-omit-frame-pointer -Wall -Wextra -Wpedantic

.PHONY: all clean run
.PHONY: format format-check
.PHONY: format-py format-py-check lint-py
.PHONY: profile-build
.PHONY: bench-build bench

all: $(BIN)

$(BIN): $(OBJ)
	$(CC) $(OBJ) -o $@ $(LDFLAGS)


$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(BUILD_DIR)/%.o: src/%.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@

init:
	git submodule update --init --recursive
	uv venv
	uv pip install -e "tools/perf-orchestrator[dev]"
	uv pip install black ruff

run: $(BIN)
	./$(BIN)

profile-build:
	$(MAKE) clean
	$(MAKE) CFLAGS='$(PROFILE_CFLAGS)'

bench-build:
	docker build --target bench -t kvc-bench .

bench:
	python3 bench/run.py $(BENCH_ARGS)

clean:
	rm -rf $(BUILD_DIR)

format:
	clang-format -i $(FMT_FILES)

format-check:
	clang-format --dry-run --Werror $(FMT_FILES)

format-py:
	.venv/bin/black bench/

format-py-check:
	.venv/bin/black --check bench/

lint-py:
	.venv/bin/ruff check bench/
