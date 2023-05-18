#! /bin/bash

source ./$(hostname)-motion.sh

### all commented lines need to be at the end or lines get ignored

python3 ./motion.py \
	--outdir ../exposures/$(hostname)-TEST-%Y%m%d \
	--width $WIDTH --height $HEIGHT \
	--zoom $ZOOM \
	--top $TOP \
	--bottom $BOTTOM \
	--left $LEFT \
	--right $RIGHT \
	--mindiff $MINDIFF \
	--threshold $THRESHOLD \
	--dilation $DILATION \
	--show-name \
	--prefix $(hostname) \
	--show-motion \
	--testframe \
	--nframes 3 \
#	--loglevel debug \
#	--save-diffs \
#	--debug \
#	--stop-at '20:30:00' \
#	--all-frames \
#	--shrinkto 640 \
#	--save-config \
#	--show-name --label-rgb 0,0,0 \
