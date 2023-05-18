#! /bin/bash
. $(hostname)-motion.sh

### all commented lines need to be at the end or lines get ignored
CMD=python3 ./motion.py \
	--outdir "$OUTDIR" \
	--width $WIDTH --height $HEIGHT  \
	--zoom $ZOOM \
	--top $TOP \
	--bottom $BOTTOM \
	--left $LEFT \
	--right $RIGHT \
	--mindiff $MINDIFF \
	--threshold $THRESHOLD \
	--dilation $DILATION \
	--prefix $PREFIX \

if [[ ! -z $SHOWMOTION ]]; then
  CMD = "$CMD	--show-motion \
  "
fi
if [[ ! -z $SHOWNAME ]]; then
  CMD = "$CMD	--show-name \
  "
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
