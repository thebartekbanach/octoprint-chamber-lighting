
class RaspberryPiDevice:
	def __init__(self, lightRelayPin, doorOpenDetectionPin, lightRelayTurnedOnState, doorOpenIsOpenState, pluginMode):
		self.lightRelayPin = lightRelayPin
		self.doorOpenDetectionPin = doorOpenDetectionPin
		self.lightRelayTurnedOnState = lightRelayTurnedOnState
		self.doorOpenOpenState = doorOpenIsOpenState
		self.pluginMode = pluginMode

	def __del__(self):
		return

	def get_lighting_state(self):
		return

Device = RaspberryPiDevice
