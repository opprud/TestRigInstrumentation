#!/bin/bash
# Run each sensor test config one by one.
# Usage:
#   ./run_sensor_tests.sh                           # scan & pick device interactively
#   ./run_sensor_tests.sh -a AA:BB:CC:DD:EE         # connect by address
#   ./run_sensor_tests.sh -d OE00031204100048       # connect by name/serial

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"
SAMPLER="${SCRIPT_DIR}/run_sampler.py"
CONFIG_DIR="${SCRIPT_DIR}/test_configs"

# Pass through any extra args (e.g. -a ADDRESS, -d DEVICE, -v)
EXTRA_ARGS="$@"

CONFIGS=(
    "00_battery.json"
    "01_temp_amb.json"
    "02_temp_mch.json"
    "03_mic_amb.json"
    "04_mic_mch.json"
    "05_adxl1002.json"
    "06_adxl362_x.json"
    "07_adxl362_y.json"
    "08_adxl362_z.json"
    "09_ism330_acc_x.json"
    "10_ism330_acc_y.json"
    "11_ism330_acc_z.json"
    "12_ism330_gyro_x.json"
    "13_ism330_gyro_y.json"
    "14_ism330_gyro_z.json"
    "15_mmc5603_x.json"
    "16_mmc5603_y.json"
    "17_mmc5603_z.json"
    "18_drv425.json"
)

TOTAL=${#CONFIGS[@]}
PASSED=0
FAILED=0
FAILED_LIST=()

for i in "${!CONFIGS[@]}"; do
    cfg="${CONFIGS[$i]}"
    num=$((i + 1))
    echo ""
    echo "========================================"
    echo "[$num/$TOTAL] Testing: $cfg"
    echo "========================================"

    if $PYTHON "$SAMPLER" --config "${CONFIG_DIR}/${cfg}" --no-sleep $EXTRA_ARGS; then
        echo "PASS: $cfg"
        PASSED=$((PASSED + 1))
    else
        echo "FAIL: $cfg"
        FAILED=$((FAILED + 1))
        FAILED_LIST+=("$cfg")
    fi
done

echo ""
echo "========================================"
echo "Results: $PASSED/$TOTAL passed, $FAILED failed"
if [ $FAILED -gt 0 ]; then
    echo "Failed:"
    for f in "${FAILED_LIST[@]}"; do
        echo "  - $f"
    done
fi
echo "========================================"
