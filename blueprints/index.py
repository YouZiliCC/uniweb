from flask import Blueprint, render_template

index_bp = Blueprint("index", __name__)


@index_bp.route("/", methods=["GET"])
def index():
    """主页"""
    return render_template("index.html")


@index_bp.route("/docs", methods=["GET"])
def docs():
    """使用帮助页面"""
    return render_template("docs.html")
