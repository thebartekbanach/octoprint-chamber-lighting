# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import flask

from enum import Enum

import threading
from time import sleep

# device.py
class RaspberryPiDevice(threading.Thread):
	def __init__(self, _logger, lastState, mode, lightRelayPin, doorOpenDetectionPin, lightRelayTurnedOnState, doorOpenIsOpenState, autoLightHoldTime, lastInitWasPropertly):
		threading.Thread.__init__(self)

		self._logger = _logger
		self._logger.info("Initializing device driver!")

		self.lightRelayPin = lightRelayPin
		self.doorOpenDetectionPin = doorOpenDetectionPin
		self.lightRelayTurnedOnState = lightRelayTurnedOnState
		self.doorOpenOpenState = doorOpenIsOpenState
		self.autoLightHoldTime = autoLightHoldTime
		self.mode = mode

		self.stop = False
		self.state = lastState
		self.lock = threading.RLock()

		if self.import_gpio_driver() and lastInitWasPropertly:
			self.setup()
			self.register_worker()
			self.initializedPropertly = True
			self._logger.info("Device driver initialized!")
		else:
			self.initializedPropertly = False
			self._logger.info("Cannot initialize device since it is not a Raspberry Pi!")


	def import_gpio_driver(self):
		try:
			import RPi.GPIO as GPIO
			self.gpio = GPIO
			return True
		except:
			return False


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
		if self.initializedPropertly:
			self.join()

	def get_lighting_state(self):
		with self.lock:
			return self.state

	def setup(self):
		self.gpio.setmode(self.gpio.BCM)
		self.gpio.setup(self.doorOpenDetectionPin, self.gpio.INPUT)
		self.gpio.setup(self.lightRelayPin, self.gpio.OUTPUT, initial=self.state)

	def update(self):
		if self.mode == LightMode.ON.value:
			self.change_light_state_to(True)
			return

		elif self.mode == LightMode.OFF.value:
			self.change_light_state_to(False)
			return

		doorIsOpen = self.door_is_open()

		if self.mode == LightMode.MANUAL.value:
			self.change_light_state_to(doorIsOpen)
		elif self.mode == LightMode.AUTO.value:
			if not doorIsOpen and self.state == True:
				sleep(self.autoLightHoldTime / 1000 - 0.25)
				self.change_light_state_to(self.door_is_open())


	def change_light_state_to(self, newState):
		self.gpio.output(self.lightRelayPin, newState)
		self.state = newState

	def door_is_open(self):
		return self.gpio.input(self.doorOpenDetectionPin) == self.doorOpenOpenState


Device = RaspberryPiDevice

# enums.light_mode.py
class LightMode(Enum):
	MANUAL = 0
	AUTO = 1
	ON = 2
	OFF = 3

# enums.pin_state.py
class PinState(Enum):
	HIGH = True
	LOW = False

# this
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
		initializedPropertly = True

		if hasattr(self, "device"):
			last = self.device.get_lighting_state()
			initializedPropertly = self.device.initializedPropertly
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
			initializedPropertly
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

