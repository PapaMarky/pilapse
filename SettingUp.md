## Useful Commands
### Running Timelapse
Run `picamera2_examples/get_sensor_modes.py` to get an idea of the Width and Height to use. If you have a big battery or are plugged in,
use the highest resolution.

### Settings Hints
For night sky timelapse use 25 second exposure time to reduce star blurring.
Aperture f/2.8 or lower

### Max Resolutions for Cameras
#### HQ Camera (imx477)

Lenses:
* 16mm 10MP Telephot: Focal length: 16mm, Aperture: F1.4–16
* 6mm 3MP Wide Angle:
```agsl
export WIDTH=2028
export HEIGHT=1080
```
```agsl
export WIDTH=4056
export HEIGHT=3040
```


##### V3-wide: imx708_wide

```agsl
export WIDTH=4608
export HEIGHT=2592
```
##### V2 noir: imx219
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
export FRAMEDIR=$(date +'%Y%m%d-night-'$(hostname))
```

Open two terminal windows, use `screen -a` so the program isn't killed when
your laptop goes to sleep.

##### Setting Up
```
export FRAMEDIR=$(date +'%Y%m%d-TEST-'$(hostname))
```
```
picamera2_examples/timelapse_stills.py -W $WIDTH -H $HEIGHT --nr off --framerate 0.3 --framedir ../exposures/$FRAMEDIR --singleshot
```
##### Setup Helper
```
setup_app2/timelapse_helper.py --port 8888
```

##### Create Dark Frames
```
export FRAMEDIR=$(date +'%Y%m%d-DARK-'$(hostname))
```

##### NightSky (15 seconds) ADD ZOOM
```
picamera2_examples/timelapse_stills.py -W $WIDTH -H $HEIGHT --nr best --framerate 15000000 --framerate 0.0666666667 --framedir ../exposures/$FRAMEDIR --stop-at 5:00:00
```
##### NightSky (25 seconds) ADD ZOOM
```
picamera2_examples/timelapse_stills.py -W $WIDTH -H $HEIGHT --nr best --framerate 25000000 --framerate 0.04 --framedir ../exposures/$FRAMEDIR --stop-at 5:00:00
```


##### Mount / Unmount thumbdrive
```agsl
  sudo mount /dev/sda1 /mnt
  sudo umount /mnt
```

##### Move images to thumbdrive
Use `--remove-source-files` at your own peril. If copies fail, the files still get removed sometimes.
```agsl
sudo rsync -avzh --no-perms --no-owner --no-group ~/exposures/$FRAMEDIR /mnt/$(hostname)
```

```
sudo rsync --remove-source-files -avzh --no-perms --no-owner --no-group ~/exposures/XXXX /mnt/$(hostname)
```

##### WiFi control
* Turn off wifi to save battery on Rpi 4 (or remove WiFi from USB)
* make sure you have an ethernet cable and any adapters.

```
sudo ifconfig wlan0 down
sudo ifconfig wlan0 up
```

To keep the WiFi off even when rebooting, use these commands:

```agsl
sudo rfkill block wifi
sudo rfkill unblock wifi
```

Rebooting will turn the WiFi back on if you do not do the following: 

**THIS DID NOT WORK FOR ME**
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
