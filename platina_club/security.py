import secrets

from flask import abort, request, session


def csrf_token():
    token = session.get("_csrf_token")
    if token is None:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def validate_csrf_token():
    expected = session.get("_csrf_token")
    supplied = request.form.get("csrf_token")
    if not expected or not supplied or not secrets.compare_digest(expected, supplied):
        abort(400)
