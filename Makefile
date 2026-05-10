CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -Wpedantic
LDFLAGS ?=

SRC := $(wildcard src/*.c)
HDR := $(wildcard src/*.h)
FMT_FILES := $(SRC) $(HDR)
OBJ := $(SRC:.c=.o)
BIN := kvc

.PHONY: all clean run
.PHONY: docker-build docker-dev docker-run docker-stop
.PHONY: format format-check

all: $(BIN)

$(BIN): $(OBJ)
	$(CC) $(OBJ) -o $@ $(LDFLAGS)

src/%.o: src/%.c
	$(CC) $(CFLAGS) -c $< -o $@

run: $(BIN)
	./$(BIN)

clean:
	rm -f $(OBJ) $(BIN)

docker-build:
	docker compose build

docker-dev:
	docker compose run --rm kvc-dev

docker-run:
	docker compose up --build kvc-run

docker-stop:
	docker compose down

format:
	clang-format -i $(FMT_FILES)

format-check:
	clang-format --dry-run --Werror $(FMT_FILES)
