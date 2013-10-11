biketl
======

Script for creating timelapse videos with overlaid metrics from Garmin .FIT files.

Draws graphs of Garmin data (speed, HR, cadence, elevation) along with a Google
map of position (updated every 10th of a mile). Google Maps has some very
aggressive rate limits, which means this script has to sleep _a lot_ and
frequently fail.  Fortunately, files are staged, and it can pick up where it
left off.

Relies on the EXIF data from the timelapse files to match the track up with the
images.

Outputs a whole bunch of files to the staging directory (specified by
`--stagingdir`), which you can then stitch together into a video with
mencoder:

`mencoder "mf://merged-*.JPG" -mf fps=12 -o output.avi -ovc lavc -lavcopts vcodec=mpeg4:mbd=2:trell:vbitrate=7000`

Tested on Linux with a GoPro Hero3 and a Garmin Edge 500:
https://www.youtube.com/watch?v=Y1VTvU5xEFM

PRE-REQS
--------
sudo apt-get install python-matplotlib
sudo apt-get install imagemagick
sudo apt-get install mencoder
