# Setting Up for Night Timelapse

## Prep
Things to do before heading out to dark places.
* Power supply
* ethernet cable
* tripod
* turn off Wi-Fi on Raspberry Pi
```shell
sudo rfkill block wifi
```
## Frame n Aim
```shell
cd ~/pilapse
```
```shell
./TimeSync.py --user pi --password $PASSWORD --host picam004.local 
```
```shell
screen -a
```
### HQ
```shell
export FRAMEDIR=$(date +'%Y%m%d-TEST-'$(hostname))
export WIDTH=4056
export HEIGHT=3040
export STOP_AT=5:30:00
export ZOOM=1.0
export GAIN=1.0
```
```shell
# Low res
export FRAMEDIR=$(date +'%Y%m%d-TEST-'$(hostname))
export WIDTH=2028
export HEIGHT=1080
export STOP_AT=5:30:00
export ZOOM=1.0
export GAIN=1.0
```
### V3 wide
```shell
export FRAMEDIR=$(date +'%Y%m%d-TEST-'$(hostname))
export WIDTH=4608
export HEIGHT=2592
export STOP_AT=5:30:00
export ZOOM=1.0
export GAIN=1.0
```
```shell
# low res
export FRAMEDIR=$(date +'%Y%m%d-TEST-'$(hostname))
export WIDTH=2304
export HEIGHT=1296
export STOP_AT=5:30:00
export ZOOM=1.0
export GAIN=1.0
```
```shell
picamera2_examples/timelapse_stills.py --zoom $ZOOM -W $WIDTH -H $HEIGHT --nr best --framedir ../exposures/$FRAMEDIR --analog-gain $GAIN --singleshot --notes
```
```shell
setup_app2/timelapse_helper.py --port 8888
```

## Focus on Stars / Choose Exposure
* wait until fully dark

## UPDATE `ZOOM` and `GAIN` variables
## Make Dark Frame
### HQ
```
export FRAMEDIR=$(date +'%Y%m%d-DARK-'$(hostname))
```
### V3 wide
```
export FRAMEDIR=$(date +'%Y%m%d-DARK-'$(hostname))
```
* Cover Lens (lens cap + box)

* Choose framerate and exposure-time

### 5 seconds
```shell
export EXPOSURE_TIME=5000000
export FRAMERATE=0.2
```
### 10 seconds
```shell
export EXPOSURE_TIME=10000000
export FRAMERATE=0.1
```
### 15 seconds
```shell
export EXPOSURE_TIME=15000000
export FRAMERATE=0.066666666666667
```
### 20 seconds
```shell
export EXPOSURE_TIME=20000000
export FRAMERATE=0.05
```
### 25 seconds
```shell
export EXPOSURE_TIME=25000000
export FRAMERATE=0.04
```
### 30 seconds
```shell
export EXPOSURE_TIME=30000000
export FRAMERATE=0.033333333333333
```
## Start DarkFrame
```shell
picamera2_examples/timelapse_stills.py -W $WIDTH -H $HEIGHT --analog-gain $GAIN --nr best --framedir ../exposures/$FRAMEDIR --framerate $FRAMERATE --exposure-time $EXPOSURE_TIME --zoom $ZOOM --notes
```

## Start Timelapse
* echo the command with settings into a file
```shell
screen -a
```
```shell
export FRAMEDIR=$(date +'%Y%m%d-nightsky-'$(hostname))
```

```shell
picamera2_examples/timelapse_stills.py -W $WIDTH -H $HEIGHT --analog-gain $GAIN --nr best --framedir ../exposures/$FRAMEDIR --stop-at $STOP_AT --poweroff --notes --framerate $FRAMERATE --exposure-time $EXPOSURE_TIME --zoom $ZOOM
```

# Appendix 

## HQ Camera
<b>Camera Model: imx477</b>
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
<b>Camera Controls</b><br/>
<table>
<tr><th>Control</th><th>Min</th><th>Max</th><th>Default</th></tr>
<tr><td>AfMode</td><td colspan="3">Not Available</td></tr>
<tr><td>LensPosition</td><td colspan="3">Not Available</td></tr>
<tr><td>AeEnable</td><td>False</td><td>True</td><td>None</td></tr>
<tr><td>AeExposureMode</td><td>AeExposureModeEnum.Normal</td><td>AeExposureModeEnum.Custom</td><td>AeExposureModeEnum.Normal</td></tr>
<tr><td>AeConstraintMode</td><td>AeConstraintModeEnum.Normal</td><td>AeConstraintModeEnum.Custom</td><td>AeConstraintModeEnum.Normal</td></tr>
<tr><td>AwbEnable</td><td>False</td><td>True</td><td>None</td></tr>
<tr><td>AwbMode</td><td>AwbModeEnum.Auto</td><td>AwbModeEnum.Custom</td><td>AwbModeEnum.Auto</td></tr>
<tr><td>AnalogueGain</td><td>1.0</td><td>22.2608699798584</td><td>None</td></tr>
</table>

# V3 Wide NoIR Camera (same as V3 Wide)
<b>Camera Model: imx708_wide_noir</b>
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
<b>Camera Controls</b><br/>
<table>
<tr><th>Control</th><th>Min</th><th>Max</th><th>Default</th></tr>
<tr><td>AfMode</td><td>AfModeEnum.Manual</td><td>AfModeEnum.Continuous</td><td>AfModeEnum.Manual</td></tr>
<tr><td>LensPosition</td><td>0.0</td><td>32.0</td><td>1.0</td></tr>
<tr><td>AeEnable</td><td>False</td><td>True</td><td>None</td></tr>
<tr><td>AeExposureMode</td><td>AeExposureModeEnum.Normal</td><td>AeExposureModeEnum.Custom</td><td>AeExposureModeEnum.Normal</td></tr>
<tr><td>AeConstraintMode</td><td>AeConstraintModeEnum.Normal</td><td>AeConstraintModeEnum.Custom</td><td>AeConstraintModeEnum.Normal</td></tr>
<tr><td>AwbEnable</td><td>False</td><td>True</td><td>None</td></tr>
<tr><td>AwbMode</td><td>AwbModeEnum.Auto</td><td>AwbModeEnum.Custom</td><td>AwbModeEnum.Auto</td></tr>
<tr><td>AnalogueGain</td><td>1.0</td><td>16.0</td><td>None</td></tr>
</table>
