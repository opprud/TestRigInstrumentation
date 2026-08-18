import asyncio
import logging
from typing import Optional
from bleak import BleakClient
from bleak.exc import BleakDBusError, BleakError
from utils import get_data_size, get_sensor_name, parse_data_to_float, parse_data

GATEWAY_SERVICE_BLE_NAME = "optimize.gateway.service.ble"

UART_SERVICE_UUID = "00002760-08c2-11e1-9073-0e8ac72e0254"
FIRMWARE_SERVICE_UUID ="00002760-08c2-11e1-9073-0e8ac72e0255"

SAMPLE_SENSORS_CMD = 0x30
SLEEP_CMD = 0x40
CONFIG_READ_CMD = 0x20
CONFIG_WRITE_CMD = 0x21
UPDATE_FIRMWARE_CMD = 0x1

TIMEOUT_DISCONNECT = 10
TIMEOUT_SAMPLE = 120
TIMEOUT_CONFIG = 20

class OeProtocol:
    def __init__(self,ble_client: BleakClient):
        self.logger = logging.getLogger(GATEWAY_SERVICE_BLE_NAME)
        self.ble_client = ble_client
        self.incoming_data_buffer = bytearray()# buffer for incoming data
        self.sampleData = {}
        self.deviceConfigs = {}
        self.tcs = None # Task completion flag

    async def take_samples(self, sensor_mask):
        self.tcs = asyncio.Future()
        try:
            self.sampleData = {}
            cmd = 0
            cmd |= SAMPLE_SENSORS_CMD
            cmd |= (1 << 14)# last packet
            cmd |= (1 << 15)# request

            payload = sensor_mask.to_bytes(4, byteorder='little')

            await self.send_command(cmd, payload)
            try:
                await asyncio.wait_for(self.tcs, timeout=TIMEOUT_SAMPLE) # Wait for data
            except ConnectionError:
                # Re-raise connection errors from disconnected_callback
                raise

        except ConnectionError as ex:
            self.logger.error(f"take_samples - Device disconnected: {ex}")
        except asyncio.TimeoutError:
            self.logger.error("take_samples Task was canceled due to timeout.")
        except Exception as ex:
            self.logger.exception(f"take_samples Task - An error occurred: {ex}")

    async def sleep(self, time_s: int, force : bool):
        self.tcs = asyncio.Future()
        try:
            cmd = 0
            cmd |= SLEEP_CMD
            cmd |= (1 << 14)# last packet
            cmd |= (1 << 15)# request

            payload = bytearray(3)
            payload[0] = 1 if force else 0
            payload[1] = time_s & 0xFF # first byte
            payload[2] = (time_s >> 8) & 0xFF # second byte

            await self.send_command(cmd, payload)
            if not force:
                try:
                    await asyncio.wait_for(self.tcs, timeout=TIMEOUT_DISCONNECT) # Wait for ack
                except ConnectionError:
                    raise

        except ConnectionError as ex:
            self.logger.error(f"sleep - Device disconnected: {ex}")
        except asyncio.TimeoutError:
            self.logger.error("sleep Task was canceled due to timeout.")
        except Exception as ex:
            self.logger.exception(f"sleep Task - An error occurred: {ex}")

    async def read_config(self, request: bytearray):
        self.tcs = asyncio.Future()
        try:
            self.deviceConfigs = {}
            cmd = 0
            cmd |= CONFIG_READ_CMD
            cmd |= (1 << 14)# last packet
            cmd |= (1 << 15)# request

            await self.send_command(cmd, request)
            try:
                await asyncio.wait_for(self.tcs, timeout=TIMEOUT_CONFIG) # Wait for data
            except ConnectionError:
                raise

        except ConnectionError as ex:
            self.logger.error(f"read_config - Device disconnected: {ex}")
        except asyncio.TimeoutError:
            self.logger.error("read_config Task was canceled due to timeout.")
        except Exception as ex:
            self.logger.exception(f"read_config Task - An error occurred: {ex}")

    async def write_config(self, config: bytearray):
        self.tcs = asyncio.Future()
        try:
            cmd = 0
            cmd |= CONFIG_WRITE_CMD
            cmd |= (1 << 14)# last packet
            cmd |= (1 << 15)# request

            await self.send_command(cmd, config)
            try:
                await asyncio.wait_for(self.tcs, timeout=TIMEOUT_CONFIG) # Wait for data
            except ConnectionError:
                raise

        except ConnectionError as ex:
            self.logger.error(f"write_config - Device disconnected: {ex}")
        except asyncio.TimeoutError:
            self.logger.error("write_config Task was canceled due to timeout.")
        except Exception as ex:
            self.logger.exception(f"write_config Task - An error occurred: {ex}")

    async def send_command(self, cmd, payload):
        try:
            self.clear_incoming_data_buffer()

            # Protocol version
            version_major = 0
            version_mid = 0
            version_minor = 1
            payload_len = 0

            if payload is not None:
                payload_len = len(payload)

            if self.ble_client is not None:
                # Check connection before sending
                if not self.ble_client.is_connected:
                    raise ConnectionError(f"Device disconnected before sending command 0x{cmd:04x}")

                packet = bytearray(payload_len + 10)
                packet[0] = cmd & 0xFF  # first CMD byte
                packet[1] = (cmd >> 8) & 0xFF  # second CMD byte
                packet[2] = version_major & 0xFF  # Version Major
                packet[3] = version_mid & 0xFF  # Version Mid
                packet[4] = version_minor & 0xFF  # first Version Minor byte
                packet[5] = (version_minor >> 8) & 0xFF  # second Version Major byte
                packet[6] = payload_len & 0xFF  # first Payload byte
                packet[7] = (payload_len >> 8) & 0xFF  # second Payload byte
                packet[8] = (payload_len >> 16) & 0xFF  # third Payload byte
                packet[9] = (payload_len >> 24) & 0xFF  # fourth Payload byte

                if payload is not None:
                    packet[10:] = payload

                try:
                    await self.ble_client.write_gatt_char(UART_SERVICE_UUID,packet)
                except (BleakDBusError, BleakError) as e:
                    if "0x0e" in str(e) or not self.ble_client.is_connected:
                        raise ConnectionError(f"Device disconnected while sending command 0x{cmd:04x}: {e}")
                    raise

        except ConnectionError as ex:
            self.logger.error(f"send_command - {ex}")
            raise
        except Exception as ex:
            self.logger.exception(f"send_command Task - An error occurred: {ex}")
            raise
    
    def parse_sensor_data_block(self, data: bytearray) -> bool:
        try:
            offset = 0
            while offset < len(data):
                remaining = len(data) - offset

                if remaining >= 3:
                    sensor_id = data[offset]
                    data_type = data[offset + 1]
                    nr_of_samples = data[offset + 2]
                    data_length = get_data_size(data_type)
                    
                    if remaining >= 3 + nr_of_samples:
                        values = data[offset + 3: offset + 3 + nr_of_samples * data_length]

                        # Assuming sampleData is a dictionary with sensor_id as key
                        if sensor_id not in self.sampleData:
                            self.sampleData[sensor_id] = {
                                'sensor_name': get_sensor_name(sensor_id),
                                'sensor_id': sensor_id,
                                'data_type_id': data_type,
                                'data': []
                            }

                        self.sampleData[sensor_id]['data'].extend(parse_data_to_float(data_type,values))

                        offset += nr_of_samples * data_length + 3
                    else:
                        return True
                else:
                    return True
            return True
        
        except Exception as ex:
            self.logger.exception(f"parse_sensor_data_block - An error occurred: {ex}")
            return False


    def parse_config_block_data(self, data: bytearray) -> bool:
        try:
            offset = 0
            self.deviceConfigs['configs'] = []

            while offset < len(data):
                remaining = len(data) - offset

                if remaining > 4:  # At least 4 bytes Config block or HashId
                    main_group = data[offset]
                    sub_group = data[offset + 1]
                    vector = data[offset + 2]

                    vector_size = 1 if ((vector & 0xF0) >> 4) == 0 else (vector & 0xF0) >> 4  # vector size is never 0
                    element_type = vector & 0x0F
                    data_length = get_data_size(element_type) * vector_size

                    # In case of string data, we need to find the length of the string
                    if element_type == 0x0C:
                        data_length = 0
                        for i in range(offset + 3, len(data)):
                            data_length += 1
                            if data[i] == 0x00:
                                break
                        values = data[offset + 3:offset + 3 + data_length -1] # no need to add 0x00 to the end of string
                    else:
                        values = data[offset + 3:offset + 3 + data_length]

                    # sub config with required fields
                    sub = {
                        'main_group': main_group,
                        'sub_group': sub_group,
                        'data_type_id': element_type,
                        'config_value': parse_data(element_type, values)
                    }

                    # Check if a config with the same main_group and sub_group exists
                    updated = False
                    for existing_sub in self.deviceConfigs['configs']:
                        if (existing_sub['main_group'] == main_group and
                            existing_sub['sub_group'] == sub_group):
                            existing_sub.update(sub)
                            updated = True
                            break

                    if not updated:
                        self.deviceConfigs['configs'].append(sub)

                    offset += 3 + data_length

                elif remaining == 4:
                    # handle Config Hash Id
                    hash_id = data[offset:offset + 4]
                    if self.parse_config_hash_id(hash_id):   
                        return True                
            return True
        except Exception as ex:
            self.logger.exception(f"parse_config_data_block - An error occurred: {ex}")
            return False

    def parse_config_hash_id(self, data: bytearray) -> bool:      
        if len(data) == 4:
            self.deviceConfigs['config_hash_id'] = int.from_bytes(data, byteorder='little', signed=False) # write hach_id to dict
            return True
        else:
            return False
  
    def parser_on_cmd_packet(self, cmd: int, payload: Optional[bytearray]):
    
        CMD_MASK = 0x0FFF
        CMD_PE_MASK = 1 << 11
        PROT_VER_ERR_MASK = 1 << 12
        LAST_PACKET_MASK = 1 << 13
        REQUEST_MASK = 1 << 14

        if SAMPLE_SENSORS_CMD == (cmd & CMD_MASK):
            if (cmd & REQUEST_MASK) == 0:  # Check if it is a reply
                # Reply payload
                status = int.from_bytes(payload[0:4], byteorder='little')
                config_crc = int.from_bytes(payload[4:8], byteorder='little')

                # Data Blocks
                data_blocks = payload[8:]

                if len(data_blocks) >= 3:  # if datablock is at least 3 bytes in size
                    if self.parse_sensor_data_block(data_blocks):                       
                        if self.tcs:
                            self.tcs.set_result(True)

        if SLEEP_CMD == (cmd & CMD_MASK):
            if (cmd & REQUEST_MASK) == 0:  # Check if it is a reply
                if self.tcs:
                    self.tcs.set_result(True)

        if CONFIG_READ_CMD == (cmd & CMD_MASK):
            if (cmd & REQUEST_MASK) == 0:  # Check if it is a reply
                if self.parse_config_block_data(payload):
                    if self.tcs:
                        self.tcs.set_result(True)
        
        if CONFIG_WRITE_CMD == (cmd & CMD_MASK):
            if (cmd & REQUEST_MASK) == 0:  # Check if it is a reply
                if self.parse_config_hash_id(payload):
                    if self.tcs:
                        self.tcs.set_result(True)

        if UPDATE_FIRMWARE_CMD == (cmd & CMD_MASK):
            if (cmd & REQUEST_MASK) == 0:  # Check if it is a reply
                if self.parse_config_hash_id(payload):
                    if self.tcs:
                        self.tcs.set_result(True)

    def push(self, data: bytearray): 
        self.incoming_data_buffer.extend(data)
        self.parse_incoming_data_buffer()

    def parse_incoming_data_buffer(self):

        while len(self.incoming_data_buffer) >= 10:

            # Masks
            CMD_PE_MASK = 1 << 11  # Command Parser Error Command ID bit mask
            PROT_VER_ERR_MASK = 1 << 12  # Protocol version Error bit mask

            # Parse the received data
            cmd = int.from_bytes(self.incoming_data_buffer[0:2], byteorder='little', signed=False)
            v_major = self.incoming_data_buffer[2]
            v_mid = self.incoming_data_buffer[3]
            v_minor = int.from_bytes(self.incoming_data_buffer[4:6], byteorder='little', signed=False)
            length = int.from_bytes(self.incoming_data_buffer[6:10], byteorder='little', signed=False)

            # Check for protocol faults
            if (cmd & CMD_PE_MASK) == 1:  # Check for Command Parser Error
                self.logger.error("parse_incoming_data_buffer - Command Parser Error!")
                if self.tcs:
                    if not self.tcs.done():
                        self.tcs.set_exception(ValueError("Command Parser Error!"))
                break

            if (cmd & PROT_VER_ERR_MASK) == 1:  # Check for Protocol Version Error
                self.logger.error("parse_incoming_data_buffer - Protocol Version Error!")
                if self.tcs:
                    if not self.tcs.done():
                        self.tcs.set_exception(ValueError("Protocol Version Error!"))
                break

            if v_major != 0 and v_mid != 0 and v_minor != 1:
                self.logger.error(f"parse_incoming_data_buffer - Decode buffer: protocol versions don't match! Received: {v_major}.{v_mid}.{v_minor}")
                if self.tcs:
                    if not self.tcs.done():
                        self.tcs.set_exception(ValueError("Protocol versions don't match!!"))
                break
            
            # Handle data if everything was received - header + datalength
            if len(self.incoming_data_buffer) >= 10 + length:
                    
                    # Quick fix!!! in this case len does not iclude the size of hash id - 4 bytes, nned a fix in fw!!!!
                    if cmd == 0x20 and len(self.incoming_data_buffer) == (10 + length + 4):
                        # Extract payload bytes based on data length
                        payload = self.incoming_data_buffer[10:10 + length + 4]

                        del self.incoming_data_buffer[0:10 + length + 4]

                        self.parser_on_cmd_packet(cmd, payload)

                    else: 

                        # Extract payload bytes based on data length
                        payload = self.incoming_data_buffer[10:10 + length]

                        del self.incoming_data_buffer[0:10 + length]

                        self.parser_on_cmd_packet(cmd, payload)

            else: # Wait for more data
                break

    def clear_incoming_data_buffer(self):
        self.incoming_data_buffer.clear()

    async def upload_firmware_data(self, firmware: bytearray):
        """
        Sends firmware to the device in 201 byte blocks. First byte is allways = 1, indicating a firmware packet.
        """
        offset = 0
        while offset < len(firmware):
            # Check if device is still connected before attempting write
            if not self.ble_client.is_connected:
                raise ConnectionError(f"Device disconnected during firmware upload at {offset}/{len(firmware)} bytes")

            length = min(200, len(firmware) - offset)

            block = bytearray(length + 1)
            block[0] = 1
            block[1:] = firmware[offset:offset + length]
            self.clear_incoming_data_buffer()

            try:
                await self.ble_client.write_gatt_char(FIRMWARE_SERVICE_UUID, block)
            except (BleakDBusError, BleakError) as e:
                # Check if error is due to disconnection
                if "0x0e" in str(e) or not self.ble_client.is_connected:
                    raise ConnectionError(f"Device disconnected during firmware upload: {e}")
                raise  # Re-raise other BLE errors

            offset += length

            # print upload status in percentage(how many % of firmware have been sent to device).
            # percent_sent = (offset / len(firmware)) * 100
            # print(f"\rSent: {percent_sent:.2f}%", end="")
        

    async def upload_signature_data(self, signature: bytearray):
        """
        Sends signature to the device. First byte = 2, indicating that that device must install the firmware.
        """
        if signature is not None:
            # Check if device is still connected
            if not self.ble_client.is_connected:
                raise ConnectionError("Device disconnected before signature upload")

            signature_size = 64
            install_cmd = bytearray(signature_size + 1)
            install_cmd[0] = 2
            install_cmd[1:] = signature[:signature_size] # copy signature after cmd byte
            self.clear_incoming_data_buffer()
            # response = false to avoid exception because device restarts when correct signature is received
            try:
                await self.ble_client.write_gatt_char(FIRMWARE_SERVICE_UUID, install_cmd,response=False)
            except (BleakDBusError, BleakError) as e:
                if "0x0e" in str(e) or not self.ble_client.is_connected:
                    raise ConnectionError(f"Device disconnected during signature upload: {e}")
                raise 
        

    async def upload_firmware(self, firmware: bytearray, signature: bytearray) -> bool: 
        """
        Updates device firmware
        """
        try:
            self.logger.debug("Uploading firmware data...")
            await self.upload_firmware_data(firmware=firmware)
            self.logger.debug("Uploading firmware data, done.")
            self.logger.debug("Uploading signature data...")
            await self.upload_signature_data(signature=signature)
            self.logger.debug("Uploading signature data, done.")
            return True

        except ConnectionError as ex:
            self.logger.error(f"Device disconnected during firmware update: {ex}")
            return False
        except asyncio.TimeoutError:
            self.logger.error("update_firmware Task was canceled due to timeout.")
            return False
        except Exception as ex:
            self.logger.exception(f"update_firmware Task - An error occurred: {ex}")
            return False
            
          