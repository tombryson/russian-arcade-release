import requests
import sys
import time
import openai
import subprocess
import os
import re
import pymorphy2
import nltk
import syllables
from urllib.request import urlretrieve
from API_key import openai_API_key
from pronunciation import get_pronunciation

subprocess.run([sys.executable, "mp4_to_vocab-list.py"])

############################################################################################################################################

subprocess.run([sys.executable, "vocab_to_anki-card.py"])