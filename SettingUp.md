## Useful Commands
### Running Timelapse
Run `picamera2_examples/get_sensor_modes.py` to get an idea of the Width and Height to use. If you have a big battery or are plugged in,
use the highest resolution.

### Settings Hints
For night sky timelapse use 25 second exposure time to reduce star blurring.
Aperture f/2.8 or lower

### Max Resolutions for Cameras
#### HQ Camera (imx477)

<table>
<tr><th>#</th><th>Size</th><th colspan=2>Exposure Limits</th><th colspan=4>Crop Limits</th></tr>
<tr>
<td rowspan=2>0</td>
<td rowspan=2>1332 x 990</td>
<td>31</td><td>667234896</td>
<td rowspan=2>696</td><td rowspan=2>528</td><td rowspan=2>2664</td><td rowspan=2>1980</td>

</tr>
<tr><td>0.000031</td><td>667.23</td></tr>
<tr>
<td rowspan=2>1</td>
<td rowspan=2>2028 x 1080</td>
<td>60</td><td>674181621</td>
<td rowspan=2>0</td><td rowspan=2>440</td><td rowspan=2>4056</td><td rowspan=2>2160</td>

</tr>
<tr><td>0.000060</td><td>674.18</td></tr>
<tr>
<td rowspan=2>2</td>
<td rowspan=2>2028 x 1520</td>
<td>60</td><td>674181621</td>
<td rowspan=2>0</td><td rowspan=2>0</td><td rowspan=2>4056</td><td rowspan=2>3040</td>

</tr>
<tr><td>0.000060</td><td>674.18</td></tr>
<tr>
<td rowspan=2>3</td>
<td rowspan=2>4056 x 3040</td>
<td>114</td><td>694422939</td>
<td rowspan=2>0</td><td rowspan=2>0</td><td rowspan=2>4056</td><td rowspan=2>3040</td>

</tr>
<tr><td>0.000114</td><td>694.42</td></tr>
</table>

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
| # | size       | exp. limits          | crop limits             |
|---|------------|----------------------|-------------------------|
| 0 | 1536x864   |        9 -  77193582 |   768   432  3072  1728 |
|   |            | 0.000009 -     77.19 |                         |
| 1 | 2304x1296  |       13 - 112015443 |     0     0  4608  2592 |
|   |            | 0.000013 -    112.02 |                         |
| 2 | 4608x2592  |       26 - 220417486 |     0     0  4608  2592 |
|   |            | 0.000026 -    220.42 |                         |

<table>
<tr><th>#</th><th>Size</th><th colspan=2>Exposure Limits</th><th colspan=4>Crop Limits</th></tr>
<tr>
<td rowspan=2>0</td>
<td rowspan=2>1536 x 864</td>
<td>9</td><td>77193582</td>
<td rowspan=2>768</td><td rowspan=2>432</td><td rowspan=2>3072</td><td rowspan=2>1728</td>

</tr>
<tr><td>0.000009</td><td>77.19</td></tr>
<tr>
<td rowspan=2>1</td>
<td rowspan=2>2304 x 1296</td>
<td>13</td><td>112015443</td>
<td rowspan=2>0</td><td rowspan=2>0</td><td rowspan=2>4608</td><td rowspan=2>2592</td>

</tr>
<tr><td>0.000013</td><td>112.02</td></tr>
<tr>
<td rowspan=2>2</td>
<td rowspan=2>4608 x 2592</td>
<td>26</td><td>220417486</td>
<td rowspan=2>0</td><td rowspan=2>0</td><td rowspan=2>4608</td><td rowspan=2>2592</td>

</tr>
<tr><td>0.000026</td><td>220.42</td></tr>
</table>



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
export FRAMEDIR=$(date +'%Y%m%d-timelapse-'$(hostname))
```
```
export FRAMEDIR=$(date +'%Y%m%d-night-'$(hostname))
```
```
export FRAMEDIR=$(date +'%Y%m%d-TEST-'$(hostname))
```

Open two terminal windows, use `screen -a` so the program isn't killed when
your laptop goes to sleep.

##### Setting Up
```
picamera2_examples/timelapse_stills.py -W $WIDTH -H $HEIGHT --nr off --framerate 0.3 --framedir ../exposures/$FRAMEDIR
```
##### Setup Helper
```
setup_app2/timelapse_helper.py --port 8888 --framedir exposures/$FRAMEDIR
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
