#! /bin/bash
. $(hostname)-timelapse.sh

CMD="python3 ./stream-test.py --width $WIDTH --height $HEIGHT --zoom $ZOOM --sensor-mode $SENSOR_MODE "

echo "$CMD"

$CMD
