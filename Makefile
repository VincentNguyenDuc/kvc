CC ?= cc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra -Wpedantic
LDFLAGS ?=

SRC := $(wildcard src/*.c)
HDR := $(wildcard src/*.h)
FMT_FILES := $(SRC) $(HDR)
OBJ := $(SRC:.c=.o)
BIN := kvc.o

.PHONY: all clean run
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

format:
	clang-format -i $(FMT_FILES)

format-check:
	clang-format --dry-run --Werror $(FMT_FILES)
