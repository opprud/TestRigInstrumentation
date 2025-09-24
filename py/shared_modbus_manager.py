#!/usr/bin/env python3
"""
Shared Modbus Connection Manager

Manages a single RS485/Modbus connection shared between multiple devices:
- Omron E5CC temperature controller (typically slave ID 2 or 4)
- RS510 VFD controller (typically slave ID 1 or 3)

This prevents conflicts from multiple processes trying to access the same FTDI485 adapter.
"""

import threading
import time
import inspect
from typing import Optional, Dict, Any
from contextlib import contextmanager
from dataclasses import dataclass
from pymodbus.client import ModbusSerialClient


@dataclass
class ModbusConfig:
    """Configuration for the shared Modbus connection."""
    port: str
    baudrate: int = 9600
    parity: str = 'N'
    bytesize: int = 8
    stopbits: int = 1
    timeout: float = 2.0
    debug: bool = False
    max_retries: int = 3
    retry_delay: float = 0.5
    connection_timeout: float = 5.0
    health_check_interval: float = 10.0


class SharedModbusManager:
    """
    Thread-safe shared Modbus connection manager.

    Ensures only one device can communicate at a time while sharing the same
    physical RS485 connection between multiple Modbus slaves.
    """

    def __init__(self, config: ModbusConfig):
        self.config = config
        self.client: Optional[ModbusSerialClient] = None
        self.lock = threading.RLock()  # Reentrant lock for nested calls
        self._is_connected = False
        self._unit_kwarg: Optional[str] = None
        self._connection_count = 0
        self._last_successful_op = time.time()
        self._consecutive_failures = 0

        if config.debug:
            print(f"[DEBUG] SharedModbusManager initialized for {config.port}")

    def _detect_unit_kwarg(self) -> Optional[str]:
        """Detect the correct kwarg for addressing (unit/slave/device_id)."""
        if not self.client:
            return None

        try:
            sig = inspect.signature(self.client.read_holding_registers)
            for key in ("unit", "slave", "device_id"):
                if key in sig.parameters:
                    return key
        except Exception:
            pass
        return None

    def _check_connection_health(self) -> bool:
        """Check if connection needs recovery based on failure patterns."""
        now = time.time()

        # Force reconnect if too many consecutive failures
        if self._consecutive_failures >= self.config.max_retries:
            if self.config.debug:
                print(f"[DEBUG] Too many failures ({self._consecutive_failures}), forcing reconnect")
            return False

        # Force reconnect if no successful ops for too long
        if now - self._last_successful_op > self.config.health_check_interval * 2:
            if self.config.debug:
                print(f"[DEBUG] No successful operations for {now - self._last_successful_op:.1f}s, forcing reconnect")
            return False

        return True

    def _ensure_connected(self) -> bool:
        """Ensure the Modbus client is connected. Must be called within lock."""
        # Check connection health
        if not self._check_connection_health():
            self._force_disconnect()

        if self._is_connected and self.client:
            return True

        if self.config.debug:
            print(f"[DEBUG] Connecting to Modbus on {self.config.port}")

        # Create client if needed
        if not self.client:
            self.client = ModbusSerialClient(
                port=self.config.port,
                baudrate=self.config.baudrate,
                parity=self.config.parity,
                bytesize=self.config.bytesize,
                stopbits=self.config.stopbits,
                timeout=self.config.timeout
            )

        # Connect with timeout
        start_time = time.time()
        connected = False

        try:
            connected = self.client.connect()
            if time.time() - start_time > self.config.connection_timeout:
                if self.config.debug:
                    print(f"[DEBUG] Connection timeout after {self.config.connection_timeout}s")
                connected = False
        except Exception as e:
            if self.config.debug:
                print(f"[DEBUG] Connection exception: {e}")
            connected = False

        if connected:
            self._is_connected = True
            self._unit_kwarg = self._detect_unit_kwarg()
            self._consecutive_failures = 0
            if self.config.debug:
                print(f"[DEBUG] Connected to Modbus, addressing kwarg: {self._unit_kwarg}")
            return True
        else:
            self._is_connected = False
            self._consecutive_failures += 1
            if self.config.debug:
                print(f"[DEBUG] Failed to connect to Modbus on {self.config.port}")
            return False

    def _force_disconnect(self):
        """Force disconnect and cleanup. Must be called within lock."""
        if self.client and self._is_connected:
            try:
                self.client.close()
            except Exception as e:
                if self.config.debug:
                    print(f"[DEBUG] Exception during disconnect: {e}")
        self._is_connected = False
        self.client = None

    @contextmanager
    def acquire_connection(self):
        """
        Context manager for acquiring exclusive access to the Modbus connection.

        Usage:
            with manager.acquire_connection() as client:
                # Use client for Modbus operations
                result = client.read_holding_registers(...)
        """
        with self.lock:
            self._connection_count += 1
            try:
                if not self._ensure_connected():
                    raise RuntimeError(f"Cannot connect to Modbus on {self.config.port}")

                if self.config.debug:
                    print(f"[DEBUG] Connection acquired (count: {self._connection_count})")

                yield self.client

            finally:
                self._connection_count -= 1
                if self.config.debug:
                    print(f"[DEBUG] Connection released (count: {self._connection_count})")

    def read_holding_register(self, slave_id: int, address: int) -> Optional[int]:
        """
        Read a single holding register from the specified slave.

        Args:
            slave_id: Modbus slave/unit ID
            address: Register address

        Returns:
            Register value or None if error
        """
        last_exception = None

        for attempt in range(self.config.max_retries):
            try:
                with self.acquire_connection() as client:
                    kwargs = {}
                    if self._unit_kwarg:
                        kwargs[self._unit_kwarg] = slave_id

                    if self.config.debug:
                        if attempt > 0:
                            print(f"[DEBUG] Reading register 0x{address:04X} from slave {slave_id} (attempt {attempt + 1})")
                        else:
                            print(f"[DEBUG] Reading register 0x{address:04X} from slave {slave_id}")

                    result = client.read_holding_registers(address=address, count=1, **kwargs)

                    if hasattr(result, 'isError') and result.isError():
                        if self.config.debug:
                            print(f"[DEBUG] Read error: {result}")
                        self._consecutive_failures += 1
                        if attempt < self.config.max_retries - 1:
                            time.sleep(self.config.retry_delay)
                            continue
                        return None

                    if not hasattr(result, 'registers') or not result.registers:
                        if self.config.debug:
                            print(f"[DEBUG] Empty response")
                        self._consecutive_failures += 1
                        if attempt < self.config.max_retries - 1:
                            time.sleep(self.config.retry_delay)
                            continue
                        return None

                    # Success
                    value = int(result.registers[0])
                    self._last_successful_op = time.time()
                    self._consecutive_failures = 0
                    if self.config.debug:
                        print(f"[DEBUG] Read value: {value}")
                    return value

            except Exception as e:
                last_exception = e
                self._consecutive_failures += 1
                if self.config.debug:
                    print(f"[DEBUG] Read exception (attempt {attempt + 1}): {e}")

                if attempt < self.config.max_retries - 1:
                    # Force reconnection on next attempt if this was a connection error
                    if "connection" in str(e).lower() or "timeout" in str(e).lower():
                        self._force_disconnect()
                    time.sleep(self.config.retry_delay)
                    continue
                break

        if self.config.debug:
            print(f"[DEBUG] Read failed after {self.config.max_retries} attempts. Last error: {last_exception}")
        return None

    def write_holding_register(self, slave_id: int, address: int, value: int) -> bool:
        """
        Write a single holding register to the specified slave.

        Args:
            slave_id: Modbus slave/unit ID
            address: Register address
            value: Value to write

        Returns:
            True if successful, False otherwise
        """
        last_exception = None

        for attempt in range(self.config.max_retries):
            try:
                with self.acquire_connection() as client:
                    kwargs = {}
                    if self._unit_kwarg:
                        kwargs[self._unit_kwarg] = slave_id

                    if self.config.debug:
                        if attempt > 0:
                            print(f"[DEBUG] Writing value {value} to register 0x{address:04X} on slave {slave_id} (attempt {attempt + 1})")
                        else:
                            print(f"[DEBUG] Writing value {value} to register 0x{address:04X} on slave {slave_id}")

                    result = client.write_register(address=address, value=value, **kwargs)

                    if hasattr(result, 'isError') and result.isError():
                        if self.config.debug:
                            print(f"[DEBUG] Write error: {result}")
                        self._consecutive_failures += 1
                        if attempt < self.config.max_retries - 1:
                            time.sleep(self.config.retry_delay)
                            continue
                        return False

                    # Success
                    self._last_successful_op = time.time()
                    self._consecutive_failures = 0
                    if self.config.debug:
                        print(f"[DEBUG] Write successful")
                    return True

            except Exception as e:
                last_exception = e
                self._consecutive_failures += 1
                if self.config.debug:
                    print(f"[DEBUG] Write exception (attempt {attempt + 1}): {e}")

                if attempt < self.config.max_retries - 1:
                    # Force reconnection on next attempt if this was a connection error
                    if "connection" in str(e).lower() or "timeout" in str(e).lower():
                        self._force_disconnect()
                    time.sleep(self.config.retry_delay)
                    continue
                break

        if self.config.debug:
            print(f"[DEBUG] Write failed after {self.config.max_retries} attempts. Last error: {last_exception}")
        return False

    def get_health_status(self) -> Dict[str, Any]:
        """Get connection health status and statistics."""
        now = time.time()
        return {
            "is_connected": self._is_connected,
            "consecutive_failures": self._consecutive_failures,
            "last_successful_op": self._last_successful_op,
            "seconds_since_success": now - self._last_successful_op,
            "connection_count": self._connection_count,
            "port": self.config.port,
            "timeout": self.config.timeout,
            "max_retries": self.config.max_retries
        }

    def disconnect(self):
        """Disconnect from the Modbus port."""
        with self.lock:
            if self.client and self._is_connected:
                if self.config.debug:
                    print(f"[DEBUG] Disconnecting from Modbus")
                self.client.close()
                self._is_connected = False

    def __del__(self):
        """Cleanup on destruction."""
        self.disconnect()


# Global instance for the shared manager
_global_manager: Optional[SharedModbusManager] = None
_manager_lock = threading.Lock()


def get_shared_modbus_manager(config: ModbusConfig) -> SharedModbusManager:
    """
    Get the global shared Modbus manager instance.

    Creates a new manager if none exists or if the configuration changes.
    """
    global _global_manager

    with _manager_lock:
        # Create new manager if none exists or config changed
        if (_global_manager is None or
            _global_manager.config.port != config.port or
            _global_manager.config.baudrate != config.baudrate):

            # Disconnect old manager if it exists
            if _global_manager:
                _global_manager.disconnect()

            _global_manager = SharedModbusManager(config)

        return _global_manager


def reset_shared_modbus_manager():
    """Reset the global manager (useful for testing)."""
    global _global_manager

    with _manager_lock:
        if _global_manager:
            _global_manager.disconnect()
            _global_manager = None