#!/usr/bin/env sh

/Users/mark/Library/Python/3.8/bin/pyreverse -o pdf ./threads.py ./camera.py ./config.py ./motion.py \
  ./camera_producer.py ./scheduling.py
open classes.pdf