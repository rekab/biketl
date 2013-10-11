#!/usr/bin/python
"""Stitch together timelapse images with a Garmin track.

Draws graphs of Garmin data (speed, HR, cadence, elevation) along with a Google
map of position (updated every 10th of a mile).

Relies on the EXIF data from the timelapse files to match the track up with the
images.

Tested on Linux with a GoPro Hero3 and a Garmin Edge 500:
https://www.youtube.com/watch?v=Y1VTvU5xEFM

USAGE:

Do to Google Map's aggressive throttling it's best to put this in a loop.

   while ! python biketl.py --fitfile=garmin_file.fit --imgsrcglob='images/gopro-source/*.JPG' --stagingdir=/tmp/temp-dir  ; do sleep 5m ; done

"""

import argparse
import bisect
import datetime
import glob
import os
import sys
import tempfile
import time
import urllib2

sys.path.append('/home/james/code/biketl/python-fitparse')
sys.path.append('/home/james/code/biketl/motionless/motionless')
sys.path.append('/home/james/code/biketl/exif-py')


from fitparse import activity
from motionless import DecoratedMap, LatLonMarker
from matplotlib import pyplot
from matplotlib import font_manager
from matplotlib.pyplot import np
import EXIF


SEMICIRCLE_RATIO = 180.0/(2**31)
MS_TO_MPH_RATIO = 2.23694
METERS_TO_MILES_RATIO = 0.000621371
METERS_TO_FEET_RATIO = 3.28084
FONT_PATH = '/home/james/code/biketl/zekton.otf'
NUM_GRAPH_POINTS=100


class ImagesAndPointsDoNotOverlap(RuntimeError):
  pass


class NoImagesFound(RuntimeError):
  pass


class NoGPSTrack(RuntimeError):
  pass


def GetPointsFromActivity(filename):
  print 'loading activity %s' % filename
  a = activity.Activity(filename)
  a.parse()
  points = []
  for record in a.get_records_by_type('record'):
    points.append(Point(record))
  return points


class PointList(object):
  def __init__(self, fitfile):
    self._points = GetPointsFromActivity(fitfile)
    self._times = [point.time for point in self._points]

  def __getitem__(self, index):
    return self._points[index]

  def __len__(self):
    return len(self._points)

  def GetIndexNearestTime(self, t):
    if not self._points:
      return None

    left_index = bisect.bisect_left(self._times, t)
    right_index = bisect.bisect_right(self._times, t)
    left, right = None, None

    if left_index >= len(self._points):
      return len(self._points)

    if right_index < len(self._points):
      left = self._points[left_index]
      right = self._points[right_index]
      if (t - left.time) < (right.time - t):
        return left_index
      else:
        return right_index
    return left_index

  def GetPointsNearestTime(self, t, num_points=50):
    index = self.GetIndexNearestTime(t)
    if index is None:
      return None

    return self._points[max(0, index - num_points):index+1]


class Point(object):
  CONVERTER = {
      'semicircles': SEMICIRCLE_RATIO,
      'm/s': MS_TO_MPH_RATIO,
      'm': METERS_TO_FEET_RATIO,
  }
  def __init__(self, record):
    self._record = record

  @property
  def distance(self):
    dist = self._record.get_data('distance')
    if dist:
      return dist * METERS_TO_MILES_RATIO
    return 0

  @property
  def position(self):
    return (self.position_lat, self.position_long)

  @property
  def temp_f(self):
    return self.temperature * 9.0 / 5.0 + 32.0

  def __getattr__(self, field_name):
    data = self._record.get_data(field_name)
    if data is None:
      return 0
    unit_ratio = self.CONVERTER.get(self._record.get_units(field_name), 1)
    return data*unit_ratio

  @property
  def time(self):
    return self._record.get_data('timestamp')

  def __repr__(self):
    return str(self)

  def __str__(self):
    return "Time: %s\nPos: %s\nSpeed: %s mph\nHR: %s bpm\nCAD: %s rpm\nAlt: %s feet\nGrade: %d%%\nDist: %s miles\nTemp: %s" % (
        self.time.ctime(), self.position, self.speed, self.heart_rate,
        self.cadence, self.altitutde, self.grade, self.distance, self.temperature)


class Image(object):
  def __init__(self, filename, timeskew=0):
    self.filename = filename
    self.timeskew = timeskew
    with open(filename, 'r') as f:
      self._tags = EXIF.process_file(f)

  @property
  def time(self):
    ts = str(self._tags['EXIF DateTimeOriginal'])
    return (datetime.datetime.strptime(ts, '%Y:%m:%d %H:%M:%S') +
        datetime.timedelta(0, self.timeskew, 0))


def GetImages(files, timeskew=0):
  """Load images.

  Args:
    files: list of filenames
    timeskew: seconds to add to each EXIF timestamp
  Returns:
    list of Image objects, ordered by exif timestamp (ascending)
  """
  print 'Loading and sorting exif data for %d image files...' % len(files)
  return sorted([Image(f, timeskew=timeskew) for f in files], key=lambda i:i.time)


def GetMapForPoints(output_dir, file_basename, points, mapdelay=3):
  # Map creation is expensive, so check if we've already fetched it.
  map_image_fname = os.path.join(output_dir, 'map-%s.png' % file_basename)
  latest = points[-1]
  if os.path.exists(map_image_fname):
    print 'map already exists for %s' % latest
    return map_image_fname

  print 'getting map for %s' % latest
  gmap = DecoratedMap(size_x=200, size_y=200, pathweight=4, pathcolor='red')
  gmap.add_marker(
      LatLonMarker(*tuple(str(x) for x in points[-1].position), color='red'))
  print 'sleeping %s seconds' % mapdelay
  time.sleep(mapdelay)
  resp = urllib2.urlopen(gmap.generate_url() + '&zoom=11')
  f = open(map_image_fname, 'w')
  f.write(resp.read())
  f.close()
  return map_image_fname


def DrawSpeedLabel(speed, ax):
  if speed > 25:
    font = font_manager.FontProperties(size=14,
        weight='bold',
        fname=FONT_PATH)
  else:
    font = font_manager.FontProperties(size=14,
        fname=FONT_PATH)
  desc = ('%.1f MPH' % speed).rjust(8)
  # I dislike that pyplot is global, it impinges my customary design.
  pyplot.text(0, .90, desc, transform=ax.transAxes, fontproperties=font, color='white')


def DrawHeartRateLabel(hr, ax):
  color = 'white'
  if hr > 165:
    desc = ('%d BPM' % hr).rjust(7)
    font = font_manager.FontProperties(size=14, weight = 'bold',
      fname=FONT_PATH)
    color = 'red'
  else:
    desc = 'Heart Rate (BPM)'
    font = font_manager.FontProperties(size=14, fname=FONT_PATH)

  pyplot.text(0, .90, desc, transform=ax.transAxes, fontproperties=font, color=color)


def GetFontPropertiesForGrade(grade):
  return font_manager.FontProperties(size=14,
      fname=FONT_PATH)


def GetFontPropertiesForCadence(cadence):
  return font_manager.FontProperties(size=14,
      fname=FONT_PATH)

def GetPointForLabel(points):
  """Get a point every few seconds, so that numbers are readable."""
  # TODO: find the last point at a minute boundary
  return points[-1]


def GetLineGraphForPoints(output_dir, file_basename, points):
  """Draw a 1024x160 graph."""
  latest = GetPointForLabel(points)
  figure = pyplot.figure(latest.time.ctime(), figsize=(10.24, 1), dpi=80)

  # TODO: merge speed with cad on the same graph. merge hr with elevation.

  ax = pyplot.subplot(1,4,1, axisbg='black')
  ax.tick_params(axis='y', colors='gray', labelsize=10)
  pyplot.xlim(0, NUM_GRAPH_POINTS)
  pyplot.subplots_adjust(left=0.05, right=1, hspace=0, wspace=0.3)
  pyplot.locator_params(nbins=4)
  pyplot.ylim(0, 30)
  pyplot.gca().get_xaxis().set_visible(False)
  DrawSpeedLabel(latest.speed, ax)
  pyplot.plot([point.speed for point in points], 'g-', linewidth=2)

  ax = pyplot.subplot(1,4,2, axisbg='black')
  ax.tick_params(axis='y', colors='gray', labelsize=10)
  pyplot.xlim(0, NUM_GRAPH_POINTS)
  pyplot.locator_params(nbins=4)
  pyplot.gca().get_xaxis().set_visible(False)
  pyplot.ylim(90, 190)
  DrawHeartRateLabel(latest.heart_rate, ax)
  pyplot.plot([point.heart_rate for point in points], 'r-', linewidth=2)

  ax = pyplot.subplot(1,4,3, axisbg='black')
  ax.tick_params(axis='y', colors='gray', labelsize=10)
  pyplot.xlim(0, NUM_GRAPH_POINTS)
  pyplot.locator_params(nbins=4)
  pyplot.gca().get_xaxis().set_visible(False)
  pyplot.ylim(0, 180)
  #desc = ('%d RPM' % latest.cadence).rjust(7)
  desc = 'Cadence (RPM)'
  font = GetFontPropertiesForCadence(latest.cadence)
  pyplot.text(0, .90, desc, transform=ax.transAxes, fontproperties=font, color='white')
  pyplot.plot([point.cadence for point in points], color='#ffff00', linewidth=2)

  ax = pyplot.subplot(1,4,4, axisbg='black')
  ax.tick_params(axis='y', colors='gray', labelsize=10)
  pyplot.xlim(0, NUM_GRAPH_POINTS)
  pyplot.locator_params(nbins=4)
  pyplot.gca().get_xaxis().set_visible(False)
  pyplot.ylim(0, 500)  # STP max elevation is 500ft
  # TODO: flash the value in bold whenever VAM is > some ft per min.
  # e.g. crossing every 100 feet for the first time in a while.
  #desc = ('%d feet' % latest.altitude).rjust(11)
  desc = 'Elevation (Feet)'
  font = GetFontPropertiesForGrade(latest.grade)  # XXX: grade is always 0?
  pyplot.text(0, .90, desc, transform=ax.transAxes, fontproperties=font, color='white')
  pyplot.gca().get_xaxis().set_visible(False)
  pyplot.plot([point.altitude for point in points], 'c-', linewidth=2)

  graph_image_fname = os.path.join(output_dir, 'graph-%s.png' % file_basename)
  print 'generating graph %s' % graph_image_fname
  pyplot.savefig(graph_image_fname, facecolor='black')
  return graph_image_fname


def Run(cmd_str, log=None):
  if log:
    print '%s:\n %s' % (log, cmd_str)

  print 'composing picture and map: %s' % cmd_str
  if os.system(cmd_str) != 0:
    raise RuntimeError('command "%s" failed' % cmd_str)


def CompositeImages(pic_fname, gmap_fname, graph_fname, msg_bar_str, output_fname):
  """Assumes:
  - 4:3 pic
  - 300x300 map
  - 1024x160 graph
  - 1024x768 output
  """
  # Resize the image down
  tmpfile = '/tmp/img-and-map.png'
  cmd_str = 'convert -scale 1024x768 %s %s' % (pic_fname, tmpfile)
  Run(cmd_str, log='scaling image down')

  # Composite the resized picture and the map
  cmd_str = 'composite -geometry +797+0 -dissolve 80 %s %s %s' % (
      gmap_fname, tmpfile, tmpfile)
  Run(cmd_str, log='composing picture and map')

  # Add status bar (mileage and time)
  cmd_str = ('convert %s '
             '-fill "#0008" '
             '-draw "rectangle 0,630,1024,665" '
             '-fill "#cccccc" '
             '-font %s '
             '-pointsize 24 '
             '-annotate +10+655 "%s" '
             '%s') % (tmpfile, FONT_PATH, msg_bar_str, tmpfile)
  Run(cmd_str, log='adding status bar (mileage and time)')

  # Composite the tempfile with the graph
  cmd_str = 'composite -geometry +0+665 -dissolve 50 %s %s %s' % (
      graph_fname, tmpfile, output_fname)
  Run(cmd_str, log='composing graph and prev composition')


def GetOutputImagePath(output_dir, pic_fname):
  return os.path.join(output_dir, 'merged-%s' % os.path.basename(pic_fname))


def CheckImagesAndPointsOverlap(images, pointlist):
  """Verify that points exist for the camera's time, fail otherwise."""
  if not len(images):
    raise NoImagesFound()

  if not len(pointlist):
    raise NoGPSTrack('GPS track has 0 points.')

  if images[-1].time < pointlist[0].time:
    raise ImagesAndPointsDoNotOverlap('Last image occurs before first GPS point.')
  if images[0].time > pointlist[-1].time:
    raise ImagesAndPointsDoNotOverlap('First image occurs after last GPS point.')

def main():
  parser = argparse.ArgumentParser(
      description='Timelapse from Garmin bike records.')
  parser.add_argument('--timeskew',
      help='Add (or subtract) seconds from each EXIF timestamp.',
      default=0)
  parser.add_argument('--imgsrcglob', help='Image source glob pattern.',
      default='/mnt/james/images/2013/gopro-flaming-geyser/*.JPG')
  parser.add_argument('--stagingdir', help='Directory to stage files.',
      default='/home/james/tmp/flaming-geyser-output')
  parser.add_argument('--fitfile', help='Path to the source Garmin .fit file.',
      default='/home/james/garmin/2013-06-22-07-05-20.fit')
  parser.add_argument('--loop', help='Iterate over all files.', dest='loop',
      action='store_true', default=True)
  parser.add_argument('--noloop', help='Iterate over all files.', dest='loop',
      action='store_false', default=False)
  parser.add_argument('--mapdelay',
      help='Number of seconds to sleep afer fetching a map.', default=5)
  flags = parser.parse_args()

  pointlist = PointList(flags.fitfile)
  total_distance = pointlist[-1].distance

  if not os.path.exists(flags.stagingdir):
    print 'making %s' % flags.stagingdir
    os.makedirs(flags.stagingdir)

  images = GetImages(glob.glob(flags.imgsrcglob), flags.timeskew)
  CheckImagesAndPointsOverlap(images, pointlist)

  prev_point = None
  map_image_fname = None
  for image in images:
    output_image_path = GetOutputImagePath(flags.stagingdir, image.filename)
    # Check if we've already rendered an image based on this source image.
    if os.path.exists(output_image_path):
      print 'skipping %s' % image.filename
      continue
    print 'processing %s' % image.filename

    # Get the previous N points
    points = pointlist.GetPointsNearestTime(image.time, num_points=NUM_GRAPH_POINTS)
    latest_point = points[-1]

    # Get a graph
    img_basename = os.path.basename(image.filename).replace('.JPG', '')
    graph_image_fname = GetLineGraphForPoints(flags.stagingdir, img_basename, points)

    # Map creation is expensive, so only get a new map if we've moved.
    if (map_image_fname
        and prev_point 
        and ('%.1f' % prev_point.distance) == ('%.1f' % latest_point.distance)):
      print 'distance unchanged, using last map'
    else:
      # Get a map
      map_image_fname = GetMapForPoints(flags.stagingdir, img_basename, points,
          mapdelay=flags.mapdelay)
    # Put them all together
    elapsed_timedelta = latest_point.time - pointlist[0].time
    elapsed_str = ':'.join(str(elapsed_timedelta).split(':')[:2])
    msg_bar_str = 'Distance: %.1f miles (%.1f miles to go) Time: %s (%s elapsed) Temp: %dF' % (
        latest_point.distance,
        total_distance - latest_point.distance,
        latest_point.time.strftime('%l:%M %P'),
        elapsed_str,
        latest_point.temp_f)
    CompositeImages(image.filename, map_image_fname, graph_image_fname,
        msg_bar_str, output_image_path)
    prev_point = latest_point
    if not flags.loop:
      print 'exiting after one iteration'
      sys.exit(0)

  # make a movie:
  # mencoder "mf://merged-*.JPG" -mf fps=12 -o output.avi -ovc lavc -lavcopts vcodec=mpeg4:mbd=2:trell:vbitrate=7000 


if __name__ == '__main__':
  main()
