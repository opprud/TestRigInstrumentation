pip install paho-mqtt

# Status på alle kanaler
python3 shelly_control.py --status

# Tænd CPU (kanal 3)
python3 shelly_control.py --on cpu
python3 shelly_control.py --on 3

# Sluk Heater
python3 shelly_control.py --off heater
python3 shelly_control.py --off 0