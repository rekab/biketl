#!/usr/bin/python

import biketl
import random
import datetime
import unittest

TEST_FIT_FILE = 'testdata/2013-06-08-07-59-08.fit'

class TestPointList(unittest.TestCase):

  def setUp(self):
    self.pointlist = biketl.PointList(TEST_FIT_FILE)

  def test_GetPointsNearestTime(self):
    # Check random locations
    for sample in random.sample(xrange(len(self.pointlist)), 5):
      expected = self.pointlist[sample]
      points = self.pointlist.GetPointsNearestTime(expected.time) 
      self.assertEqual(expected, points[-1])

    # Check head of list
    expected = self.pointlist[0]
    t = expected.time - datetime.timedelta(0, 10)
    points = self.pointlist.GetPointsNearestTime(expected.time) 
    self.assertEqual(expected, points[-1])

    # Check end of list
    expected = self.pointlist[-1]
    t = expected.time + datetime.timedelta(0, 10)
    points = self.pointlist.GetPointsNearestTime(t)
    self.assertEqual(expected, points[-1])

  def test_GetMapForPoints(self):
    pass

  def test_GetLineGraphForPoints(self):
    end_point = self.pointlist[-1]
    points = self.pointlist.GetPointsNearestTime(end_point.time)
    graph = biketl.GetLineGraphForPoints('/tmp', 'test', points)
    print 'graph=%s' % graph


class FakeImage(object):
  def __init__(self, time):
    self.time = time

class TestCheckImagesAndPointsOverlap(unittest.TestCase):

  def setUp(self):
    self.pointlist = biketl.PointList(TEST_FIT_FILE)

  def test_NoOverlap(self):
    end_time = self.pointlist[-1].time + datetime.timedelta(0, 1, 0)
    images = [FakeImage(end_time)]
    self.assertRaises(biketl.ImagesAndPointsDoNotOverlap, biketl.CheckImagesAndPointsOverlap,
        images, self.pointlist)

  def test_NoImages(self):
    self.assertRaises(biketl.NoImagesFound, biketl.CheckImagesAndPointsOverlap,
        [], self.pointlist)

  def test_NoPoints(self):
    images = [FakeImage(datetime.datetime.now())]
    self.assertRaises(biketl.NoGPSTrack, biketl.CheckImagesAndPointsOverlap,
        images, [])

  def test_Success(self):
    end_time = self.pointlist[-1].time
    images = [FakeImage(end_time)]
    biketl.CheckImagesAndPointsOverlap(images, self.pointlist)


if __name__ == '__main__':
  unittest.main()
