import logging
import asyncio
import os
from bleak import BleakClient, BLEDevice
from oe_protocol import OeProtocol
from utils import get_data_size

GATEWAY_SERVICE_BLE_NAME = "optimize.gateway.service.ble"

UART_CHAR_UUID = "00002760-08c2-11e1-9073-0e8ac72e0254"
FIRMWARE_CHAR_UUID ="00002760-08c2-11e1-9073-0e8ac72e0255"

class OeDevice:
    def __init__(self, device : BLEDevice, name):
        self.logger = logging.getLogger(GATEWAY_SERVICE_BLE_NAME )
        self.client = BleakClient(device.address ,disconnected_callback = self.disconnected_callback)
        self.name = name
        self.protocol = None
        self.connected = False

    async def sample(self, mask):
        if self.protocol:
            self.logger.info(f"[{self.name}] - Sampling sensor mask: {mask}...")
            await self.protocol.take_samples(mask)
            self.logger.info(f"[{self.name}] - Sampling sensor mask: {mask}, done.")

    async def sleep(self, time, force):
        if self.protocol:
            self.logger.info(f"[{self.name}] - Sending to sleep for {time} seconds...")
            await self.protocol.sleep(time, force)
            self.logger.info(f"[{self.name}] - Sending to sleep, done.")

    async def read_all_configs(self) -> dict:
        if self.protocol:
            self.logger.info(f"[{self.name}] - Reading all configs...")
            await self.protocol.read_config([])
            self.logger.info(f"[{self.name}] - Reading all configs, done.")
            return self.protocol.deviceConfigs

    async def read_config(self, main_group: int, sub_group: int) -> dict:       
        request = bytearray(2)
        request[0] = main_group
        request[1] = sub_group

        if self.protocol:
            self.logger.info(f"[{self.name}] - Reading config, main_group {main_group}, sub_group {sub_group}...")
            await self.protocol.read_config(request)
            self.logger.info(f"[{self.name}] - Reading config, done.")
            configs = self.protocol.deviceConfigs

            if main_group in configs:
                for config in configs[main_group]:
                    if config['sub_group'] == sub_group:
                        return config

    async def write_all_configs(self, configs: bytearray) -> int:
        """
        Writes configs byte array to device.
        """
        if self.protocol:
            self.logger.info(f"[{self.name}] - Writing configs...")
            await self.protocol.write_config(configs)
            self.logger.info(f"[{self.name}] - Writing configs, done.")
            hash_id = self.protocol.deviceConfigs['config_hash_id']
            return hash_id

    async def write_config(self, main_group: int, sub_group: int, data_type_id: int, config_value: bytearray) -> int:
        """
        Writes one config to the device.
        """
        vector = 0x00
        element_type = data_type_id & 0x0F
        vector_size = len(config_value) / get_data_size(element_type)

        vector |= (0x00 << 4) if vector_size <= 1 else (vector_size << 4)  # Set the first 4 bits based on vectorSize if more than 1, else 0
        vector |= element_type & 0x0F

        # String length is not written in vector length
        if element_type == 0x0C:
            vector &= 0x0F

        data_length = len(config_value)
        payload = bytearray(3 + data_length)
        payload[0] = main_group  # main group
        payload[1] = sub_group  # sub group
        payload[2] = vector  # vector

        payload[3:3 + data_length] = config_value

        if self.protocol:
            self.logger.info(f"[{self.name}] - Writing configs...")
            await self.protocol.write_config(payload)
            self.logger.info(f"[{self.name}] - Writing configs, done.")
            hash_id = self.protocol.deviceConfigs['config_hash_id']
            return hash_id
        
    async def upload_firmware(self, firmware: bytearray, signature: bytearray) -> bool:
        """
        Uploads device firmware to the device.
        """
        if self.protocol:
            self.logger.info(f"[{self.name}] - Uploading Firmware and Signature...")
            result = await self.protocol.upload_firmware(firmware=firmware, signature=signature)
            self.logger.info(f"[{self.name}] - Uploading Firmware and Signature, done.")         
            return result
        
    async def connect(self):
        try:
            await self.client.connect(timeout=20.0)
            await asyncio.sleep(0.2)  # wait a bit to let the connection stabilize

            # Force service discovery BEFORE notify/write
            services = self.client.services

            self.logger.debug(f"[{self.name}] - services:")
            for service in services:
                self.logger.debug(f"  {service.uuid}")
                for char in service.characteristics:
                    self.logger.debug(f"    {char.uuid} {char.properties}")

            # Subscribe to the UART characteristic. Without this nothing ever reaches
            # notification_handler -> OeProtocol.push(), and since the protocol only
            # ever writes (there is no read_gatt_char anywhere), no reply from the
            # device can be parsed at all. It must come after service discovery.
            await self.client.start_notify(UART_CHAR_UUID, self.notification_handler)

            self.protocol = OeProtocol(self.client)
            self.connected = True
            self.logger.info(f"[{self.name}] - Connected!")
        except Exception as e:
            self.logger.exception(f"[{self.name}] - Connection failed: {e}")
            await self.client.disconnect()  # cleanup just in case
            self.connected = False

    async def connect_ota(self): 
        try:
            await self.client.connect()
            await asyncio.sleep(0.2)  # wait a bit to let the connection stabilize
            await self.client.start_notify(FIRMWARE_CHAR_UUID, self.notification_handler)
            self.protocol = OeProtocol(self.client)
            self.connected = True
            self.logger.info(f"[{self.name}] - Connected!")
        except Exception as e:
            self.logger.exception(f"[{self.name}] - Connection failed: {e}")
            await self.client.disconnect()  # cleanup just in case
            self.connected = False

    async def disconnect(self):
        if self.connected:
            try:
                await self.client.disconnect()
            except Exception as e:
                pass
                self.logger.exception(f"[{self.name}] OeDevice - Failed to disconnect cleanly: {e}")
            self.connected = False

    def notification_handler(self, sender, data):
        # Diagnostic, off unless OE_TRACE is set. Being able to see whether *any* frame
        # arrives is what separated "the device is not answering" from "our parsing is
        # wrong" during the 2026-08-19 hardware test — the answer was zero frames.
        if os.environ.get("OE_TRACE"):
            n = getattr(self, "_rx_n", 0) + 1
            self._rx_n = n
            if n <= 5 or n % 200 == 0:
                print(f"    [rx] #{n} {len(data)}B", flush=True)
        if self.protocol:
            self.protocol.push(data)
    
    def disconnected_callback(self, client):
        self.connected = False
        self.logger.info(f"[{self.name}] - Disconnected!")

        # Cancel any pending operations when disconnect occurs
        if self.protocol and self.protocol.tcs:
            if not self.protocol.tcs.done():
                self.protocol.tcs.set_exception(ConnectionError("Device disconnected unexpectedly"))

        # Clear any partial data in buffer
        if self.protocol:
            self.protocol.clear_incoming_data_buffer()

    def get_sample_data(self) -> list:
        if self.protocol:
            return list(self.protocol.sampleData.values())
    
    def get_config_data(self):
        if self.protocol:
            return self.protocol.deviceConfigs
        
    def get_config_hash_id(self):
        if self.protocol:
            return self.protocol.deviceConfigs['config_hash_id']