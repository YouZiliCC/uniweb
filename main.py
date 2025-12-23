from app import create_app
from flask import render_template

# 创建应用实例
app, socketio = create_app()


# 全局错误处理
@app.errorhandler(400)
def bad_request(e):
    return render_template("errors/400.html"), 400


@app.errorhandler(403)
def forbidden(e):
    return render_template("errors/403.html"), 403


@app.errorhandler(404)
def page_not_found(e):
    return render_template("errors/404.html"), 404


@app.errorhandler(500)
def internal_server_error(e):
    return render_template("errors/500.html"), 500


@app.errorhandler(502)
def bad_gateway(e):
    return render_template("errors/502.html"), 502


@app.errorhandler(503)
def service_unavailable(e):
    return render_template("errors/503.html"), 503


@app.errorhandler(504)
def gateway_timeout(e):
    return render_template("errors/504.html"), 504


@app.route("/health")
def health_check():
    return {"status": "ok", "service": "Uniweb"}, 200


if __name__ == "__main__":
    # 支持websocket
    socketio.run(
        app,
        debug=app.config["DEBUG"],
        host=app.config["HOST"],
        port=app.config["PORT"],
        allow_unsafe_werkzeug=True,
    )
