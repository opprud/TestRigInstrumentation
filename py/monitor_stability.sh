#!/bin/bash
# Monitor the stability test progress

LOG_FILE="stability_test_v2.log"

echo "Monitoring stability test..."
echo "Press Ctrl+C to stop monitoring (test will continue running)"
echo "========================================"

while true; do
    if [ -f "$LOG_FILE" ]; then
        # Count completed sweeps
        SWEEPS=$(grep -c "Sweep.*/" "$LOG_FILE" 2>/dev/null || echo "0")

        # Get last sweep line
        LAST_SWEEP=$(tail -10 "$LOG_FILE" 2>/dev/null | grep "Sweep" | tail -1)

        # Check for errors
        ERRORS=$(grep -c "Error\|Traceback" "$LOG_FILE" 2>/dev/null || echo "0")

        clear
        echo "=== Stability Test Monitor ==="
        echo "Time: $(date '+%H:%M:%S')"
        echo "Sweeps completed: $SWEEPS / 100"
        echo "Last sweep: $LAST_SWEEP"
        echo "Errors detected: $ERRORS"
        echo ""
        echo "Last 5 lines:"
        tail -5 "$LOG_FILE" 2>/dev/null || echo "(no output yet)"

        if [ "$ERRORS" -gt "0" ]; then
            echo ""
            echo "⚠️  ERRORS DETECTED - Check $LOG_FILE for details"
        fi
    else
        echo "Waiting for log file to be created..."
    fi

    sleep 5
done
