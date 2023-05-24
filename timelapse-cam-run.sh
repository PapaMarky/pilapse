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

if [[ ! -z $METER_MODE ]]; then
  CMD="$CMD --meter-mode $METER_MODE "
fi

if [[ ! -z $EXPOSURE_MODE ]]; then
  CMD="$CMD --exposure-mode $EXPOSURE_MODE "
fi

if [[ ! -z $TESTFRAME ]]; then
  CMD="$CMD --testframe "
fi

if [[ ! -z $SHOWNAME ]]; then
  CMD="$CMD --show-name "
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
