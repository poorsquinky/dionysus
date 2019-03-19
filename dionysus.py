#!/usr/bin/env python3

import time
from rpi_ws281x import *
import Adafruit_PCA9685
import argparse
import colorsys

import aubio
import numpy as np
import pyaudio
import wave

import random
import sys
import copy

import multiprocessing # Hold onto your butts.

LED_COUNT      = 130      # Number of LED pixels.
LED_PIN        = 12      # GPIO pin connected to the pixels (18 uses PWM!).
LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 10      # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 255     # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL    = 0       # set to '1' for GPIOs 13, 19, 41, 45 or 53
LED_STRIP      = WS2812_STRIP

def float_close(a, b):
    return abs(a-b) <= 0.00001

def cmp_color(a,b,proximity=0.00001):
    if abs(a[0] - b[0]) > 0.05:
        return False
    for i in range(1,3):
        if abs(a[i]-b[i]) > proximity:
            return False
    return True

class LED(object):

    def __init__(self, pwm, r_pin,g_pin,b_pin):
        self.pwm   = pwm

        self.rgb  = [0.0,0.0,0.0]
        self.hsl  = [0.0,0.0,0.0]
        self.pins = [r_pin,g_pin,b_pin]

    def set_rgb(self, rgb):
        if not cmp_color(rgb,self.rgb):
            self.rgb = [rgb[0],rgb[1],rgb[2]]
            hls = colorsys.rgb_to_hls(rgb[0],rgb[1],rgb[2])
            self.hsl = [hls[0],hls[2],hls[1]]
            for i in range(3):
                if rgb[i] < 0.01: # this seems like the most reasonable possible cutoff
                    pwm.set_pwm(self.pins[i], 0, 0)
                else:
                    on = 4096 - int(4096 * rgb[i])
                    pwm.set_pwm(self.pins[i], on, 4095)

    def get_hsl(self):
        return self.hsl.copy()

class Thruster(object):

    def __init__(self, pwm, pin):
        self.pwm = pwm
        self.pin = pin
        self.brightness = 0.0
        self.last_time = time.time()

    def blink(self):
        self.brightness = 0.0
        self.last_time = time.time()

    def go(self):
        if self.brightness < 1.0:
            self.brightness = min(1.0, (time.time() - self.last_time) * 4.0 - 0.5) # 1/4 second fade time and 1/4 second black
            self.set(self.brightness)

    def set(self, level):
        if level < 0.01:
            self.pwm.set_pwm(self.pin, 0, 0)
        else:
            on = 4096 - int(4096 * level)
            self.pwm.set_pwm(self.pin, on, 4095)

def colorWipe(strip, color, wait_ms=50):
    """Wipe color across display a pixel at a time."""
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, color)
    strip.show()

class DisplayMode(object):
    def __init__(self, strip, hx, clear=True):
        self.hx = hx
        self.strip = strip
        self.length = LED_COUNT

        self.last_loud = time.time()
        self.quiet_vol = 0.0
        self.loud_vol = 0.0
        self.is_quiet = False

        if clear:
            for i in range(0, self.strip.numPixels()):
                self.strip.setPixelColor(i, Color(0,0,0))

        self.palettes = {
            # HSL values

#            "rainbow": [
#                [0.0,       1.0, 0.5], # red
#                [0.035, 1.0, 0.5], # orange
#                [0.09, 1.0, 0.5], # yellow
#                [0.333333333333333, 1.0, 0.5], # green
#                [0.6, 1.0, 0.5], # blue
#                [0.72, 1.0, 0.5], # indigo
#                [0.8,      1.0, 0.4], # violet
#            ],
#            "experiment": lambda: list(map(lambda x: [20.0/max(x % 20,0.0001), 1.0, random.choice([random.random() * 0.5, 0.0])], range(100))),
            "rainbow snake": lambda x=random.random(), z=random.choice([2,3,4,1000]): list(map( lambda y: [x + y * 0.005,1.0,(max(0.6 - y * 0.005, 0.0) if y % z != 0 else 0.0)], range(175) )),
            "30 degree quad": lambda x=random.random(): [
                [x, 1.0, 0.05],
                [x, 1.0, 0.1],
                [x, 1.0, 0.25],
                [x, 1.0, 0.5],
                [x, 1.0, 0.75],
                [x, 1.0, 0.5],
                [x, 1.0, 0.25],
                [x, 1.0, 0.1],
                [x, 1.0, 0.05],

                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],

                [x + 0.0833333, 1.0, 0.25],
                [x + 0.0833333, 1.0, 0.25],

                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],

                [x + 0.5, 1.0, 0.0625],
                [x + 0.5, 1.0, 0.125],
                [x + 0.5, 1.0, 0.25],
                [x + 0.5, 1.0, 0.125],
                [x + 0.5, 1.0, 0.0625],

                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],

                [x + 0.0833333, 1.0, 0.25],
                [x + 0.0833333, 1.0, 0.25],

                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
            ],
            "quad bubbles": lambda x=random.random(): [
                [x,1.0,0.0625],
                [x,1.0,0.125],
                [x,1.0,0.25],
                [x,1.0,0.5],
                [x,1.0,0.75],
                [x,1.0,0.5],
                [x,1.0,0.25],
                [x,1.0,0.125],
                [x,1.0,0.0625],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [x + 0.25,0.25,0.133333],
                [x + 0.25,0.25,0.25],
                [x + 0.25,0.25,0.133333],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [x + 0.5,0.5,0.0625],
                [x + 0.5,0.5,0.125],
                [x + 0.5,0.5,0.25],
                [x + 0.5,0.5,0.5],
                [x + 0.5,0.5,0.75],
                [x + 0.5,0.5,0.5],
                [x + 0.5,0.5,0.25],
                [x + 0.5,0.5,0.125],
                [x + 0.5,0.5,0.0625],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [x + 0.75,0.25,0.133333],
                [x + 0.75,0.25,0.25],
                [x + 0.75,0.25,0.133333],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
                [0.0,0.0,0.0],
            ],
            "mermaid": lambda: [
                [0.5,  1.0, 0.03125],
                [0.66, 1.0, 0.03125],
                [0.7,  1.0, 0.03125],
                [0.66, 1.0, 0.03125],
                [0.5,  1.0, 0.0625],
                [0.66, 1.0, 0.0625],
                [0.7,  1.0, 0.0625],
                [0.66, 1.0, 0.0625],
                [0.5,  1.0, 0.125],
                [0.66, 1.0, 0.125],
                [0.7,  1.0, 0.125],
                [0.66, 1.0, 0.125],
                [0.5,  1.0, 0.25],
                [0.66, 1.0, 0.25],
                [0.7,  1.0, 0.25],
                [0.66, 1.0, 0.25],
                [0.5,  1.0, 0.5],
                [0.66, 1.0, 0.5],
                [0.7,  1.0, 0.5],
                [0.66, 1.0, 0.5],
                [0.5,  1.0, 0.25],
                [0.66, 1.0, 0.25],
                [0.7,  1.0, 0.25],
                [0.66, 1.0, 0.25],
                [0.5,  1.0, 0.125],
                [0.66, 1.0, 0.125],
                [0.7,  1.0, 0.125],
                [0.66, 1.0, 0.125],
                [0.5,  1.0, 0.0625],
                [0.66, 1.0, 0.0625],
                [0.7,  1.0, 0.0625],
                [0.66, 1.0, 0.0625],
            ],
            "lava": lambda: [
                [0.0,    1.0, 0.5],
                [0.0,    1.0, 0.125],
                [0.0,    1.0, 0.05],
                [0.0,    1.0, 0.025],
                [0.0, 0.0, 0.0], # black
                [0.09,  1.0, 0.5], # yellow
                [0.09,  1.0, 0.66], # yellow
                [0.04, 1.0, 0.5], # orange
            ],
            "lori": lambda: [
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black

                [0.75,    1.0, 0.125],
                [0.75,    1.0, 0.0625],
                [0.0,    1.0, 0.1333],
                [0.0,    1.0, 0.125],
                [0.0,    1.0, 0.0625],
                [0.66,    1.0, 0.15],

                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black

                [0.75,    1.0, 0.5],
                [0.75,    1.0, 0.25],
                [0.0,    1.0, 0.66],
                [0.0,    1.0, 0.5],
                [0.0,    1.0, 0.25],
                [0.66,    1.0, 0.75],

                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black

                [0.75,    1.0, 0.25],
                [0.75,    1.0, 0.125],
                [0.0,    1.0, 0.33],
                [0.0,    1.0, 0.25],
                [0.0,    1.0, 0.125],
                [0.66,    1.0, 0.375],

                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black

                [0.75,    1.0, 0.5],
                [0.75,    1.0, 0.25],
                [0.0,    1.0, 0.66],
                [0.0,    1.0, 0.5],
                [0.0,    1.0, 0.25],
                [0.66,    1.0, 0.75],
            ],
            "starfield": lambda: [
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.1666666, 1.0, 0.7], # yellow
                [0.1666666, 0.0, 0.75], # white
                [0.6666666, 1.0, 0.7], # blue
                [0.0, 0.0, 0.0], # black
                [0.6666666, 1.0, 0.2], # blue
            ],
            "blue and green": lambda: [
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.6666666, 1.0, 0.5], # blue
                [0.6666666, 1.0, 0.25], # blue
                [0.6666666, 1.0, 0.0125], # blue
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.3333333, 1.0, 0.5], # green
                [0.3333333, 1.0, 0.125], # green
                [0.3333333, 1.0, 0.05], # green
            ],
            "candy cane": lambda: [
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 1.0, 0.05], # dark red
                [0.0, 1.0, 0.5], # red
                [0.0, 0.0, 1.0], # white
                [0.0, 0.0, 0.05], # gray
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
            ],
            "protons": lambda: [
                # powder blue 15%
                [0.6666666, 1.0, 0.66], # powder blue
                [0.6666666, 1.0, 0.5], # powder blue
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                # white 15%
                [0.6666666, 1.0, 1.0], # white
                [0.6666666, 1.0, 1.0], # white
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
            ],
            "megarainbow": lambda: [
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0,       1.0, 0.5], # red
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.035, 1.0, 0.5], # orange
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.09, 1.0, 0.5], # yellow
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.333333333333333, 1.0, 0.5], # green
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.6, 1.0, 0.5], # blue
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.72, 1.0, 0.5], # indigo
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.0, 0.0, 0.0], # black
                [0.8,      1.0, 0.4], # violet
            ],
            "night sky": lambda: [
                [0.16666, 1.0, 0.2], # yellow
                [0.16666, 1.0, 0.75], # yellow
                [0.16666, 1.0, 0.2], # yellow
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.64, 1.0, 0.0125], # blue
                [0.65, 1.0, 0.025], # blue
                [0.66, 1.0, 0.05], # blue
                [0.67, 1.0, 0.1], # blue
                [0.68, 1.0, 0.2], # blue
                [0.69, 1.0, 0.3], # blue
                [0.70, 1.0, 0.4], # blue
                [0.71, 1.0, 0.5], # blue
                [0.70, 1.0, 0.4], # blue
                [0.69, 1.0, 0.3], # blue
                [0.68, 1.0, 0.2], # blue
                [0.67, 1.0, 0.1], # blue
                [0.66, 1.0, 0.05], # blue
                [0.65, 1.0, 0.025], # blue
                [0.64, 1.0, 0.0125], # blue
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.0, 1.0, 0.2], # red
                [0.0, 1.0, 0.75], # red
                [0.0, 1.0, 0.2], # red
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.64, 1.0, 0.0125], # blue
                [0.65, 1.0, 0.025], # blue
                [0.66, 1.0, 0.05], # blue
                [0.67, 1.0, 0.1], # blue
                [0.68, 1.0, 0.2], # blue
                [0.69, 1.0, 0.3], # blue
                [0.70, 1.0, 0.4], # blue
                [0.71, 1.0, 0.5], # blue
                [0.70, 1.0, 0.4], # blue
                [0.69, 1.0, 0.3], # blue
                [0.68, 1.0, 0.2], # blue
                [0.67, 1.0, 0.1], # blue
                [0.66, 1.0, 0.05], # blue
                [0.65, 1.0, 0.025], # blue
                [0.64, 1.0, 0.0125], # blue
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
            ],
            "red and black": lambda: [
                [0.0, 1.0, 0.0125], # red
                [0.0, 1.0, 0.5], # red
                [0.0, 1.0, 0.5], # red
                [0.0, 1.0, 0.0125], # red
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
            ],
            "primary male": lambda: [
                [0.0, 1.0, 0.5], # red
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.0, 1.0, 0.5], # red
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.0, 1.0, 0.5], # red
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.09, 1.0, 0.5], # yellow
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.09, 1.0, 0.5], # yellow
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.09, 1.0, 0.5], # yellow
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.6, 1.0, 0.5], # blue
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.6, 1.0, 0.5], # blue
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.6, 1.0, 0.5], # blue
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
                [0.62, 1.0, 0.0], # black
            ],
            "movie poster": lambda: [
                [0.7125,  1.0, 0.05], # violet
                [0.7125,  1.0, 0.15], # violet
                [0.7125,  1.0, 0.25], # violet
                [0.7125,  1.0, 0.35], # violet
                [0.7125,  1.0, 0.45], # violet
                [0.7125,  1.0, 0.5], # violet
                [0.07,    1.0, 0.5], # orange
                [0.075,   1.0, 0.4], # orange
                [0.08,    1.0, 0.3], # orange
                [0.085,   1.0, 0.2], # orange
                [0.09,    1.0, 0.1], # orange
                [0.09,    1.0, 0.1], # orange
                [0.085,   1.0, 0.2], # orange
                [0.08,    1.0, 0.3], # orange
                [0.075,   1.0, 0.4], # orange
                [0.07,    1.0, 0.5], # orange
                [0.7125,  1.0, 0.45], # violet
                [0.7125,  1.0, 0.35], # violet
                [0.7125,  1.0, 0.25], # violet
                [0.7125,  1.0, 0.15], # violet
                [0.7125,  1.0, 0.05], # violet
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
            ],
#            "yellowblue": lambda: [
#                [0.6666666, 1.0, 1.0], # blue
#                [0.6666666, 1.0, 0.7], # blue
#                [0.1666666, 1.0, 0.5], # yellow
#                [0.1666666, 1.0, 0.25], # yellow
#            ],
            "pinot noir": lambda: [
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.055, 1.0, 0.0625], # brown
                [0.055, 1.0, 0.0625], # brown
                [0.055, 1.0, 0.0625], # brown
                [0.0, 1.0, 0.125], # red
                [0.0, 1.0, 0.25], # red
                [0.0, 1.0, 0.5], # red
                [0.0, 1.0, 0.25], # red
                [0.0, 1.0, 0.125], # red
                [0.95,  1.0, 0.125], # violet
                [0.95,  1.0, 0.25], # violet
                [0.95,  1.0, 0.5], # violet
                [0.95,  1.0, 0.25], # violet
                [0.95,  1.0, 0.125], # violet
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
                [0.0, 1.0, 0.0], # black
            ],
        }

        self.fps          = 60
        self.frame_count  = 0
        self.last_beat    = 0.0
        self.no_beat      = False

        self.subbeat = 0
        self.is_subbeat = False

        self.beat_count = 0

        self.last_beat_duration = 0.25 # arbitrary init value
        self.last_exec = time.time()
        self.last_subbeat = -1

        self.saved_palette_name = ""
        self.saved_palette = []

        self.reset()

    def go_wrap(self, is_beat=False, volume=0.0):
        start_time = time.time()

        # FIXME: we should only set the color of an led when it changes, to save bandwidth for longer strands.

        # if the sub beat we're on changes
        self.subbeat = int((start_time - self.last_beat) / (self.last_beat_duration / 8))
        self.is_subbeat = self.subbeat != self.last_subbeat
        if is_beat:
            self.last_beat = time.time()

        if time.time() - self.last_beat > 2.0:
            self.no_beat = True
        else:
            self.no_beat = False

        self.go(is_beat, volume)

        self.last_subbeat = self.subbeat
        self.frame_count += 1
        finish_time = time.time()
        sleep_time = max((1.0 / self.fps) - (finish_time - start_time), 0.0)
        time.sleep(sleep_time)

    def get_palette(self):
        if self.saved_palette_name != self.palette:
            self.saved_palette = []
            for color in self.palettes[self.palette]():
                self.saved_palette.append([color[0],color[1],color[2]])
            self.saved_palette_name = self.palette
        return self.saved_palette

    def set_pixel_hsl(self, pixnum, hsl):

        c = colorsys.hls_to_rgb(hsl[0],hsl[2],hsl[1])
        self.strip.setPixelColor(pixnum, Color(
            int(c[0] * 255),
            int(c[1] * 255),
            int(c[2] * 255),
        ))

    def get_nonblack_color(self):
        color = [0.0,0.0,0.0]
        while float_close(color[2], 0.0):
            color = random.choice(self.get_palette())
        return color

    def flip_hex_colors(self):
        adjacent_color = hx[0].get_hsl()
        for i in range(len(hx)):
            h = hx[i]
            oldcolor = h.get_hsl()
            color_list = self.get_palette().copy()
            random.shuffle(color_list)
            hxhsl = color_list[0].copy()
            while cmp_color(hxhsl,oldcolor, 0.1) or cmp_color(hxhsl, adjacent_color, 0.1) or float_close(hxhsl[2], 0.0):
                if len(color_list) == 1:
                    hxhsl = adjacent_color.copy()
                    hxhsl[2] += 0.5
                    if hxhsl[2] > 1.0:
                        hxhsl[2] -= 1.0
                    for i in range(1,3):
                        hxhsl[i] += 0.3333333 + random.random() * 0.3333333
                        if hxhsl[i] > 1.0:
                            hxhsl[i] -= 1.0
                    break
                else:
                    color_list.pop(0)
                    hxhsl = color_list[0].copy()
            if hxhsl[2] < 0.25:
                hxhsl[2] += 0.5
            hxcolor = colorsys.hls_to_rgb(hxhsl[0],hxhsl[2],hxhsl[1])
            h.set_rgb(hxcolor)
            adjacent_color = h.get_hsl()

    def reset(self):
        self.palette = random.choice(list(self.palettes))

        self.saved_palette_name = ""


class Shimmer(DisplayMode):
    def __init__(self, strip, hx, clear=True):
        super(Shimmer, self).__init__(strip, hx, clear)
        self.chance = 1.0

    def reset(self):
        super(Shimmer, self).reset()
        self.chance = random.choice([0.1,0.5,0.75,1.0])
        if self.chance >= 0.75:
            self.fps = 15
        else:
            self.fps = 30

    def go(self, is_beat=False, volume=0.0):

        do_beat = is_beat == True or (self.no_beat and self.frame_count % self.fps == 0)

        if do_beat:
            self.flip_hex_colors()

        for i in range(self.length):
            if random.random() < self.chance:
                self.set_pixel_hsl(i, random.choice(self.get_palette()))

        self.strip.show()

class Chase(DisplayMode):
    def __init__(self, strip, hx, clear=True):
        super(Chase, self).__init__(strip, hx, clear)
        self.hxidx     = 0
        self.stripidx  = 0
        self.chase_dir = 1

    def reset(self):
        super(Chase, self).reset()
        self.chase_dir = random.choice([-1,1])
        self.fps = 15


    def chase_color(self,idx):
        pl = len(self.get_palette())
        while idx >= pl:
            idx -= pl
        while idx < 0:
            idx += pl
        return self.get_palette()[idx]


    def go(self, is_beat=False, volume=0.0):

        do_beat = is_beat == True or (self.no_beat and self.frame_count % self.fps == 0)
        if do_beat:
            self.flip_hex_colors()

        for i in range(self.length):
            self.set_pixel_hsl(i, self.chase_color(self.stripidx + i))

        self.stripidx += self.chase_dir
        if self.stripidx >= 65535:
            self.stripidx -= 65535
        if self.stripidx < -65535:
            self.stripidx = 65535

        self.strip.show()

class Shift(DisplayMode):
    def __init__(self, strip, hx, clear=True):
        super(Shift, self).__init__(strip, hx, clear)
        self.hxidx     = 0
        self.stripidx  = 0
        self.chase_dir = 1

        self.offset1 = 0
        self.offset2 = 0

    def reset(self):
        super(Shift, self).reset()
        self.fps = random.randrange(10,30)

        self.colormap1 = []
        self.colormap2 = []

        palette = self.get_palette()

        blackcount = 0

        while len(self.colormap1) < self.length:
            for i in range(len(palette)):
                color = palette[i]
                halfway = len(self.colormap1) - self.length / 2
                if halfway > 0:
                    color[2] = max(color[2] * halfway / (self.length / 2.0), 0.0)
                if color[2] == 0.0:
                    blackcount += 1
                else:
                    blackcount = 0
                if blackcount <= 3:
                    for j in range(5):
                        self.colormap1.append(color.copy())
                        self.colormap2.append(color.copy())
                    for j in range(10):
                        self.colormap1.append(None)
                        self.colormap2.append(None)

        self.colormap2.reverse()

        # fuzz the map a little
        for j in range(10):
            for i in range(len(self.colormap1)):
                pickfrom = i + random.choice([2,1,1,-1,-1,-2])
                if pickfrom < 0:
                    pickfrom += len(self.colormap1)
                if pickfrom >= len(self.colormap1):
                    pickfrom -= len(self.colormap1)
                holdcolor = self.colormap1[pickfrom]
                self.colormap1[pickfrom] = self.colormap1[i]
                self.colormap1[i] = holdcolor

                # same for colormap2
                pickfrom = i + random.choice([2,1,1,-1,-1,-2])
                if pickfrom < 0:
                    pickfrom += len(self.colormap2)
                if pickfrom >= len(self.colormap2):
                    pickfrom -= len(self.colormap2)
                holdcolor = self.colormap2[pickfrom]
                self.colormap2[pickfrom] = self.colormap2[i]
                self.colormap2[i] = holdcolor

    def go(self, is_beat=False, volume=0.0):

        do_beat = is_beat == True or (self.no_beat and self.frame_count % self.fps == 0)
        if do_beat:
            self.flip_hex_colors()

        for i in range(self.length):
            index = i + self.offset1
            while index >= len(self.colormap1):
                index -= len(self.colormap1)
            while index < 0:
                index += len(self.colormap1)

            if self.colormap1[index] is not None:
                self.set_pixel_hsl(i, self.colormap1[index])

            index = i + self.offset2
            while index >= len(self.colormap2):
                index -= len(self.colormap2)
            while index < 0:
                index += len(self.colormap2)

            if self.colormap2[index] is not None:
                self.set_pixel_hsl(i, self.colormap2[index])

        self.offset1 += 1
        if self.offset1 >= self.length:
            self.offset1 -= self.length

        self.offset2 -= 1
        if self.offset2 < 0:
            self.offset2 += self.length

        self.strip.show()



class ShootingStar(DisplayMode):
    def __init__(self, strip, hx, clear=True):
        super(ShootingStar, self).__init__(strip, hx, clear)

        self.hslfield = []
        for i in range(0, strip.numPixels()):
            self.hslfield.append([0,0,0])
        self.hotSpots = [
                {
                    "x": 0.0,
                    "hsl": self.get_nonblack_color(),
                    "v": 1.0
                },
                {
                    "x": self.length - 1,
                    "hsl": self.get_nonblack_color(),
                    "v": -1.0
                }
        ]

        self.color_index = 0

    def reset(self):
        super(ShootingStar, self).reset()
        self.fps = 60

    def next_star_color(self):
        if self.color_index >= len(self.get_palette()):
            self.color_index = 0
        color = self.get_palette()[self.color_index]
        self.color_index += 1
        if float_close(color[2], 0.0):
            return self.next_star_color()
        return color

    def go(self, is_beat=False, volume=0.0):

        # handle the hexagons
        do_beat = is_beat == True or (self.no_beat and self.frame_count % self.fps == 0)
        if do_beat:
            self.flip_hex_colors()

        if is_beat and len(self.hotSpots) < 16:
            forward_color = self.next_star_color()
            if random.randrange(3) == 0:
                self.hotSpots.append({
                    "x": 0.0,
                    "hsl": forward_color,
                    "v": random.choice([1.0, 1.0, 1.0, 1.0, 1.0, 0.75, 0.5, 0.5, 0.25, 0.125])
                })
            if random.randrange(4) == 0:
                reverse_color = self.next_star_color()
                self.hotSpots.append({
                    "x": self.length - 1,
                    "hsl": reverse_color,
                    "v": random.choice([-1.0, -1.0, -1.0, -0.5, -0.5, -0.25])
                })

        for h in self.hotSpots:
            x = int(h["x"])
            self.hslfield[x] = h["hsl"].copy()
            self.hslfield[x][2] = 1.0
            h["x"] += h["v"]
            if h["x"] >= self.length or h["x"] < 0.0:
                self.hotSpots.remove(h)

        for i in range(self.length):
            l = self.hslfield[i][2]
            if l > 0.0:
                l = l * 0.8
                if l < 0.0001:
                    l = 0.0
                self.hslfield[i][2] = l
                self.set_pixel_hsl(i,self.hslfield[i])

        self.strip.show()




def beat_detect_proc(
    shared_exiting,
    shared_is_beat,
    shared_volume,
    shared_peak_volume,
    shared_tempo_bpm
        ):

    ### set up all the bpm detection stuff

    win_s = 2048                # fft size
    hop_s = win_s // 2          # hop size

    p = pyaudio.PyAudio()

    samplerate=44100
    a_tempo = aubio.tempo("default", win_s, hop_s, samplerate)

    stream = None
    try:
        stream = None
        # Open stream.
        stream = p.open(
                format=pyaudio.paFloat32,
                channels=1,
                rate=samplerate,
                input=True,
                frames_per_buffer=1024,
                )

        stream.start_stream()
    except OSError:
        pass

    fake_beat_start = time.time()
    running_peak_volume = 0.0 # we're using this so that the peaks carry between beats, inclusive

    is_beat = False
    volume = 0.0
    peak_volume = 0.0
    tempo_bpm = 0.0

    try:

        while bool(shared_exiting.value) is False:
            is_beat = False
            if stream:
                data = stream.read(1024)
                samples = np.fromstring(data,
                    dtype=aubio.float_type)
                tempo = a_tempo(samples)
                # Compute the energy (volume) of the
                # current frame.
                current_volume = np.sum(samples**2)/len(samples)

                peak_volume = max(running_peak_volume, volume)
                if tempo:
                    tempo_bpm = a_tempo.get_bpm()
                    is_beat = True
                    volume = current_volume
                    running_peak_volume = volume

            else:
                fake_beat_elapsed = time.time() - fake_beat_start
                if fake_beat_elapsed > 0.25:
                    is_beat = True
                    fake_beat_start = time.time()

            if not stream:
                time.sleep(0.001)

            shared_is_beat.value     = bool(shared_is_beat.value) or is_beat
            shared_volume.value      = volume
            shared_peak_volume.value = peak_volume
            shared_tempo_bpm.value   = tempo_bpm

        if stream:
            stream.stop_stream()
            stream.close()

    except:

        print("Error in audio proc: %s" % sys.exc_info()[0])
        shared_exiting.value = True
        raise




if __name__ == '__main__':

    # globals that I'm being an asshole and not locking properly
    shared_exiting     = multiprocessing.Value('b', False, lock=False)
    shared_is_beat     = multiprocessing.Value('b', False, lock=False)
    shared_volume      = multiprocessing.Value('f', 0.0, lock=False)
    shared_peak_volume = multiprocessing.Value('f', 0.0, lock=False)
    shared_tempo_bpm   = multiprocessing.Value('f', 0.0, lock=False)

    # Create NeoPixel object with appropriate configuration.
    strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL, LED_STRIP)
    # Intialize the library (must be called once before other functions).
    strip.begin()


    pwm = Adafruit_PCA9685.PCA9685()
    pwm.set_pwm_freq(120)
    hx = [
        LED(pwm,  0,  1,  2),
        LED(pwm,  3,  4,  5),
        LED(pwm,  6,  7,  8),
        LED(pwm,  9, 10, 11),
        LED(pwm, 12, 13, 14),
    ]
    for h in hx:
        h.set_rgb([0, 0, 0])

    thruster = Thruster(pwm, 15)

    elapsed = 0.0
    last_time = time.time()

    display_modes = {
        "Shooting Star": ShootingStar(strip, hx),
        "Shimmer": Shimmer(strip, hx, clear=True),
        "Chase": Chase(strip, hx),
        "Shift": Shift(strip, hx),
    }
    current_mode = "Shift"
    beat_count = 0

    audio_process = multiprocessing.Process(target=beat_detect_proc, args=(
        shared_exiting,
        shared_is_beat,
        shared_volume,
        shared_peak_volume,
        shared_tempo_bpm
        ))
    audio_process.start()

    running_beat_volume = []

    avg_beat_volume = 0.0
    max_beat_volume = 0.0
    min_beat_volume = 0.0
    is_quiet = False
    prev_peak_volume = 0.0
    prev_tempo_bpm = 0.0

    last_beat      = time.time()
    half_beat_done = True

    try:

        exiting = bool(shared_exiting)

        while exiting is False and audio_process.is_alive():
            exiting     = bool(shared_exiting.value)
            is_beat     = bool(shared_is_beat.value)
            volume      = float(shared_volume.value)
            peak_volume = float(shared_peak_volume.value)
            tempo_bpm   = float(shared_tempo_bpm.value)

            last_time = time.time()
            bpm_time = 60.0 / max(tempo_bpm, 60.0)

            half_beat_active = False
            if tempo_bpm < 70 and tempo_bpm > 50.0:
                half_beat_active = True

            if not is_beat:
                if half_beat_active and half_beat_done is False and last_beat + bpm_time / 2.0 <= time.time():
                    last_half_beat = time.time()
                    display_modes[current_mode].go_wrap(True, volume)
                    half_beat_done = True
                else:
                    display_modes[current_mode].go_wrap(False, volume)

            else:

                last_beat = time.time()
                half_beat_done = False
                changing = False
                tempo_diff    = (max(tempo_bpm,prev_tempo_bpm) + 0.0001) / (min(tempo_bpm, prev_tempo_bpm) + 0.0001)
                max_peak_diff = (peak_volume + 0.0001)                   / (max_beat_volume + 0.0001)
                min_peak_diff = (min_beat_volume + 0.0001)               / (peak_volume + 0.0001)

                print(" ** beat %s @%s - td %s, maxpd %s, minpd %s" % (
                    beat_count,
                    "{:.6f}".format(tempo_bpm),
                    "{:.6f}".format(tempo_diff),
                    "{:.6f}".format(max_peak_diff),
                    "{:.6f}".format(min_peak_diff),
                    ))

                thruster.blink()

                if beat_count >= 2 and tempo_diff > 1.01:
                    print("%s: t %s != %s (%s)" % (beat_count, "{:.2f}".format(tempo_bpm), "{:.2f}".format(prev_tempo_bpm), "{:.2f}".format(tempo_diff)))
                    changing = True
                elif beat_count >= 2 and max_peak_diff > 2.0:
                    print("%s: %s > %s (%s)" % (beat_count, "{:.6f}".format(peak_volume), "{:.6f}".format(max_beat_volume), "{:.2f}".format(max_peak_diff)))
                    changing = True
                    is_quiet = False
                elif beat_count >= 4 and min_peak_diff > 5.0:
                    print("%s: %s < %s (%s)" % (beat_count, "{:.6f}".format(peak_volume), "{:.6f}".format(min_beat_volume), "{:.2f}".format(min_peak_diff)))
                    is_quiet = True
                    changing = True
                elif volume < 0.00001 and beat_count == 32:
                    print("32 beats")
                    changing = True
                elif beat_count == 128:
                    print("128 beats")
                    changing = True
                if changing:

                    beat_count = 0
                    current_mode = random.choice(list(display_modes))
                    display_modes[current_mode].reset()
                    print("Mode: %s; palette: %s" % (current_mode, display_modes[current_mode].palette))


                running_beat_volume.append(peak_volume)
                if len(running_beat_volume) > 4:
                    del running_beat_volume[0]

                max_beat_volume = max(running_beat_volume)
                min_beat_volume = min(running_beat_volume)

                prev_peak_volume = peak_volume
                prev_tempo_bpm = tempo_bpm

                ## handle the display stuff

                display_modes[current_mode].go_wrap(True, volume)
                beat_count += 1
                is_beat = False

                shared_is_beat.value = is_beat

            thruster.go()


            newtime = time.time()
            elapsed = newtime - last_time

    except KeyboardInterrupt:
        colorWipe(strip, Color(0,0,0), 10)
        for h in hx:
            h.set_rgb([0, 0, 0])

        shared_exiting.value = True
        audio_process.join()

    except:
        print("Error in main proc: %s" % sys.exc_info()[0])
        shared_exiting.value = True
        audio_process.join()
        raise

