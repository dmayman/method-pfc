#! /bin/bash

sudo systemctl stop hostapd
sudo systemctl stop dnsmasq

sudo cp $OPENAG_BRAIN_ROOT/scripts/raspi-network-configs/dhcpcd.conf.noap /etc/dhcpcd.conf
sudo service dhcpcd restart

