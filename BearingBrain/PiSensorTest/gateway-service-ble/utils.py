import json
import os
import struct

import struct


def value_to_bytearray(data_type: int, value):
    """
    Converts config values to the bytearray
    """
    # Ensure value is always a list for consistent processing
    if not isinstance(value, list):
        value = [value]

    result = bytearray()

    for val in value:
        if data_type == 0x00:  # UINT8
            result += struct.pack("<B", val)

        elif data_type == 0x01:  # UINT16
            result += struct.pack("<H", val)

        elif data_type == 0x02:  # UINT24
            result += val.to_bytes(3, byteorder="little", signed=False)

        elif data_type == 0x03:  # UINT32
            result += struct.pack("<I", val)

        elif data_type == 0x04:  # UINT64
            result += struct.pack("<Q", val)

        elif data_type == 0x05:  # INT8
            result += struct.pack("<b", val)

        elif data_type == 0x06:  # INT16
            result += struct.pack("<h", val)

        elif data_type == 0x07:  # INT24
            result += int(val & 0xFFFFFF).to_bytes(3, byteorder="little", signed=True)

        elif data_type == 0x08:  # INT32
            result += struct.pack("<i", val)

        elif data_type == 0x09:  # INT64
            result += struct.pack("<q", val)

        elif data_type == 0x0A:  # FLOAT
            result += struct.pack("<f", val)

        elif data_type == 0x0B:  # DOUBLE
            result += struct.pack("<d", val)

        elif data_type == 0x0C:  # STRING (null-terminated)
            result += val.encode("utf-8") + b"\x00"

        else:
            raise ValueError(f"Unknown DataTypeId: 0x{data_type:02X}")

    return result


def add_config_to_buffer(buffer: bytearray, config):
    """
    Adds device config to the buffer
    """
    main_group = config["main_group"]
    sub_group = config["sub_group"]
    data_type_id = config["data_type_id"]
    value = config["config_value"]
    config_value = value_to_bytearray(data_type=data_type_id, value=value)

    vector = 0x00
    element_type = data_type_id & 0x0F
    vector_size = len(config_value) / get_data_size(element_type)

    vector |= (
        (0x00 << 4) if vector_size <= 1 else (vector_size << 4)
    )  # Set the first 4 bits based on vectorSize if more than 1, else 0
    vector |= element_type & 0x0F

    # String length is not written in vector length
    if element_type == 0x0C:
        vector &= 0x0F

    data_length = len(config_value)
    payload = bytearray(3 + data_length)
    payload[0] = main_group  # main group
    payload[1] = sub_group  # sub group
    payload[2] = vector  # vector

    payload[3 : 3 + data_length] = config_value
    buffer.extend(payload)


def compare_configs(device_configs: list, sampling_configs: list) -> list:
    """
    Compare sapling configurations with device configurations retrieved from the device.
    If device configuration does NOT match to sapling configuration, save it to the output list.
    """
    result = []

    # Build a lookup dictionary for sampling configs
    sampling_configs_lookup = {
        (item["main_group"], item["sub_group"]): item for item in sampling_configs
    }

    # Compare each item in device configs
    for device_config in device_configs:
        key = (device_config["main_group"], device_config["sub_group"])
        sapling_config = sampling_configs_lookup.get(key)

        if sapling_config:
            if sapling_config["config_value"] != device_config["config_value"]:
                result.append(sapling_config)

    return result


def save_data_to_file(data, path, name):
    try:
        # Ensure the directory exists
        os.makedirs(path, exist_ok=True)

        filename = os.path.join(path, name)

        with open(filename, "w") as f:
            json.dump(data, f, indent=4)

    except Exception as e:
        print(f"Error while saving sensor data: {e}")


# get sensor names
def get_sensor_name(sensor_id: int) -> str:
    if sensor_id == 0:
        return "Battery Level"
    elif sensor_id == 1:
        return "Ambient Temperature"
    elif sensor_id == 2:
        return "Machine Temperature"
    elif sensor_id == 3:
        return "Ambient Microphone"
    elif sensor_id == 4:
        return "Machine Microphone"
    elif sensor_id == 5:
        return "Acceleration ADXL1002"
    elif sensor_id == 6:
        return "Acceleration ADXL362 X"
    elif sensor_id == 7:
        return "Acceleration ADXL362 Y"
    elif sensor_id == 8:
        return "Acceleration ADXL362 Z"
    elif sensor_id == 9:
        return "Acceleration ISM330 X"
    elif sensor_id == 10:
        return "Acceleration ISM330 Y"
    elif sensor_id == 11:
        return "Acceleration ISM330 Z"
    elif sensor_id == 12:
        return "Gyroscope ISM330 X"
    elif sensor_id == 13:
        return "Gyroscope ISM330 Y"
    elif sensor_id == 14:
        return "Gyroscope ISM330 Z"
    elif sensor_id == 15:
        return "Magnetic MMC5603NJ X"
    elif sensor_id == 16:
        return "Magnetic MMC5603NJ Y"
    elif sensor_id == 17:
        return "Magnetic MMC5603NJ Z"
    elif sensor_id == 18:
        return "Magnetic DRV425"
    else:
        return str(sensor_id)


# convert data to correct datatype according to OE protocol
def parse_data(data_type: int, data: bytearray):

    if data_type == 0x00:  # UINT8
        result = list(data)

    elif data_type == 0x01:  # UINT16
        result = [
            int.from_bytes(data[i : i + 2], "little", signed=False)
            for i in range(0, len(data), 2)
        ]

    elif data_type == 0x02:  # UINT24
        result = [
            (data[i] | (data[i + 1] << 8) | (data[i + 2] << 16))
            for i in range(0, len(data), 3)
        ]

    elif data_type == 0x03:  # UINT32
        result = [
            int.from_bytes(data[i : i + 4], "little", signed=False)
            for i in range(0, len(data), 4)
        ]

    elif data_type == 0x04:  # UINT64
        result = [
            int.from_bytes(data[i : i + 8], "little", signed=False)
            for i in range(0, len(data), 8)
        ]

    elif data_type == 0x05:  # INT8
        result = [struct.unpack("<b", bytes([b]))[0] for b in data]

    elif data_type == 0x06:  # INT16
        result = [
            int.from_bytes(data[i : i + 2], "little", signed=True)
            for i in range(0, len(data), 2)
        ]

    elif data_type == 0x07:  # INT24
        result = []
        for i in range(0, len(data), 3):
            val = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16)
            if val & 0x800000:
                val |= ~0xFFFFFF
            result.append(val)

    elif data_type == 0x08:  # INT32
        result = [
            int.from_bytes(data[i : i + 4], "little", signed=True)
            for i in range(0, len(data), 4)
        ]

    elif data_type == 0x09:  # INT64
        result = [
            int.from_bytes(data[i : i + 8], "little", signed=True)
            for i in range(0, len(data), 8)
        ]

    elif data_type == 0x0A:  # FLOAT
        result = [
            struct.unpack("<f", data[i : i + 4])[0] for i in range(0, len(data), 4)
        ]

    elif data_type == 0x0B:  # DOUBLE
        result = [
            float(struct.unpack("<d", data[i : i + 8])[0])
            for i in range(0, len(data), 8)
        ]

    elif data_type == 0x0C:  # String
        return data.decode("utf-8")

    else:
        raise ValueError("Unknown DataTypeId: 0x{:02X}".format(data_type))

    # Return a single value if result contains only one item
    if len(result) == 1:
        return result[0]
    return result


# get data size acording to OE protocol
def get_data_size(data_type: int) -> int:
    if data_type == 0x00:
        return 1
    elif data_type == 0x01:
        return 2
    elif data_type == 0x02:
        return 3
    elif data_type == 0x03:
        return 4
    elif data_type == 0x04:
        return 8
    elif data_type == 0x05:
        return 1
    elif data_type == 0x06:
        return 2
    elif data_type == 0x07:
        return 3
    elif data_type == 0x08:
        return 4
    elif data_type == 0x09:
        return 8
    elif data_type == 0x0A:
        return 4
    elif data_type == 0x0B:
        return 8
    elif data_type == 0x0C:
        return 1
    else:
        return data_type


# Sensor Masks: Is a bit mask indicating what sensors to be Enabled, starting from MSB:
class SensorMasks:
    @classmethod
    def bat_lvl(self) -> int:
        return 1 << 0  # ...0001

    @classmethod
    def temp_amb(self) -> int:
        return 1 << 1  # ...0010

    @classmethod
    def temp_mch(self) -> int:
        return 1 << 2  # ...0100

    @classmethod
    def mic_amb(self) -> int:
        return 1 << 3

    @classmethod
    def mic_mch(self) -> int:
        return 1 << 4

    @classmethod
    def adxl1002_acc(self) -> int:
        return 1 << 5

    @classmethod
    def adxl362_x_acc(self) -> int:
        return 1 << 6

    @classmethod
    def adxl362_y_acc(self) -> int:
        return 1 << 7

    @classmethod
    def adxl362_z_acc(self) -> int:
        return 1 << 8

    @classmethod
    def ism330_x_acc(self) -> int:
        return 1 << 9

    @classmethod
    def ism330_y_acc(self) -> int:
        return 1 << 10

    @classmethod
    def ism330_z_acc(self) -> int:
        return 1 << 11

    @classmethod
    def ism330_x_gyr(self) -> int:
        return 1 << 12

    @classmethod
    def ism330_y_gyr(self) -> int:
        return 1 << 13

    @classmethod
    def ism330_z_gyr(self) -> int:
        return 1 << 14

    @classmethod
    def mmc5603_x_mag(self) -> int:
        return 1 << 15

    @classmethod
    def mmc5603_y_mag(self) -> int:
        return 1 << 16

    @classmethod
    def mmc5603_z_mag(self) -> int:
        return 1 << 17

    @classmethod
    def drv425_mag(self) -> int:
        return 1 << 18


def parse_data_to_float(data_type: int, data: bytearray):
    data_out = []

    if data_type == 0x00:  # UINT8
        data_out = [float(b) for b in data]

    elif data_type == 0x01:  # UINT16
        for i in range(0, len(data), 2):
            value = struct.unpack("<H", bytes(data[i : i + 2]))[0]
            data_out.append(float(value))

    elif data_type == 0x02:  # UINT24
        for i in range(0, len(data), 3):
            value = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16)
            data_out.append(float(value))

    elif data_type == 0x03:  # UINT32
        for i in range(0, len(data), 4):
            value = struct.unpack("<I", bytes(data[i : i + 4]))[0]
            data_out.append(float(value))

    elif data_type == 0x04:  # UINT64
        for i in range(0, len(data), 8):
            value = struct.unpack("<Q", bytes(data[i : i + 8]))[0]
            data_out.append(float(value))

    elif data_type == 0x05:  # INT8
        data_out = [float(struct.unpack("b", bytes([b]))[0]) for b in data]

    elif data_type == 0x06:  # INT16
        for i in range(0, len(data), 2):
            value = struct.unpack("<h", bytes(data[i : i + 2]))[0]
            data_out.append(float(value))

    elif data_type == 0x07:  # INT24
        for i in range(0, len(data), 3):
            value = data[i] | (data[i + 1] << 8) | (data[i + 2] << 16)
            if value & 0x800000:
                value |= -1 << 24  # Sign extension
            data_out.append(float(value))

    elif data_type == 0x08:  # INT32
        for i in range(0, len(data), 4):
            value = struct.unpack("<i", bytes(data[i : i + 4]))[0]
            data_out.append(float(value))

    elif data_type == 0x09:  # INT64
        for i in range(0, len(data), 8):
            value = struct.unpack("<q", bytes(data[i : i + 8]))[0]
            data_out.append(float(value))

    elif data_type == 0x0A:  # FLOAT
        for i in range(0, len(data), 4):
            value = struct.unpack("<f", bytes(data[i : i + 4]))[0]
            data_out.append(value)

    elif data_type == 0x0B:  # DOUBLE
        for i in range(0, len(data), 8):
            value = struct.unpack("<d", bytes(data[i : i + 8]))[0]
            data_out.append(float(value))

    else:
        raise ValueError("Unknown byte value")

    return data_out


# TODO: Make universal function which can take the dev configs as parameter
def scale_data(sensor_dict, zero_offset, scale_factor):

    scaled_dict = {}

    for key, value in sensor_dict.items():
        scaled_data = [(x - zero_offset) * scale_factor for x in value["data"]]
        # Create a copy of the original dict and replace 'data' with scaled_data
        scaled_entry = value.copy()
        scaled_entry["data"] = scaled_data
        scaled_dict[key] = scaled_entry

    return scaled_dict
