#!/bin/bash

# Simple tool to get the information about the FEUSB device

# Usage: fe-dev-info.sh [ /dev/ttyACM* | /dev/fercs* ]

DEV=/dev/ttyACM0

if [ ! -c $DEV ]; then
	exit 1
fi

if [ $# -gt 0 ]; then
	DEV=$1
	echo "Using DEV $1"
fi

SEARCH="(idVendor|idProduct|bcdDevice|manufacturer|product|serial)"
GETINFO="/sbin/udevadm info -a -p $(/sbin/udevadm info -q path -n /dev/ttyACM0)"


$GETINFO | egrep $SEARCH | head -n6
