#!bin/sh
rm -r /home/octoprint/octoprint-plugin-build
mkdir /home/octoprint/octoprint-plugin-build
cp -r /home/octoprint/octoprint-plugin/* /home/octoprint/octoprint-plugin-build
/opt/octoprint/venv/bin/pip install -e /home/octoprint/octoprint-plugin-build

/opt/octoprint/venv/bin/octoprint serve