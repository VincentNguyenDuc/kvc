FMT_FILES := $(wildcard src/*/*.c) $(wildcard src/*/*.h) \
             $(wildcard src/*/*.cpp) $(wildcard src/*/*.hpp)

.PHONY: init clean
.PHONY: format format-check format-py format-py-check lint-py

init:
	git submodule update --init --recursive
	uv venv
	uv pip install -e "tools/perf-orchestrator[dev]"

clean:
	rm -rf build

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
