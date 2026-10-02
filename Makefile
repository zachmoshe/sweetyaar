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

.PHONY: help setup app build flash monitor flash-monitor clean test test-unit test-device test-app test-firmware check-python check-pio

help: ## Show the available project commands.
	@printf 'SweetYaar project commands\n\n'
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nOverrides: APP_PORT=8000 PIO_ENV=<environment> SERIAL_PORT=/dev/cu...\n'
	@printf '\nGeneric-board examples:\n'
	@printf '  make build PIO_ENV=sweetyaar-generic\n'
	@printf '  make flash PIO_ENV=sweetyaar-generic\n'

setup: ## Create or refresh the root Python/PlatformIO environment with uv.
	$(UV) sync

app: check-python ## Serve the parent web app locally (override APP_PORT as needed).
	@printf 'Serving SweetYaar at http://localhost:%s/ (Ctrl-C to stop)\n' '$(APP_PORT)'
	"$(PYTHON)" -m http.server --directory "$(APP_DIR)" "$(APP_PORT)"

build: check-pio ## Build the ESP32 firmware.
	cd "$(FIRMWARE_DIR)" && "$(PIO)" run -e "$(PIO_ENV)"

flash: check-pio ## Build and upload firmware to the connected ESP32.
	cd "$(FIRMWARE_DIR)" && "$(PIO)" run -e "$(PIO_ENV)" -t upload $(if $(SERIAL_PORT),--upload-port "$(SERIAL_PORT)",)
	@printf '\nAfter flashing: run the BLE deployment checklist in %s/docs/engineering/firmware.md#ble-deployment-checklist\n' '$(ROOT_DIR)'
	@printf 'Check Settings and reconnect without rebooting the toy; recover stale macOS Bluetooth state if characteristics are missing.\n'

monitor: check-pio ## Open the ESP32 serial monitor.
	cd "$(FIRMWARE_DIR)" && "$(PIO)" device monitor -e "$(PIO_ENV)" $(if $(SERIAL_PORT),--port "$(SERIAL_PORT)",)

flash-monitor: ## Flash firmware and then open the serial monitor.
	$(MAKE) flash
	$(MAKE) monitor

clean: check-pio ## Remove generated PlatformIO build output.
	cd "$(FIRMWARE_DIR)" && "$(PIO)" run -e "$(PIO_ENV)" -t clean

test: check-python ## Run the complete pytest suite.
	cd "$(ROOT_DIR)" && "$(PYTHON)" -m pytest

test-unit: check-python ## Run host tests only; never flash or connect to hardware.
	cd "$(ROOT_DIR)" && "$(PYTHON)" -m pytest -m "not firmware"

test-device: check-pio ## Approved device test; requires DEVICE_TEST_APPROVED=1, PIO_ENV and SERIAL_PORT.
	@test "$(DEVICE_TEST_APPROVED)" = 1 || { printf 'Get explicit user approval for this hardware test, then set DEVICE_TEST_APPROVED=1.\n' >&2; exit 1; }
	@test "$(origin PIO_ENV)" = 'command line' -o "$(origin PIO_ENV)" = environment || { printf 'Set PIO_ENV explicitly to match the connected board.\n' >&2; exit 1; }
	@test -n "$(SERIAL_PORT)" || { printf 'Set SERIAL_PORT to the connected toy.\n' >&2; exit 1; }
	"$(PYTHON)" "$(ROOT_DIR)/tools/device_test.py" --approved --pio-env "$(PIO_ENV)" --port "$(SERIAL_PORT)" $(DEVICE_TEST_ARGS)

test-app: check-python ## Run the parent-app and PWA regression tests.
	cd "$(ROOT_DIR)" && "$(PYTHON)" -m pytest tests/test_parent_app.py tests/test_parent_app_pwa.py

test-firmware: check-python ## Run firmware configuration, native-code, and build tests.
	cd "$(ROOT_DIR)" && "$(PYTHON)" -m pytest tests/test_firmware_config.py tests/test_battery_monitor.py tests/test_charger_status.py tests/test_ble_transport.py tests/test_bluetooth_access.py tests/test_state_machine.py tests/test_settings_runtime.py tests/test_firmware_build.py

check-python:
	@test -x "$(PYTHON)" || { printf 'Python environment not found at %s. Run make setup first.\n' '$(PYTHON)' >&2; exit 1; }

check-pio:
	@test -x "$(PIO)" || { printf 'PlatformIO not found at %s. Run make setup first.\n' '$(PIO)' >&2; exit 1; }
