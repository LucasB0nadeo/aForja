from flask import Blueprint


steam = Blueprint("steam", __name__, url_prefix="/steam")

from . import routes
