import enums.light_mode
import enums.pin_state

settings_defaults = dict(
	lighting_mode = LightMode.ON,
	mode_when_printing = LightMode.ON,
	door_open_detection_pin = 0,
	door_open_detection_state = PinState.HIGH,
	lighting_relay_switch_pin = 0,
	lighting_relay_switch_on_state = PinState.LOW,
	auto_light_hold_time = 5000
)
