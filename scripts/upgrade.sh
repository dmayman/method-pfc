#!/bin/bash

# Get the full path to this script, the top dir is one up.
TOPDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
TOPDIR+=/..
cd $TOPDIR

if [[ "$OSTYPE" == "linux"* ]]; then

  # If the brain is running from /etc/rc.local, stop it.
  sudo service rc.local stop
  sudo systemctl daemon-reload

  # Fix up some directories and files that may be owned by root
  sudo chmod -f -R 777 logs/ images/ 
fi

# Install any new python modules
source venv/bin/activate
pip3 install -f venv/pip_download -r requirements.txt 

# Remove all rows in the state table only.
echo 'Updating database...'
if [[ "$OSTYPE" == "linux"* ]]; then
  sudo -u postgres psql openag_brain -c "DELETE FROM app_statemodel;"
else # we are on OSX
  psql postgres openag_brain -c "DELETE FROM app_statemodel;"
fi

# If there is no device type configured, make an unspecified one
DEV_FILE='config/device.txt'
if [ ! -f $DEV_FILE ]; then
  # No file, so create one
  echo "unspecified" > $DEV_FILE
fi

# Load our models
echo 'Migrating the django/postgres database...'
python3.6 manage.py migrate

# Also need to make our user super again for the django admin
echo "from django.contrib.auth.models import User; User.objects.filter(email='openag@openag.edu').delete(); User.objects.create_superuser('openag', 'openag@openag.edu', 'openag')" | python3.6 manage.py shell

# How to test access to the backend, if you see weird IoT errors:
# openssl s_client -connect mqtt.googleapis.com:8883

# Check if brain root env is exported in venv activate, if not add it
if ! grep "OPENAG_BRAIN_ROOT" $TOPDIR/venv/bin/activate > /dev/null; then
  echo "export OPENAG_BRAIN_ROOT=$TOPDIR" >> $TOPDIR/venv/bin/activate
fi

# Remove rc.local
sudo rm -f /etc/rc.local

# Sym link to config/rc.local.<run_context>
if [ ! -f 'config/develop' ]; then
  sudo ln -s $TOPDIR/config/rc.local.production /etc/rc.local
else
  sudo ln -s $TOPDIR/config/rc.local.development /etc/rc.local
fi

# Reload rc.local daemon
sudo systemctl daemon-reload

# Start the OpenAg Brain as a service running as rc.local
sudo service rc.local start
sudo systemctl status rc.local --no-pager