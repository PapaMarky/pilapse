#! /bin/bash
. $(hostname)-timelapse.sh

### all commented lines need to be at the end or lines get ignored
CMD="python3 ./timelapse.py --outdir $OUTDIR --width $WIDTH --height $HEIGHT --zoom $ZOOM"
CMD="${CMD} --prefix $PREFIX --framerate $FRAMERATE "

if [[ ! -z $NFRAMES ]]; then
  CMD="$CMD --nframes $NFRAMES "
fi

if [[ ! -z $RUN_FROM ]]; then
  CMD="$CMD --run-from $RUN_FROM "
fi

if [[ ! -z $RUN_UNTIL ]]; then
  CMD="$CMD --run-until $RUN_UNTIL "
fi

if [[ ! -z $STOP_AT ]]; then
  CMD="$CMD --stop-at $STOP_AT"
fi

if [[ ! -z $METER_MODE ]]; then
  CMD="$CMD --meter-mode $METER_MODE "
fi

if [[ ! -z $EXPOSURE_MODE ]]; then
  CMD="$CMD --exposure-mode $EXPOSURE_MODE "
fi

if [[ ! -z $AWB_MODE ]]; then
  CMD="$CMD --awb-mode $AWB_MODE "
fi

if [[ ! -z $TESTFRAME ]]; then
  CMD="$CMD --testframe "
fi

### Does this make sense?
if [[ ! -z $TESTFRAME_NOGRID ]]; then
  CMD="$CMD --testframe-nogrid "
fi

if [[ ! -z $SHOWNAME ]]; then
  CMD="$CMD --show-name "
fi

if [[ ! -z $SHOW_CAMERA_SETTINGS ]]; then
  CMD="$CMD --show-camera-settings \
  "
fi

if [[ ! -z $CAMERA_SETTINGS_LOG ]]; then
  CMD="$CMD --camera-settings-log $CAMERA_SETTINGS_LOG \
  "
fi

if [[ ! -z $AUTO_CAM ]]; then
  CMD="$CMD --auto-cam \
  "
fi

if [[ ! -z $NIGHTSKY ]]; then
  CMD="$CMD --nightsky \
  "
fi

if [[ ! -z $ISO ]]; then
  CMD="$CMD --iso $ISO \
  "
fi

# location=(37.255329186920946, -121.94417304596949)
if [[ ! -z $LOCATION ]]; then
  CMD="$CMD --location $LOCATION \
  "
fi

if [[ ! -z $LABEL_RGB ]]; then
  CMD="$CMD --label-rgb $LABEL_RGB"
fi

if [[ ! -z $LOGLEVEL ]]; then
  CMD="$CMD --loglevel $LOGLEVEL "
fi

if [[ ! -z $ROTATE ]]; then
    CMD="$CMD --rotate $ROTATE "
fi

echo "CMD: $CMD"

$CMD

#	--loglevel debug \
#	--testframe \
#	--save-diffs \
#	--debug \
#	--stop-at '20:30:00' \
#	--all-frames \
#	--shrinkto 640 \
#	--save-config \
