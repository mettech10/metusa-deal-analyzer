"""Flask blueprint for /v1/ltd-co/* and /api/v1/ltd-co/*."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from ltd_co.engine import dispatch
from ltd_co.rates import RatePackError


def _handle(action: str):
    try:
        payload = request.get_json(silent=True) or {}
        if request.args.get("ratePackId") and "ratePackId" not in payload:
            payload["ratePackId"] = request.args["ratePackId"]
        result = dispatch(action, payload)
        return jsonify(result), 200
    except RatePackError as exc:
        return jsonify({"error": str(exc), "type": "rate_pack"}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc), "type": "validation"}), 400
    except Exception as exc:  # pragma: no cover — last-resort envelope
        return jsonify({"error": str(exc), "type": "engine"}), 500


def _make_blueprint(name: str, url_prefix: str) -> Blueprint:
    bp = Blueprint(name, __name__, url_prefix=url_prefix)

    @bp.route("/", methods=["GET"], strict_slashes=False)
    def index():
        return _handle("")

    @bp.get("/rates")
    def get_rates():
        return _handle("rates")

    @bp.post("/rates")
    def post_rates():
        return _handle("rates")

    @bp.post("/compare")
    def post_compare():
        return _handle("compare")

    @bp.post("/section-24")
    def post_section24():
        return _handle("section-24")

    @bp.post("/sdlt")
    def post_sdlt():
        return _handle("sdlt")

    @bp.post("/corporation-tax")
    def post_ct():
        return _handle("corporation-tax")

    @bp.post("/dividends")
    def post_dividends():
        return _handle("dividends")

    return bp


ltd_co_bp = _make_blueprint("ltd_co_v1", "/v1/ltd-co")
ltd_co_api_bp = _make_blueprint("ltd_co_api_v1", "/api/v1/ltd-co")
