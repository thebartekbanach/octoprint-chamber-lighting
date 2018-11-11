# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import flask

from enum import Enum

import threading
from time import sleep

class FakeGpio:
	IN = "IN"
	OUT = "OUT"

	PUD_DOWN = "PUD_DOWN"
	PUD_UP = "PUD_UP"

	BCM = "BCM"
	BOARD = "BOARD"

	def __init__(self, log):
		self.log = log

	def setmode(self, mode):
		self.log.info("GPIO SETMODE CALLED TO " + mode)

	def setup(self, pin, mode, pull_up_down = None, initial = None):
		self.log.info("GPIO SETUP FOR BCM" + str(pin) + " WITH MODE '" + mode + "' AND " + (("pull_up_down=" + pull_up_down) if pull_up_down else ("initial=" + str(initial))))

	def output(self, pin, state):
		self.log.info("GPIO OUTPUT FOR BCM" + str(pin) + " TO STATE " + str(state))

	def input(self, pin):
		self.log.info("GPIO INPUT FOR BCM" + str(pin) + " RETURNING FALSE")
		return 0

class RaspberryPiDevice(threading.Thread):
	def __init__(self, _logger, lastState, mode, lightRelayPin, doorOpenDetectionPin, lightRelayTurnedOnState, doorOpenIsOpenState, autoLightHoldTime, is_rpi):
		threading.Thread.__init__(self)

		self._logger = _logger
		self._logger.info("Initializing device driver!")

		self.lightRelayPin = lightRelayPin
		self.doorOpenDetectionPin = doorOpenDetectionPin
		self.lightRelayTurnedOnState = lightRelayTurnedOnState
		self.doorOpenOpenState = doorOpenIsOpenState
		self.autoLightHoldTime = autoLightHoldTime
		self.mode = mode
		self.is_rpi = is_rpi

		self.stop = False
		self.state = lastState
		self.lock = threading.RLock()

		self._logger.info(
			"Device driver initialized!"
			if self.import_gpio_driver()
			else "Device driver initialized with FakeGpio class!"
		)

		self.setup()
		self.register_worker()


	def import_gpio_driver(self):
		if hasattr(self, "is_rpi") and self.is_rpi != None and self.is_rpi == False:
			self.gpio = FakeGpio(self._logger)
			return False

		try:
			import RPi.GPIO as GPIO
			self.gpio = GPIO
			self.is_rpi = True
		except:
			self.gpio = FakeGpio(self._logger)
			self.is_rpi = False

		return self.is_rpi


	def register_worker(self):
		self.start()

	def run(self):
		while True:
			with self.lock:
				if self.stop == True:
					return

			self.update()
			sleep(0.25)

	def delete(self):
		with self.lock:
			self.stop = True

		self.join()

	def get_lighting_state(self):
		with self.lock:
			return self.state

	def setup(self):
		self.gpio.setmode(self.gpio.BCM)
		self.gpio.setup(self.doorOpenDetectionPin, self.gpio.IN, pull_up_down = self.gpio.PUD_DOWN if self.doorOpenOpenState == True else self.gpio.PUD_UP)
		self.gpio.setup(self.lightRelayPin, self.gpio.OUT)

		self.initialize_light_state()
		self.update()

	def update(self):
		if self.mode == LightMode.ON.value:
			self.change_light_state_to(True)
			return

		elif self.mode == LightMode.OFF.value:
			self.change_light_state_to(False)
			return

		doorIsOpen = self.door_is_open()
		self._logger.info("doorIsOpen = " + str(doorIsOpen))

		if self.mode == LightMode.MANUAL.value:
			self.change_light_state_to(doorIsOpen)

		elif self.mode == LightMode.AUTO.value:
			if doorIsOpen:
				self.change_light_state_to(True)
			elif not doorIsOpen and self.state == True:
				self.hold_light_and_turn_off()

	def hold_light_and_turn_off(self):
		holdTime = 0

		while holdTime < self.autoLightHoldTime:
			with self.lock:
				if self.stop == True: # check for plugin mode change
					self.change_light_state_to(False)
					return

			holdTime += 0.25
			sleep(0.25)

		if not self.door_is_open():
			self.change_light_state_to(False)

	def initialize_light_state(self):
		self.state = not self.state
		self.change_light_state_to(not self.state)

	def change_light_state_to(self, newState):
		if self.state != newState:
			self._logger.info("Changing light state")
			self._logger.info("Setting GPIO" + str(self.lightRelayPin) + " to " + str(self.lightRelayTurnedOnState) if newState else str(not self.lightRelayTurnedOnState))
			self.gpio.output(self.lightRelayPin, self.lightRelayTurnedOnState if newState else not self.lightRelayTurnedOnState)

			with self.lock:
				self.state = newState
				self._logger.info("NEW STATE IS " + str(self.state))

	def door_is_open(self):
		return self.gpio.input(self.doorOpenDetectionPin) == self.doorOpenOpenState


Device = RaspberryPiDevice

class LightMode(Enum):
	MANUAL = 0
	AUTO = 1
	ON = 2
	OFF = 3

class PinState(Enum):
	HIGH = True
	LOW = False

class ChamberLightingPlugin(octoprint.plugin.StartupPlugin,
							octoprint.plugin.TemplatePlugin,
							octoprint.plugin.SettingsPlugin,
							octoprint.plugin.SimpleApiPlugin,
							octoprint.plugin.EventHandlerPlugin,
							octoprint.plugin.AssetPlugin):

	def on_after_startup(self):
		self.reinitialize_device()

	def reinitialize_device(self):
		last = False
		is_rpi = None

		if hasattr(self, "device"):
			last = self.device.get_lighting_state()
			is_rpi = self.device.is_rpi
			self.device.delete()
			self.device = None

		self.device = Device(
			self._logger,
			last,
			self._settings.get_int(["lighting_mode"]),
			self._settings.get_int(["lighting_relay_switch_pin"]),
			self._settings.get_int(["door_open_detection_pin"]),
			self._settings.get_boolean(["lighting_relay_switch_on_state"]),
			self._settings.get_boolean(["door_open_detection_state"]),
			self._settings.get_int(["auto_light_hold_time"]),
			is_rpi
		)

	def get_settings_defaults(self):
		return dict( # default_settings.py
			lighting_mode = LightMode.ON.value,
			mode_when_printing = LightMode.ON.value,
			door_open_detection_pin = 0,
			lighting_relay_switch_pin = 0,
			door_open_detection_state = PinState.HIGH.value,
			lighting_relay_switch_on_state = PinState.LOW.value,
			auto_light_hold_time = 5000
		)

	def get_template_configs(self):
		return [
			dict(type = "navbar", custom_bindings = False),
			dict(type = "settings", custom_bindings = False)
		]

	def get_assets(self):
		return dict(
			js = ["navbar.js"],
			less = ["navbar.less"]
		)

	def get_api_commands(self):
		return dict(
			next_lighitng_state = [],
			are_lights_turn_on = []
		)

	def on_api_command(self, command, data):
		if command == "are_lights_turn_on":
			return flask.jsonify(state = self.device.get_lighting_state())

		elif command == "next_lighitng_state":
			self._logger.info("Changing to next chamber lighting state")
			self.change_to_next_lighting_state()

		else: self._logger.error("Bad octoprint_chamber_lighting command! Name: " + command)

	def on_settings_save(self, data):
		self._logger.info(data)
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		self.reinitialize_device()

	def change_to_next_lighting_state(self):
		next_state = self.get_next_lighting_state()
		self.change_lighting_state_to(next_state)

	def get_actual_lighting_state(self):
		return self._settings.get(["lighting_mode"])

	def get_next_lighting_state(self):
		actual = self.get_actual_lighting_state()

		if actual == LightMode.OFF.value:
			return LightMode.MANUAL.value
		else: return actual + 1

	def change_lighting_state_to(self, next_state):
		self._settings.set(["lighting_mode"], next_state)
		self._settings.save()
		self.reinitialize_device()

