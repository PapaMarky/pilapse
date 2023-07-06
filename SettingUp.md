
## Useful Commands
### Running Timelapse
Run `picamera2_examples/get_sensor_modes.py` to get an idea of the Width and Height to use. If you have a big battery or are plugged in,
use the highest resolution.

### Max Resolutions for Cameras
#### HQ Camera (imx477)
| # | size       | exp. limits     | crop limits             |
|---|------------|-----------------|-------------------------|
| 0 | 1332x990   |  31 - 667234896 |   696   528  2664  1980 |
| 1 | 2028x1080  |  60 - 674181621 |     0   440  4056  2160 |
| 2 | 2028x1520  |  60 - 674181621 |     0     0  4056  3040 |
| 3 | 4056x3040  | 114 - 694422939 |     0     0  4056  3040 |
```agsl
export WIDTH=4056
export HEIGHT=3040
```
##### V3-wide: imx708_wide
| # | size       | exp. limits     | crop limits             |
|---|------------|-----------------|-------------------------|
| 0 | 1536x864   |   9 -  77193582 |   768   432  3072  1728 |
| 1 | 2304x1296  |  13 - 112015443 |     0     0  4608  2592 |
| 2 | 4608x2592  |  26 - 220417486 |     0     0  4608  2592 |
```agsl
export WIDTH=4608
export HEIGHT=2592
```
##### V2 noir: imx219
| #  | size       | exp. limits     | crop limits             |
|----|------------|-----------------|-------------------------|
| 0  | 640x480    |  75 -  11766829 |  1000   752  1280   960 |
| 1  | 1640x1232  |  75 -  11766829 |     0     0  3280  2464 |
| 2  | 1920x1080  |  75 -  11766829 |   680   692  1920  1080 |
|  3 | 3280x2464  |  75 -  11766829 |     0     0  3280  2464 |
| 4  | 640x480    |  75 -  11766829 |  1000   752  1280   960 |
| 5  | 1640x1232  |  75 -  11766829 |     0     0  3280  2464 |
| 6  | 1920x1080  |  75 -  11766829 |   680   692  1920  1080 |
| 7  | 3280x2464  |  75 -  11766829 |     0     0  3280  2464 |
```agsl
export WIDTH=3208
export HEIGHT=2464
```

or use 1080p size
```agsl
export WIDTH=1920
export HEIGHT=1080
```
for setting up, use one of the lower resolutions:

4:6
```agsl
export WIDTH=640
export HEIGHT=480
```
16:9
```agsl
export WIDTH=690
export HEIGHT=540
```
Setup where you want the frames to go:
```
export FRAMEDIR=$(date +'%Y%m%d-timelapse')
export FRAMEDIR=$(date +'%Y%m%d-night')
export FRAMEDIR=$(date +'%Y%m%d-TEST')
```

Open two terminal windows, use `screen -a` so the program isn't killed when
your laptop goes to sleep.
```
picamera2_examples/timelapse_stills.py -W $WIDTH -H $HEIGHT --framerate 0.3 --framedir ../exposures/$FRAMEDIR

python setup_app2/timelapse_helper.py --port 8888 --framedir exposures/$FRAMEDIR
```


##### Mount / Unmount thumbdrive
```agsl
  sudo mount /dev/sda1 /mnt
  sudo umount /mnt
```

##### Move images to thumbdrive
```agsl
sudo rsync --remove-source-files -avzh --no-perms --no-owner --no-group ~/exposures/XXXX /mnt/picam004
```

##### WiFi control
* Turn off wifi to save battery on Rpi 4 (or remove WiFi from USB)
* make sure you have an ethernet cable and any adapters.

```
sudo ifconfig wlan0 down
sudo ifconfig wlan0 up
```
Rebooting will turn the WiFi back on if you do not do the following:
```agsl
#  setup crontab to always turn WiFi off:
sudo crontab -e
```

add this line: 
```
@reboot ifconfig wlan0 down
```

FUTURE: write a script that checks for a file (/home/pi/NOWIFI) and shuts off wifi at boot if the file exists

Just in case: IP addresses of Pis on ad-hoc network

|  Device         | Ip Address     |
|-----------------|----------------|
| picam003.local  | 169.254.86.13  |
| picam004.local  | 169.254.218.35 |
| picamnoir.local | 169.254.102.94 |
