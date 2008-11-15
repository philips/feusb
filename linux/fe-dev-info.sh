#!/bin/sh

# Simple tool to get the information about the FEUSB device

# Usage: sh info.sh [ /dev/ttyACM* | /dev/fercs* ]

DEV=/dev/ttyACM0

SEARCH="(idVendor|idProduct|bcdDevice|manufacturer|product|serial)"
GETINFO="/sbin/udevadm info -a -p $(/sbin/udevadm info -q path -n /dev/ttyACM0)"

if [ $# -gt 0 ]; then
	DEV=$1
	echo "Using DEV $1"
fi

$GETINFO | egrep $SEARCH | head -n6
