# To Good To Go TeleGram bot

This is a telegram bot for users of 'Too good to go'.
It provides them with an telegram alert when one of their too good to go favorites has a deal.

- clone this repo and cd in its folder
- create a python virtual enviroment and activate it.
    - python3 -m venv venv
    - source venv/bin/activate
- install the dependencies in the virtual enviroment.
    - pip install -r requirements.txt
- start the bot: python tgtgtgbot.py
- to stop press ctrl-c and enter deactivate to leave the python virtual enviroment

To autostart the script with systemd:
- edit tgtgtgbot.service.example with the right values
- copy tgtgtgbot.service.example to your appropiate folder e.g. /etc/systemd/system/tgtgtgbot.service
- enable the service to start at boot
    - sudo systemctl enable tgtgtgbot
- start the service and check if it is running
    - sudo systemctl start tgtgtgbot
    - sudo systemctl status tgtgtgbot
