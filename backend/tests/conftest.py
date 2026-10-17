"""Tests never touch the shared database or Auth0: sample data (mock mode) and the dev "Sign in as" users.

Set here, before any test module imports planit.config, so the order tests are collected in doesn't matter.
"""

import os

os.environ["PLANIT_MOCK"] = "1"
os.environ["PLANIT_AUTH_DEV"] = "1"
