CC  ?= cc
CXX ?= c++
CFLAGS   ?= -O2 -Wall -Wextra -Wpedantic
CXXFLAGS ?= -O2 -Wall -Wextra -Wpedantic -std=c++17
LDFLAGS  ?=

VERSION ?= v1_baseline

SRC_C   := $(wildcard src/$(VERSION)/*.c)
SRC_CXX := $(wildcard src/$(VERSION)/*.cpp)
HDR     := $(wildcard src/$(VERSION)/*.h) $(wildcard src/$(VERSION)/*.hpp)
FMT_FILES := $(wildcard src/*/*.c) $(wildcard src/*/*.h) \
             $(wildcard src/*/*.cpp) $(wildcard src/*/*.hpp)
BUILD_DIR := build
OBJ_C   := $(patsubst src/$(VERSION)/%.c,$(BUILD_DIR)/$(VERSION)/%.o,$(SRC_C))
OBJ_CXX := $(patsubst src/$(VERSION)/%.cpp,$(BUILD_DIR)/$(VERSION)/%.o,$(SRC_CXX))
OBJ     := $(OBJ_C) $(OBJ_CXX)
BIN     := $(BUILD_DIR)/$(VERSION)/kvc.o
PROFILE_CFLAGS   := -O2 -g -fno-omit-frame-pointer -Wall -Wextra -Wpedantic
PROFILE_CXXFLAGS := -O2 -g -fno-omit-frame-pointer -Wall -Wextra -Wpedantic -std=c++17

LINKER  := $(if $(SRC_CXX),$(CXX),$(CC))

.PHONY: all clean run
.PHONY: format format-check format-py format-py-check lint-py
.PHONY: profile-build

all: $(BIN)

$(BIN): $(OBJ)
	$(LINKER) $(OBJ) -o $@ $(LDFLAGS)

$(BUILD_DIR)/$(VERSION):
	mkdir -p $@

$(BUILD_DIR)/$(VERSION)/%.o: src/$(VERSION)/%.c | $(BUILD_DIR)/$(VERSION)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD_DIR)/$(VERSION)/%.o: src/$(VERSION)/%.cpp | $(BUILD_DIR)/$(VERSION)
	$(CXX) $(CXXFLAGS) -c $< -o $@

init:
	git submodule update --init --recursive
	uv venv
	uv pip install -e "tools/perf-orchestrator[dev]"

run: $(BIN)
	./$(BIN)

profile-build:
	$(MAKE) clean
	$(MAKE) VERSION=$(VERSION) CFLAGS='$(PROFILE_CFLAGS)' CXXFLAGS='$(PROFILE_CXXFLAGS)'

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
