$(function() {
    function NavbarViewModel(parameters) {
        self = this;

        self.settings = null; // parameters[0].settings; setted in onAfterBinding

        self.pluginId = "#navbar_plugin_chamber_lighting";
        self.pluginRoot = self.pluginId + " .root";
        self.stateTextId = self.pluginId + " .state-text";
        self.lightStateClass = "is-turned-on";

        self.states = [
            "Manual",
            "Auto",
            "On",
            "Off"
        ]

        self.actualStateString = function(newState) {
            if(newState) {
                $(self.stateTextId).text(newState);
            } else {
                return $(self.stateTextId).text();
            }
        }

        self.actualLightState = function(newState) {
            if(typeof newState !== "undefined" && newState !== null) {
                $(self.pluginId).toggleClass(self.lightStateClass, !!newState);
            } else {
                return $(self.pluginId).hasClass(self.lightStateClass);
            }
        }

        self.setupLightStateChecking = function() {
            setTimeout(self.checkLightState, 1000);
        }

        self.checkLightState = function() {
            self.requestTo("chamber_lighting", { command: "are_lights_turn_on" }, (response) => {
                self.actualLightState(response.state);
                self.setupLightStateChecking();
            });
        }

        self.changeToNextLightingState = function() {
            const current = self.actualStateString();
            const actualIndex = self.states.indexOf(current);
            const next = actualIndex === self.states.length - 1 ? 0 : actualIndex + 1;

            self.actualStateString(self.states[next]);
            self.requestTo("chamber_lighting", { command: "next_lighitng_state" });
        }

        self.requestTo = function (endpoint, data, onSuccess) {
            $.ajax({
                url: "/api/plugin/" + endpoint,
                type: "POST",
                dataType: 'json',
                data: JSON.stringify(data),
                contentType: 'application/json; charset=UTF-8',
                success: onSuccess
            });
        }

        self.onAfterBinding = (function() {
            Object.defineProperty(self, "settings", { get: () => parameters[0].settings });
            self.actualStateString(self.states[self.settings.plugins.chamber_lighting.lighting_mode()]);
            $(self.pluginRoot).toggleClass("is-hidden", false);
            console.log(self.settings);

            self.setupLightStateChecking();
            $(self.pluginId).on("click", () => self.changeToNextLightingState());
        }).bind(self);
    }

    OCTOPRINT_VIEWMODELS.push([
        NavbarViewModel,

        // self is a list of dependencies to inject into the plugin, the order which you request
        // here is the order in which the dependencies will be injected into your view model upon
        // instantiation via the parameters argument
        ["settingsViewModel"],

        // Finally, self is the list of selectors for all elements we want self view model to be bound to.
        ["#navbar_plugin_chamber_lighting"]
    ]);
});
