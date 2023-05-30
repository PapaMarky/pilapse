#! /bin/bash
. $(hostname)-motion.sh

### all commented lines need to be at the end or lines get ignored
CMD="python3 ./motion.py --outdir $OUTDIR --width $WIDTH --height $HEIGHT --zoom $ZOOM --top $TOP --bottom $BOTTOM"
CMD="${CMD} --left $LEFT --right $RIGHT --mindiff $MINDIFF --threshold $THRESHOLD --dilation $DILATION --prefix $PREFIX"

if [[ ! -z $TESTFRAME ]]; then
  CMD="$CMD --testframe \
  "
fi

if [[ ! -z $NFRAMES ]]; then
  CMD="$CMD --nframes $NFRAMES "
fi

if [[ ! -z $RUN_FROM ]]; then
  CMD="$CMD --run-from $RUN_FROM "
fi

if [[ ! -z $RUN_UNTIL ]]; then
  CMD="$CMD --run-until $RUN_UNTIL "
fi

if [[ ! -z $SHOWMOTION ]]; then
  CMD="$CMD --show-motion \
  "
fi

if [[ ! -z $SHOWNAME ]]; then
  CMD="$CMD --show-name \
  "
fi

if [[ ! -z $SHOW_CAMERA_SETTINGS ]]; then
  CMD="$CMD --show-camera-settings \
  "
fi

if [[ ! -z $CAMERA_SETTINGS_LOG ]]; then
  CMD="$CMD --camera-settings-log $CAMERA_SETTINGS_LOG \
  "
fi

if [[ ! -z $METER_MODE ]]; then
  CMD="$CMD --meter-mode $METER_MODE "
fi

if [[ ! -z $EXPOSURE_MODE ]]; then
  CMD="$CMD --exposure-mode $EXPOSURE_MODE "
fi

if [[ ! -z LABEL_RGB ]]; then
  CMD="$CMD --label-rgb $LABEL_RGB"
fi

echo "CMD: $CMD"

$CMD

#	--loglevel debug \
#	--testframe \
#	--nframes 3 \
#	--save-diffs \
#	--debug \
#	--stop-at '20:30:00' \
#	--all-frames \
#	--shrinkto 640 \
#	--save-config \
#	--show-name --label-rgb 0,0,0 \
