#!/bin/bash

function pause(){
	echo $*
	read TMP
}


while true; do
	sleep 1;
	./fe-dev-info.sh
	if [ $? -eq 0 ]; then
		pause "Press any key to continue..."
	fi
done
