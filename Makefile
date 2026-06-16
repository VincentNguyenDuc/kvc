FMT_FILES := $(wildcard src/*/*.c) $(wildcard src/*/*.h) \
             $(wildcard src/*/*.cpp) $(wildcard src/*/*.hpp)

.PHONY: init clean install-hooks
.PHONY: format format-check format-py format-py-check lint-py

help:
	@echo "-----------------------------------------------------------------------"
	@echo "Usage: make [target]"
	@echo "Targets:"
	@echo "  init            | Initialize the project, install dependencies, and install git hooks"
	@echo "  clean           | Remove build artifacts"
	@echo "  format          | Format C/C++ files and Python files"
	@echo "  format-check    | Check formatting of C/C++ files and Python files"
	@echo "  format-py       | Format only Python files"
	@echo "  format-py-check | Check formatting of only Python files"
	@echo "  lint-py         | Lint Python files"
	@echo "-----------------------------------------------------------------------"

init:
	git submodule update --init --recursive
	uv venv
	uv pip install -e "tools/perf-orchestrator[dev]"
	$(MAKE) install-hooks

install-hooks:
	git config core.hooksPath .githooks
	@echo "Git hooks installed (.githooks/pre-commit)"

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
