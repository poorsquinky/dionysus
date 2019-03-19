# dionysus
Lighting controller for Dionysus, a mutant vehicle

-----

When we first built Dionysus in 2015, we intended to build a central computerized controller for its lighting effects, but time was not on our side.  After a few years of hiatus, we brought her out of mothball and finally produced the lighting upgrade we've always wanted.

Dionysus's controlled lights consist of:

* The hexagons: Several diffused LED lights that require direct PWM control
* The chase lights: about 50 feet of WS2813 and WS2815 individually-addressable LED strips, cut up and rearranged around the vehicle
* The thrusters: Two large single-channel red LED panels in the rear.

The control hardware is:
* [Raspberry Pi 3 Model A+](https://www.raspberrypi.org/products/raspberry-pi-3-model-a-plus/)
* [Adafruit I²C PWM module](https://www.adafruit.com/product/815) (PCA9685) with a bunch of power MOSFETs hanging off it, divided into 5x RGB channels (hexagons), and 1x monochrome channel (thrusters)
* A cheap logic-level converter from Amazon
* A cheap USB audio interface from Amazon

On the software side, we're taking advantage of:
* [rpi_ws281x](https://github.com/jgarff/rpi_ws281x)'s Python library to control the addressable lights
* Adafruit's [PCA9685 Python library](https://github.com/adafruit/Adafruit_Python_PCA9685)
* [aubio](https://github.com/aubio/aubio) for music analysis and beat detection

-----

Hopefully we can add more info (setup, photos and video, etc.) soon!

