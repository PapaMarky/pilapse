#! /bin/bash
. $(hostname)-timelapse.sh

### all commented lines need to be at the end or lines get ignored
CMD="python3 ./timelapse.py --outdir $OUTDIR --width $WIDTH --height $HEIGHT --zoom $ZOOM"
CMD="${CMD} --prefix $PREFIX --framerate $FRAMERATE "

if [[ ! -z $NFRAMES ]]; then
  CMD="$CMD --nframes $NFRAMES "
fi

if [[ ! -z $TESTFRAME ]]; then
  CMD="$CMD --testframe "
fi

if [[ ! -z $SHOWNAME ]]; then
  CMD="$CMD --show-name "
fi

echo "CMD: $CMD"

$($CMD)

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
