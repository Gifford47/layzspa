# layzspa
A Script to get/set data to/from bestway/intex whirlpools

```
usage: layzspa.py [-h] [--getsecrets] [--mqttupdate] [--getdata] [--cmd command value] [--loop]

optional arguments:
  -h, --help           show this help message and exit
  --getsecrets         Gets and saves token and DID automatically.
  --mqttupdate         Gets device information and publish it to mqtt broker.
  --getdata            Gets and prints device information.
  --cmd command value  Sends a command with value to device.
  --loop               Create a MQTT Loop to receive MQTT commands and send them to the spa.
```
