FMT_FILES := $(wildcard src/*/*.c) $(wildcard src/*/*.h) \
             $(wildcard src/*/*.cpp) $(wildcard src/*/*.hpp)

.PHONY: init clean install-hooks
.PHONY: format
.PHONY: docs

help:
	@echo "-----------------------------------------------------------------------"
	@echo "Usage: make [target]"
	@echo "Targets:"
	@echo "  init            | Initialize the project, install dependencies, and install git hooks"
	@echo "  clean           | Remove build artifacts"
	@echo "  format          | Format C/C++ files and Python files"
	@echo "  docs            | Regenerate dashboard data and serve at http://localhost:8000"
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

docs:
	python3 bench/generate_manifest.py
	@echo "Open http://localhost:8000 in your browser (Ctrl-C to stop)"
	python3 -m http.server 8000 --directory docs
