#!/bin/sh
export LOGFILE=nightrun.log

./nightpi.py \
       --outdir /home/pi/exposures/$(hostname)'/%Y%m%d-nightrun' \
       --filename '%Y%m%d_%H%M%S_%ISO%_%SHUTTER%_%TIMEOFDAY%' \
       --settings ./camera_settings.json \
       --sleep 40 \
       --zoom 1
