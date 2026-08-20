# Bearing Brain Gateway Emulator

The purpose of the emulator is to implement the BLE protocol facilitating communication and data capture from the bearing brain sensor.
In particular the audible data from the ultrasound microphone is of interest.

## Organisation
Source files are cloned directly from the bearing brain gateway project, and a toplevel application file `run_sampler.py`allows capture from the sensing device.


├── ble_debug_scan.py
├── gateway-service-ble
├── gateway-service-device-configs
├── gateway-service-measurement-creator
├── pdm_mic_config.json
├── plot_samples.py
├── readme.md
├── requirements_local.txt
├── run_sampler.py
├── run_sensor_tests.sh
├── samples
├── temp_amb_mic_config.json
└── test_configs

In addition a few utility files are provided

`ble_debug_scan.py` allows scanning the BLE interface for devices

## Example usage
BLE Scan

(base) au263437@d57733 BearingBrainGWEmulator % python ble_debug_scan.py

======================================================================
Scanning for 15.0s... (11:20:24)
======================================================================



[(no name)]
  Address:          D76128A3-3C1F-4446-42DE-5BA770A07BD2
  Name (cached):    (none)
  Name (adv):       (none)
  RSSI:             -39 dBm
  Manufacturer:     0x004C -> 12020001
                    ASCII: ....

[Packet] <<<
  Address:          39374AAD-6DAC-F9C6-C027-434A14819274
  Name (cached):    Packet
  Name (adv):       OE00031204100074
  RSSI:             -45 dBm
  *** NAME MISMATCH: cached='Packet' vs adv='OE00031204100074' ***
  Service UUIDs:    0000180a-0000-1000-8000-00805f9b34fb
  Manufacturer:     0xFFFF -> 
                    ASCII: 


Here our 'OExxxxxxxxxx'device name is cached as 'Packet', and is the device with adv OE00031204100074

Data Capture

python run_sampler.py

## Device firmware 
the device can be build with standard firmware, sampling the SPH641UL microphone a 100Ksps, or a custom firmware allowing the PDM microphone to be utilised upto 80KHz.

---

<!-- Everything below this line is a note from the TestRig side, not part of the vendor readme. -->

## Note for the rig: this copy is partial (added 2026-08-20)

The tree here holds 8 of the 13 items the listing above names. **Missing:**
`gateway-service-device-configs`, `gateway-service-measurement-creator`, `pdm_mic_config.json`,
`temp_amb_mic_config.json` — and, until now, this readme.

Nothing in the capture path depends on the missing files. The one that will be wanted eventually
is **`pdm_mic_config.json`**, which `plot_samples.py` takes via `-c` to get the correct sample
rates into an FFT — mic data analysed without it will have the wrong frequency axis.

**Read the scan example above before calling anything a fault.** The device advertising as
`OE00031204100074` while caching the name `Packet`, exposing only service `0x180a`, and carrying
an empty `0xFFFF` manufacturer field is the **documented normal state**, and `ble_debug_scan.py`
prints its `NAME MISMATCH` line routinely. It was briefly mistaken for evidence of a wedged
device on 2026-08-19; it is not evidence of anything. See ticket 0019.

**Two firmware variants exist** (see *Device firmware* above): standard, sampling the SPH641UL at
100 ksps, and a custom build driving the PDM microphone up to 80 kHz. Which one a given unit runs
determines the mic sample rate, so it has to be known before mic data can be interpreted — and it
is worth asking BearingBrain which is on our unit when raising the other questions with them.
