from flask import Blueprint

# You can import your blueprints here so they’re auto-discoverable
from .dockets import dockets_bp

# If you later add more blueprints (like students, admin, etc.)
# you can import them here too.
