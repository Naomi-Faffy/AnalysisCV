import sys
import os

APP_DIR = os.path.dirname(__file__)
sys.path.insert(0, APP_DIR)

from app import app as application