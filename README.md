biketl
======

Script for creating timelapse videos with overlaid metrics from Garmin .FIT files.

Draws graphs of Garmin data (speed, HR, cadence, elevation) along with a Google
map of position (updated every 10th of a mile).

Relies on the EXIF data from the timelapse files to match the track up with the
images.

Tested on Linux with a GoPro Hero3 and a Garmin Edge 500:
https://www.youtube.com/watch?v=Y1VTvU5xEFM

PRE-REQS
--------
sudo apt-get install python-matplotlib
sudo apt-get install imagemagick
