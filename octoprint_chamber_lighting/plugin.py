# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
import flask

import threading
from time import sleep

class LightMode:
	MANUAL = 0
	AUTO = 1
	ON = 2
	OFF = 3

class PinState:
	HIGH = True
	LOW = False

class LightState:
	ON = True
	OFF = False

class AutoTurnOnWhen:
	OFF = 0
	PRINTING = 1
	CONNECTED = 2

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
		self.log.debug("GPIO SETMODE CALLED TO " + mode)

	def setup(self, pin, mode, pull_up_down = None, initial = None):
		self.log.debug("GPIO SETUP FOR BCM" + str(pin) + " WITH MODE '" + mode + "' AND " + (("pull_up_down=" + pull_up_down) if pull_up_down else ("initial=" + str(initial))))

	def output(self, pin, state):
		self.log.debug("GPIO OUTPUT FOR BCM" + str(pin) + " TO STATE " + str(state))

	def input(self, pin):
		self.log.debug("GPIO INPUT FOR BCM" + str(pin) + " RETURNING FALSE")
		return 0

class RaspberryPiDevice(threading.Thread):
	_updateTime = 0.25

	def __init__(self,
				 logger,
				 pluginMode,
				 lightRelayPin,
				 doorOpenDetectionPin,
				 lightRelayTurnedOnState,
				 doorIsOpenState,
				 autoLightHoldTime,
				 last_instance_shared_data):

		threading.Thread.__init__(self)

		self._log = logger

		self._lightRelayPin = lightRelayPin
		self._doorOpenDetectionPin = doorOpenDetectionPin
		self._lightRelayTurnedOnState = lightRelayTurnedOnState
		self._doorIsOpenState = doorIsOpenState
		self._autoLightHoldTime = autoLightHoldTime
		self._pluginMode = pluginMode

		self._stop = False
		self._lock = threading.RLock()

		self._init_with_data_from_last_instance(last_instance_shared_data)

		self._setup_device()
		self._run_worker()

	def release_driver(self):
		with self._lock:
			self._stop = True

		self.join()

		return dict(
			_state = self._state,
			_isRpi = self._isRpi,
			_gpio = self._gpio
		)

	def get_lighting_state(self):
		return self._get_state()

	def _init_with_data_from_last_instance(self, data):
		if data != None: # initialize from last state
			self._state = data["_state"]
			self._isRpi = data["_isRpi"]
			self._gpio = data["_gpio"]
		else: # initialize defaults
			self._state = False
			self._gpio = self._import_gpio_driver()

	def _import_gpio_driver(self):
		try:
			import RPi.GPIO as GPIO
			self._gpio = GPIO
			self._isRpi = True
		except:
			self._gpio = FakeGpio(self._log)
			self._isRpi = False

		return self._gpio

	def _run_worker(self):
		self.start()

	def run(self):
		while True:
			with self._lock:
				if self._stop == True:
					return

			self._update()
			sleep(self._updateTime)

	def _setup_device(self):
		self._gpio.setmode(self._gpio.BCM)

		self._gpio.setup(
			self._doorOpenDetectionPin,
			self._gpio.IN, pull_up_down =
				self._gpio.PUD_DOWN
				if self._doorIsOpenState == True
				else self._gpio.PUD_UP
			)

		self._gpio.setup(self._lightRelayPin, self._gpio.OUT)

		self._initialize_light_state()
		self._update(isInitial = True)

	def _initialize_light_state(self):
		self._state = not self._state
		self._change_light_state_to(not self._state)

	def _set_state(self, newState):
		with self._lock:
			self._state = newState

	def _get_state(self):
		with self._lock:
			return self._state

	def _update(self, isInitial = False):
		if self._pluginMode == LightMode.ON:
			self._change_light_state_to(True)
			return

		elif self._pluginMode == LightMode.OFF:
			self._change_light_state_to(False)
			return

		doorIsOpen = self._door_is_open()

		if self._pluginMode == LightMode.MANUAL:
			self._change_light_state_to(doorIsOpen)

		elif self._pluginMode == LightMode.AUTO:
			if doorIsOpen:
				self._change_light_state_to(True)
			elif isInitial and self._get_state() == True:
				self._change_light_state_to(False)
			elif not doorIsOpen and self._get_state() == True:
				self._hold_light_and_turn_off()

	def _hold_light_and_turn_off(self):
		currentHoldTime = 0
		modeHasBeenChanged = False

		while currentHoldTime < self._autoLightHoldTime:
			with self._lock:
				if self._stop == True: # look for plugin mode change
					modeHasBeenChanged = True
					break

			currentHoldTime += self._updateTime
			sleep(self._updateTime)

		if modeHasBeenChanged or not self._door_is_open():
			self._change_light_state_to(False)

	def _change_light_state_to(self, newState):
		if self._get_state() != newState:
			self._gpio.output(
				self._lightRelayPin,
				self._lightRelayTurnedOnState if newState
					else not self._lightRelayTurnedOnState
			)

			self._set_state(newState)

	def _door_is_open(self):
		return self._gpio.input(self._doorOpenDetectionPin) == self._doorIsOpenState

Device = RaspberryPiDevice

class ChamberLightingPlugin(octoprint.plugin.StartupPlugin,
							octoprint.plugin.TemplatePlugin,
							octoprint.plugin.SettingsPlugin,
							octoprint.plugin.SimpleApiPlugin,
							octoprint.plugin.EventHandlerPlugin,
							octoprint.plugin.AssetPlugin):

	def on_after_startup(self):
		self._update_printer_state(False, False)
		self.reinitialize_device()

	def reinitialize_device(self):
		shared = None

		if hasattr(self, "device") and self.device != None:
			shared = self.device.release_driver()
			self.device = None

		self.device = Device(
			self._logger,
			self._get_lighting_mode(),
			self._settings.get_int(["lighting_relay_switch_pin"]),
			self._settings.get_int(["door_open_detection_pin"]),
			self._settings.get_boolean(["lighting_relay_switch_on_state"]),
			self._settings.get_boolean(["door_open_detection_state"]),
			self._settings.get_int(["auto_light_hold_time"]),
			shared
		)

	def _get_lighting_mode(self):
		autoTurnOnWhen = self._settings.get_int(["auto_turn_on_when"])
		isAutoMode = self._settings.get_int(["lighting_mode"]) == LightMode.AUTO

		if autoTurnOnWhen == AutoTurnOnWhen.CONNECTED and self._printer_is_connected and isAutoMode:
			return LightMode.ON
		elif autoTurnOnWhen == AutoTurnOnWhen.PRINTING and self._is_printing and isAutoMode:
			return LightMode.ON
		else:
			return self._settings.get_int(["lighting_mode"])

	def get_settings_defaults(self):
		return dict( # default_settings.py
			lighting_mode = LightMode.ON,
			auto_turn_on_when = AutoTurnOnWhen.CONNECTED,
			door_open_detection_pin = 0,
			lighting_relay_switch_pin = 0,
			door_open_detection_state = PinState.HIGH,
			lighting_relay_switch_on_state = PinState.LOW,
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

	def on_event(self, event, payload):
		if event == "Connected":
			self._update_printer_state(_printer_is_connected = True)
		elif event == "Disconnected":
			self._update_printer_state(_printer_is_connected = False, _is_printing = False)
		elif event == "PrinterStateChanged":
			if payload["state_id"] == "PRINTING":
				self._update_printer_state(_is_printing = True)
			elif payload["state_id"] in ["CLOSED", "ERROR", "CLOSED_WITH_ERROR"]:
				self._update_printer_state(_is_printing = False)

	def _update_printer_state(self, _printer_is_connected = None, _is_printing = None):
		if _printer_is_connected != None:
			self._printer_is_connected = _printer_is_connected

		if _is_printing != None:
			self._is_printing = _is_printing

		self.reinitialize_device()

	def on_api_command(self, command, data):
		if command == "are_lights_turn_on":
			return flask.jsonify(state = self.device.get_lighting_state())

		elif command == "next_lighitng_state":
			self.change_to_next_lighting_state()

		else: self._logger.error("Bad octoprint_chamber_lighting command! Name: " + command)

	def on_settings_save(self, data):
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
		self.reinitialize_device()

	def change_to_next_lighting_state(self):
		next_state = self.get_next_lighting_state()
		self.change_lighting_state_to(next_state)

	def get_actual_lighting_state(self):
		return self._settings.get(["lighting_mode"])

	def get_next_lighting_state(self):
		actual = self.get_actual_lighting_state()

		if actual == LightMode.OFF:
			return LightMode.MANUAL
		else: return actual + 1 # next

	def change_lighting_state_to(self, next_state):
		self._settings.set(["lighting_mode"], next_state)
		self._settings.save()
		self.reinitialize_device()

