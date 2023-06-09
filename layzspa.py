#!/usr/bin/python3
# -*- coding: utf-8 -*-

import requests, json, time, os.path
import paho.mqtt.client as paho
import threading
from configparser import ConfigParser
import argparse

# Set default configfile
configfile = 'config.ini'

class layzspa():
    def __init__(self):
        self.spadata = {}         # stores device data received from device
        self.config = None
        self.client = None

        self.load_settings()      # dont remove! it loads all settings

    def load_settings(self):
        # Validate that configuration file exists
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),configfile)
        if (os.path.isfile(path) == False):
            print(f'Cannot find configfile: {configfile}')
            exit(1)
        # Read config
        self.config = ConfigParser()
        self.config.read(path)
        self.client = None
        self.api = self.config.get("Layzspa", 'api')
        self.email = self.config.get("Layzspa", 'email')
        self.password = self.config.get("Layzspa", 'password')
        self.gizwits_appid = self.config.get("Layzspa", 'gizwits_appid')
        self.did = self.config.get("Layzspa", 'did')
        self.api_token = self.config.get("Layzspa", 'api_token')
        self.mqtt_host = self.config.get("MQTT", 'host')
        self.mqtt_user = self.config.get("MQTT", 'user')
        self.mqtt_password = self.config.get("MQTT", 'password')
        self.mqtt_client = self.config.get("MQTT", 'client')
        self.mqtt_rootTopic = self.config.get("MQTT", 'rootTopic')

        self.api_data = self.api + '/devdata/' + self.did + '/latest'
        self.api_login = self.api + '/login'
        self.api_binding = self.api + '/bindings?limit=20&skip=0'
        self.api_control = self.api + '/control/' + self.did

    def sendMQTT(self, topic, data):
        # Function to send a message to the MQTT Broker
        pub_topic = self.mqtt_rootTopic + "/" + topic
        self.client.publish(pub_topic, json.dumps(data))
        print('Sent data to topic:'+pub_topic)

    def get_lazyspa_secrets(self):
        pass_flag = False
        payload = '{"username": "'+self.email+'", "password": "'+self.password+'"}'
        headers = {
            'X-Gizwits-Application-Id': self.gizwits_appid,
            'Content-Type': 'text/plain'
        }
        response = requests.request("POST", self.api_login, headers=headers, data=payload, timeout=3)
        data = response.json()
        if response.status_code == 200:
            if 'token' in data:
                self.api_token = data['token']
                self.config['Layzspa']['api_token'] = self.api_token  # update
                if 'uid' in data:
                    self.uid = data['uid']
                    self.config['Layzspa']['uid'] = self.uid  # update
                    pass_flag = True
        else:
            print('Getting secrets: API error: ' + json.dumps(data))
            pass_flag = False

        payload = {}
        headers = {
            'X-Gizwits-Application-Id': self.gizwits_appid,
            'X-Gizwits-User-token': self.api_token
        }
        response = requests.request("GET", self.api_binding, headers=headers, data=payload, timeout=3)
        data = response.json()
        if response.status_code == 200:
            if 'devices' in data:
                if 'did' in data['devices'][0]:         # returns a list of devices
                    self.did = data['devices'][0]['did']
                    self.config['Layzspa']['did'] = self.did  # update
                    pass_flag = True
        else:
            print('Getting secrets: API error: '+json.dumps(data))
            pass_flag = False
        if pass_flag:
            print('Got secrets, writing to '+configfile)
            with open(configfile, 'w') as cfg:  # save new data
                self.config.write(cfg)
            self.load_settings()      # load new settings
        else:
            return 1

    def mqtt_disconnect(self):
        if self.client:
            self.client.disconnect()
            self.client.loop_stop()
            self.client = None

    def connect_to_mqtt(self):
        # Connect to the MQTT Broker
        self.client = paho.Client(self.mqtt_client)
        self.client.on_message = self.on_message
        self.client.on_connect = self.on_connect
        if self.mqtt_user and self.mqtt_password:
            self.client.username_pw_set(self.mqtt_user, self.mqtt_password)
        print(f'Connecting to MQTT broker: {self.mqtt_host}')
        self.client.connect(self.mqtt_host)

    def on_connect(self, mqttc, obj, flags, rc):
        if rc == 0:
            print("Connected to MQTT Broker!")
            mqttc.subscribe(self.config['MQTT']['cmdtopic']+'/#')
        else:
            print('Couldn´t connect to broker, returned:'+str(rc))

    def on_message(self, mqttc, obj, msg):
        print(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))          # topic example: /layzspa/cmd/power
        if self.config['MQTT']['cmdtopic'] in msg.topic:
            cmd = msg.topic.split('/')[-1]      # get last element from list
            payload = str(msg.payload.decode('utf-8'))
            self.layzspa_setcmd(cmd, payload)

    def get_data_interval(self):
        interval = int(self.config['MQTT']['get_data_interval'])
        if interval < 600:
            interval = 600
        while 1:
            time.sleep(interval)
            self.layzspa_get_devinfo()
            self.mqtt_pub_data()

    def layzspa_login_check(self):
        if (self.did is None or self.api_token is None or self.did == '' or self.api_token == '') and (self.email and self.password):
            self.get_lazyspa_secrets()
        elif self.did and self.api_token:
            print("LazySpa API config is OK")
        else:
            print("You have to define either did and api_token, or email and password..")
            exit(1)

    def layzspa_get_devinfo(self):
        # LazySpa API calls
        headers = {
            'X-Gizwits-Application-Id': self.gizwits_appid,
            'X-Gizwits-User-token': self.api_token
        }
        print('Getting device info...')
        response = requests.request("GET", self.api_data, headers=headers, timeout=3)
        if response.status_code != 200 or response.json() == None:
            print(f'Response from API was not OK, exiting.. {response.status_code}')
        self.spadata = response.json()
        if 'attr' in self.spadata:
            #print('Got device info:'+json.dumps(self.spadata, indent=4))
            if self.spadata['attr']['power'] == 0:
                print(f'SPA is online but powered off .. power status from api is: ' + str(self.spadata['attr']['power']))
        else:
            print('No data received! Status from api is: '+json.dumps(self.spadata, indent=4))

    def layzspa_setcmd(self, cmd, payload):
        if payload.isnumeric:
            payload = int(payload)
        else:
            payload = str(payload)
        #print(type(payload), payload)
        data = {"attrs": {cmd:payload}}
        headers = {
            'X-Gizwits-Application-Id': self.gizwits_appid,
            'X-Gizwits-User-token': self.api_token,
            'Content-Type': 'text/plain'
        }
        response = requests.request("POST", self.api_control, headers=headers, json=data)
        if response.json() == {}:
            print('Cmd Response OK!')
        else:
            print('Cmd Response NOT OK! Response:'+response.text)

    def mqtt_pub_data(self):
        if self.client:
            if 'attr' in self.spadata:
                self.sendMQTT('info', self.spadata['attr'])

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    # Add arguments
    parser.add_argument('--getsecrets', action='store_true', help='Gets and saves token and DID automatically.')
    parser.add_argument('--mqttupdate', action='store_true', help='Gets device information and publish it to mqtt broker.')
    parser.add_argument('--getdata', action='store_true', help='Gets and prints device information.')
    parser.add_argument('--cmd', type=str, nargs=2, metavar=('command', 'value'), help='Sends a command with value to device.')
    parser.add_argument('--loop', action='store_true', help='Create a MQTT Loop to receive MQTT commands and send them to the spa.')
    # Parse the arguments
    args = parser.parse_args()

    spa = layzspa()

    if spa.layzspa_login_check():
        exit(1)

    if args.getsecrets:
        spa.layzspa_login_check()

    if args.mqttupdate:
        spa.connect_to_mqtt()
        spa.layzspa_get_devinfo()
        spa.mqtt_pub_data()
        spa.mqtt_disconnect()

    if args.getdata:
        spa.layzspa_get_devinfo()
        if spa.spadata:
            print(json.dumps(spa.spadata, indent=2))

    if args.cmd:
        args.cmd[1] = int(args.cmd[1])
        spa.layzspa_setcmd(args.cmd[0], args.cmd[1])

    if args.loop:
        spa.connect_to_mqtt()
        spa.layzspa_get_devinfo()
        spa.mqtt_pub_data()
        spa.client.loop_start()
        spa.get_data_interval()         # refresh data every X seconds

