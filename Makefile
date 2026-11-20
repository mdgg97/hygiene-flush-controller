# Hygiene Flush Controller - build & test
CC      ?= gcc
CFLAGS  ?= -std=c11 -Wall -Wextra -Werror -Wconversion -O2 -g
COVFLAGS = --coverage -O0
BUILD   := build
SRC     := src/flush_ctrl.c

.PHONY: all unit system test bug-demo coverage ml clean

all: $(BUILD)/hfc_sim $(BUILD)/test_unit

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/hfc_sim: $(SRC) sim/main.c src/flush_ctrl.h | $(BUILD)
	$(CC) $(CFLAGS) $(EXTRA) -Isrc $(SRC) sim/main.c -o $@

$(BUILD)/test_unit: $(SRC) tests/unit/test_flush_ctrl.c src/flush_ctrl.h | $(BUILD)
	$(CC) $(CFLAGS) $(EXTRA) -Isrc $(SRC) tests/unit/test_flush_ctrl.c -o $@

unit: $(BUILD)/test_unit
	./$(BUILD)/test_unit

system: $(BUILD)/hfc_sim
	HFC_SIM=$(BUILD)/hfc_sim python3 -m pytest tests/system -q

test: unit system

# Build with a typical timer-overflow bug injected: the tests must FAIL.
bug-demo:
	$(MAKE) clean
	-$(MAKE) unit EXTRA=-DFC_INJECT_BUG_OVERFLOW
	-$(MAKE) system EXTRA=-DFC_INJECT_BUG_OVERFLOW
	$(MAKE) clean

coverage: | $(BUILD)
	$(CC) -std=c11 $(COVFLAGS) -Isrc $(SRC) tests/unit/test_flush_ctrl.c -o $(BUILD)/test_cov
	./$(BUILD)/test_cov > /dev/null
	gcov -b $(BUILD)/test_cov-flush_ctrl.gcda | grep -A4 "File 'src/flush_ctrl.c'"
	mv *.gcov $(BUILD)/

ml:
	python3 ml/generate_telemetry.py --out build/telemetry.csv
	python3 ml/anomaly_detector.py build/telemetry.csv

clean:
	rm -rf $(BUILD) *.gcov
