SHELL := /bin/sh
.DEFAULT_GOAL := help

ROOT_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
FIRMWARE_DIR := $(ROOT_DIR)/firmware/esp32
APP_DIR := $(ROOT_DIR)/app/public

PIO_ENV ?= sweetyaar
APP_PORT ?= 8000
SERIAL_PORT ?=

# In an ordinary checkout the venv is at ROOT_DIR/.venv. The second candidate
# lets the same commands work from repository worktrees created under
# .worktrees/ without duplicating the environment.
VENV_DIR ?= $(or $(firstword $(wildcard $(ROOT_DIR)/.venv $(ROOT_DIR)/../../.venv)),$(ROOT_DIR)/.venv)
PYTHON ?= $(VENV_DIR)/bin/python
PIO ?= $(VENV_DIR)/bin/pio
UV ?= uv

.PHONY: help setup app build flash monitor flash-monitor clean test test-app test-firmware check-python check-pio

help: ## Show the available project commands.
	@printf 'SweetYaar project commands\n\n'
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nOverrides: APP_PORT=8000 PIO_ENV=sweetyaar SERIAL_PORT=/dev/cu...\n'

setup: ## Create or refresh the root Python/PlatformIO environment with uv.
	$(UV) sync

app: check-python ## Serve the parent web app locally (override APP_PORT as needed).
	@printf 'Serving SweetYaar at http://localhost:%s/ (Ctrl-C to stop)\n' '$(APP_PORT)'
	"$(PYTHON)" -m http.server --directory "$(APP_DIR)" "$(APP_PORT)"

build: check-pio ## Build the ESP32 firmware.
	cd "$(FIRMWARE_DIR)" && "$(PIO)" run -e "$(PIO_ENV)"

flash: check-pio ## Build and upload firmware to the connected ESP32.
	cd "$(FIRMWARE_DIR)" && "$(PIO)" run -e "$(PIO_ENV)" -t upload $(if $(SERIAL_PORT),--upload-port "$(SERIAL_PORT)",)

monitor: check-pio ## Open the ESP32 serial monitor.
	cd "$(FIRMWARE_DIR)" && "$(PIO)" device monitor -e "$(PIO_ENV)" $(if $(SERIAL_PORT),--port "$(SERIAL_PORT)",)

flash-monitor: ## Flash firmware and then open the serial monitor.
	$(MAKE) flash
	$(MAKE) monitor

clean: check-pio ## Remove generated PlatformIO build output.
	cd "$(FIRMWARE_DIR)" && "$(PIO)" run -e "$(PIO_ENV)" -t clean

test: check-python ## Run the complete pytest suite.
	cd "$(ROOT_DIR)" && "$(PYTHON)" -m pytest

test-app: check-python ## Run the parent-app and PWA regression tests.
	cd "$(ROOT_DIR)" && "$(PYTHON)" -m pytest tests/test_parent_app.py tests/test_parent_app_pwa.py

test-firmware: check-python ## Run firmware configuration, native-code, and build tests.
	cd "$(ROOT_DIR)" && "$(PYTHON)" -m pytest tests/test_firmware_config.py tests/test_state_machine.py tests/test_firmware_build.py

check-python:
	@test -x "$(PYTHON)" || { printf 'Python environment not found at %s. Run make setup first.\n' '$(PYTHON)' >&2; exit 1; }

check-pio:
	@test -x "$(PIO)" || { printf 'PlatformIO not found at %s. Run make setup first.\n' '$(PIO)' >&2; exit 1; }
