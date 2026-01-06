from functools import wraps
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    current_app,
    abort,
    jsonify,
)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField, SelectField
from wtforms.validators import DataRequired, Length, ValidationError
from database.actions import *
from utils.redis_client import docker_status as DOCKER_STATUS
from utils.docker_client import (
    _docker_image_exists,
    _docker_container_exists,
    _docker_container_status,
    _docker_build_image,
    _docker_run_container,
    _docker_start_container,
    _docker_stop_container,
    _docker_remove_container,
    _docker_list_images,
)
from utils.image_upload import save_uploaded_image
import logging
import threading

# 项目蓝图
project_bp = Blueprint("project", __name__)
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------------------------
# Project Forms
# -------------------------------------------------------------------------------------------
class ProjectForm(FlaskForm):
    pname = StringField("项目名称", validators=[DataRequired(), Length(min=3, max=100)])
    pinfo = TextAreaField("项目描述", validators=[Length(max=5000)])
    docker_image = SelectField("Docker镜像", validators=[DataRequired()])
    port = StringField("项目端口", validators=[DataRequired(), Length(min=2, max=10)])
    docker_port = StringField(
        "Docker端口", validators=[DataRequired(), Length(min=2, max=10)]
    )
    submit = SubmitField("保存")

    def __init__(self, *args, **kwargs):
        self.original_port = kwargs.pop("original_port", None)
        self.original_docker_port = kwargs.pop("original_docker_port", None)
        # 获取镜像列表并设置选项
        image_choices = kwargs.pop("image_choices", None)
        super(ProjectForm, self).__init__(*args, **kwargs)
        # 设置镜像选项
        if image_choices:
            self.docker_image.choices = image_choices
        else:
            self.docker_image.choices = [('', '暂无可用镜像')]

    # 自定义验证器
    def validate_port(self, port):
        if not port.data.isdigit() or not (10000 <= int(port.data) <= 65535):
            raise ValidationError("端口号必须是10000到65535之间的数字")
        # 如果端口号没有改变，跳过验证
        if self.original_port and int(port.data) == int(self.original_port):
            return
        # 检查端口是否被其他项目占用
        existing_project = get_projects_by_port(port.data)
        if existing_project:
            raise ValidationError("端口号已被占用")

    def validate_docker_port(self, docker_port):
        if not docker_port.data.isdigit() or not (
            1024 <= int(docker_port.data) <= 65535
        ):
            raise ValidationError("Docker端口号必须是1024到65535之间的数字")


# -------------------------------------------------------------------------------------------
# Group Decorators
# -------------------------------------------------------------------------------------------
def group_required_pid(func):
    """工作组成员权限装饰器"""

    @wraps(func)
    def decorated(*args, **kwargs):
        pid = str(kwargs.get("pid"))
        project = get_project_by_pid(pid)
        if not project:
            abort(404, description="项目不存在")
        if any(
            [
                not current_user.is_authenticated,
                not current_user.gid,
                str(current_user.gid) != str(project.gid),
            ]
        ):
            abort(403, description="需要工作组成员权限才能访问此页面")
        return func(*args, **kwargs)

    return decorated


# -------------------------------------------------------------------------------------------
# Project Views
# -------------------------------------------------------------------------------------------
@project_bp.route("/", methods=["GET"])
def project_list():
    """项目列表页面"""
    projects = list_all_projects()
    external_url = (
        current_app.config.get("SERVER_PROTOCOL", "http")
        + "://"
        + current_app.config.get("SERVER_DOMAIN", "localhost")
    )
    return render_template(
        "project/list.html", projects=projects, external_url=external_url
    )


@project_bp.route("/<uuid:pid>", methods=["GET"])
def project_detail(pid):
    """项目详情页面"""
    pid = str(pid)
    project = get_project_by_pid(pid)
    if not project:
        abort(404, description="项目不存在")

    # 获取评论列表
    comments = get_ordered_project_comments_by_pid(pid)

    # 获取点赞数和当前用户点赞状态
    star_count = get_project_star_count_by_pid(pid)
    user_starred = False
    if current_user.is_authenticated:
        user_starred = check_user_starred(current_user.uid, pid)

    external_url = (
        current_app.config.get("SERVER_PROTOCOL", "http")
        + "://"
        + current_app.config.get("SERVER_DOMAIN", "localhost")
    )

    # 获取仅教师评论设置
    teacher_only_comment = get_system_setting("teacher_only_comment", "false") == "true"
    # 判断当前用户是否可以评论
    can_comment = True
    if teacher_only_comment and current_user.is_authenticated:
        can_comment = current_user.is_teacher or current_user.is_admin

    return render_template(
        "project/detail.html",
        project=project,
        comments=comments,
        star_count=star_count,
        user_starred=user_starred,
        external_url=external_url,
        teacher_only_comment=teacher_only_comment,
        can_comment=can_comment,
    )


# -------------------------------------------------------------------------------------------
# ProjectStar
# -------------------------------------------------------------------------------------------
@project_bp.route("/<uuid:pid>/star", methods=["POST"])
@login_required
def project_star(pid):
    """项目点赞功能"""
    pid = str(pid)
    project = get_project_by_pid(pid)
    if not project:
        return jsonify({"success": False, "message": "项目不存在"}), 404

    # find existing star record by current user
    existing_star = next((s for s in project.stars if s.uid == current_user.uid), None)
    if existing_star:
        # 已点赞，取消点赞
        if not delete_project_star(existing_star):
            logger.error(
                f"取消点赞失败: user={current_user.uname}, project={project.pname}"
            )
            return jsonify({"success": False, "message": "取消点赞失败"}), 500
        # get fresh count
        star_count = get_project_star_count_by_pid(pid)
        logger.debug(f"取消点赞: user={current_user.uname}, project={project.pname}")
        return (
            jsonify(
                {
                    "success": True,
                    "message": "取消点赞成功",
                    "star_count": star_count,
                    "starred": False,
                }
            ),
            200,
        )

    # 未点赞，添加点赞
    new_star = create_project_star(current_user.uid, project.pid)
    if not new_star:
        logger.error(f"点赞失败: user={current_user.uname}, project={project.pname}")
        return jsonify({"success": False, "message": "点赞失败"}), 500
    star_count = get_project_star_count_by_pid(pid)
    logger.debug(f"点赞成功: user={current_user.uname}, project={project.pname}")
    return (
        jsonify(
            {
                "success": True,
                "message": "点赞成功",
                "star_count": star_count,
                "starred": True,
            }
        ),
        200,
    )


# -------------------------------------------------------------------------------------------
# ProjectComment
# -------------------------------------------------------------------------------------------
@project_bp.route("/<uuid:pid>/comment", methods=["POST"])
@login_required
def project_comment(pid):
    """项目评论功能"""
    pid = str(pid)
    project = get_project_by_pid(pid)
    if not project:
        return jsonify({"success": False, "message": "项目不存在"}), 404

    # 检查仅教师评论设置
    from database.actions import get_system_setting
    teacher_only = get_system_setting("teacher_only_comment", "false") == "true"
    if teacher_only and not current_user.is_teacher and not current_user.is_admin:
        return jsonify({"success": False, "message": "仅教师用户可以发表评论"}), 403

    # accept JSON or form-encoded content
    content = None
    if request.is_json:
        data = request.get_json(silent=True) or {}
        content = data.get("content")
    else:
        content = request.form.get("content")

    if not content or not content.strip():
        return jsonify({"success": False, "message": "评论不能为空"}), 400

    created = create_project_comment(current_user.uid, project.pid, content.strip())
    if not created:
        return jsonify({"success": False, "message": "创建评论失败"}), 500

    # respond with comment data for client-side rendering
    return (
        jsonify(
            {
                "success": True,
                "message": "评论已发布",
                "comment": {
                    "pcid": created.pcid,
                    "uid": created.uid,
                    "uname": created.user.uname if created.user else current_user.uname,
                    "content": created.content,
                    "created_at": created.created_at.strftime("%Y-%m-%d %H:%M"),
                },
            }
        ),
        200,
    )


@project_bp.route("/<uuid:pid>/comment/<pcid>", methods=["PUT", "PATCH"])
@login_required
def project_comment_edit(pid, pcid):
    """编辑评论"""
    from database.actions import get_comment_by_pcid, update_comment

    comment = get_comment_by_pcid(pcid)
    if not comment:
        return jsonify({"success": False, "message": "评论不存在"}), 404

    # 只允许作者编辑自己的评论
    if str(comment.uid) != str(current_user.uid):
        return jsonify({"success": False, "message": "无权编辑此评论"}), 403

    # 获取新内容
    data = request.get_json(silent=True) or {}
    content = data.get("content", "").strip()

    if not content:
        return jsonify({"success": False, "message": "评论内容不能为空"}), 400

    # 更新评论
    if not update_comment(comment, content=content):
        return jsonify({"success": False, "message": "更新评论失败"}), 500

    return (
        jsonify(
            {
                "success": True,
                "message": "评论已更新",
                "comment": {
                    "pcid": comment.pcid,
                    "content": comment.content,
                },
            }
        ),
        200,
    )


@project_bp.route("/<uuid:pid>/comment/<pcid>", methods=["DELETE"])
@login_required
def project_comment_delete(pid, pcid):
    """删除评论"""
    from database.actions import get_comment_by_pcid

    comment = get_comment_by_pcid(pcid)
    if not comment:
        return jsonify({"success": False, "message": "评论不存在"}), 404

    # 只允许作者/Admin删除评论
    if str(comment.uid) != str(current_user.uid) and not current_user.is_admin:
        return jsonify({"success": False, "message": "无权删除此评论"}), 403

    # 删除评论
    if not delete_project_comment(comment):
        return jsonify({"success": False, "message": "删除评论失败"}), 500

    return jsonify({"success": True, "message": "评论已删除"}), 200


# -------------------------------------------------------------------------------------------
# Project Actions
# -------------------------------------------------------------------------------------------
@project_bp.route("/<uuid:pid>/edit", methods=["GET", "POST"])
@login_required
@group_required_pid
def project_edit(pid):
    """项目编辑页面"""
    pid = str(pid)
    project = get_project_by_pid(pid)
    if not project:
        flash("项目不存在", "warning")
        abort(404, description="项目不存在")

    # 获取Docker镜像列表
    images = _docker_list_images()
    image_choices = [('', '请选择Docker镜像')]
    for img in images:
        image_choices.append((img['name'], f"{img['name']} ({img['size']} MB)"))

    form = ProjectForm(
        obj=project,
        original_port=project.port,
        original_docker_port=project.docker_port,
        image_choices=image_choices,
    )
    if form.validate_on_submit():
        # 处理图片上传
        if "pimg" in request.files:
            file = request.files["pimg"]
            success, message = save_uploaded_image(
                file=file,
                save_folder="static/img/projects",
                filename=pid,
                convert_to_format="PNG",
            )
            if success:
                flash(message, "success")
            else:
                flash(message, "warning")

        updated_project = update_project(
            project,
            pname=form.pname.data,
            pinfo=form.pinfo.data,
            port=form.port.data,
            docker_port=form.docker_port.data,
            docker_image=form.docker_image.data,
        )
        if not updated_project:
            flash("更新项目失败，请重试", "danger")
            logger.error(
                f"更新项目失败: project={form.pname.data}, user={current_user.uname}"
            )
            return render_template("project/edit.html", form=form, project=project)
        if updated_project and not success:
            flash(f"项目更新成功，但图片上传失败", "warning")
            logger.debug(
                f"更新项目成功，但图片上传失败: {form.pname.data} by user {current_user.uname}"
            )
        else:
            flash("项目更新成功", "success")
            logger.info(f"更新项目成功: {form.pname.data} by user {current_user.uname}")
        return redirect(url_for("project.project_detail", pid=pid))
    return render_template("project/edit.html", form=form, project=project)


@project_bp.route("/<uuid:pid>/start", methods=["POST"])
@login_required
@group_required_pid
def start_docker(pid):
    """启动Docker容器"""
    pid = str(pid)
    project = get_project_by_pid(pid)
    working_dir = current_app.config.get("WORKING_DIR")
    if not project:
        return jsonify({"success": False, "message": "项目不存在"}), 404

    image_name = project.docker_image
    container_name = project.docker_name

    # 需要提前配置好端口映射
    try:
        host_port = int(project.port) if project.port else None
        container_port = int(project.docker_port) if project.docker_port else None
    except Exception:
        host_port = None
        container_port = None

    # docker config
    CPU_COUNT = current_app.config.get("CPU_COUNT", 1)
    MEM_LIMIT = current_app.config.get("MEM_LIMIT", "1g")
    MEMSWAP_LIMIT = current_app.config.get("MEMSWAP_LIMIT", "1.5g")
    PIDS_LIMIT = current_app.config.get("PIDS_LIMIT", 8)

    if not host_port or not container_port:
        logger.error(
            f"启动容器失败，端口未配置: project={project.pname}, port={host_port}, container={container_port}"
        )
        return (
            jsonify(
                {"success": False, "message": "未配置项目端口或容器端口，无法启动"}
            ),
            400,
        )

    # 如果已有正在处理的任务，直接返回启动中
    if DOCKER_STATUS.get(pid) == "starting":
        return (
            jsonify({"success": True, "message": "启动中", "status": "starting"}),
            202,
        )

    # 检查镜像是否存在
    image_exists = _docker_image_exists(image_name)

    # 检查容器是否存在
    container_exists = _docker_container_exists(container_name)

    # 启动流程可能比较耗时（build），我们使用后台线程执行并立即返回启动中状态
    def _build_and_start():
        try:
            DOCKER_STATUS[pid] = "starting"
            logger.info(f"开始启动项目容器: project={project.pname}, pid={pid}")

            # 如果镜像不存在，先 build
            if not image_exists:
                logger.info(
                    f"镜像不存在，开始构建: image={image_name}, project={project.pname}"
                )
                success = _docker_build_image(image_name, path=working_dir)
                if not success:
                    DOCKER_STATUS[pid] = "stopped"
                    logger.error(
                        f"镜像构建失败，容器启动终止: project={project.pname}, pid={pid}"
                    )
                    return

            # 如果容器不存在，创建并运行；否则尝试启动已存在的容器
            if not container_exists:
                logger.info(
                    f"容器不存在，创建并运行: container={container_name}, project={project.pname}"
                )
                container_id = _docker_run_container(
                    image_name,
                    container_name,
                    host_port,
                    container_port,
                    cpu_count=CPU_COUNT,
                    mem_limit=MEM_LIMIT,
                    memswap_limit=MEMSWAP_LIMIT,
                    pids_limit=PIDS_LIMIT,
                )
                if container_id:
                    # persist container id to project record
                    DOCKER_STATUS[pid] = "running"
                    logger.info(
                        f"容器启动成功: container={container_name}, id={container_id}, project={project.pname}"
                    )
                    return
                else:
                    DOCKER_STATUS[pid] = "stopped"
                    logger.error(
                        f"容器创建失败: container={container_name}, project={project.pname}"
                    )
                    return
            else:
                # 尝试启动已存在容器
                logger.info(
                    f"容器已存在，尝试启动: container={container_name}, project={project.pname}"
                )
                started = _docker_start_container(container_name)
                if started:
                    DOCKER_STATUS[pid] = "running"
                    logger.info(
                        f"已存在容器启动成功: container={container_name}, project={project.pname}"
                    )
                    return
                else:
                    DOCKER_STATUS[pid] = "stopped"
                    logger.error(
                        f"已存在容器启动失败: container={container_name}, project={project.pname}"
                    )
                    return
        finally:
            # 如果线程结束且状态仍为 starting，则设置为 stopped 以表示未运行
            if DOCKER_STATUS.get(pid) == "starting":
                DOCKER_STATUS[pid] = "stopped"
                logger.warning(
                    f"容器启动超时或异常终止: project={project.pname}, pid={pid}"
                )

    # 启动后台线程
    t = threading.Thread(target=_build_and_start, daemon=True)
    t.start()

    return (
        jsonify({"success": True, "message": "启动已开始", "status": "starting"}),
        202,
    )


@project_bp.route("/<uuid:pid>/docker/stop", methods=["POST"])
@login_required
@group_required_pid
def stop_docker(pid):
    """停止Docker容器"""
    pid = str(pid)
    project = get_project_by_pid(pid)
    if not project:
        return jsonify({"success": False, "message": "项目不存在"}), 404

    container_name = project.docker_name
    if not _docker_container_exists(container_name):
        logger.warning(
            f"停止容器失败，容器不存在: container={container_name}, project={project.pname}"
        )
        return jsonify({"success": False, "message": "容器不存在"}), 404
    stopped = _docker_stop_container(container_name)
    if not stopped:
        logger.error(
            f"停止容器失败: container={container_name}, project={project.pname}"
        )
        return jsonify({"success": False, "message": "停止容器失败"}), 500
    DOCKER_STATUS[pid] = "stopped"
    logger.info(f"容器已停止: project={project.pname}, pid={pid}")
    return jsonify({"success": True, "message": "容器已停止", "status": "stopped"}), 200


@project_bp.route("/<uuid:pid>/docker/remove", methods=["POST"])
@login_required
@group_required_pid
def remove_docker(pid):
    """删除Docker容器"""
    pid = str(pid)
    project = get_project_by_pid(pid)
    if not project:
        return jsonify({"success": False, "message": "项目不存在"}), 404

    container_name = project.docker_name
    if not _docker_container_exists(container_name):
        logger.warning(
            f"删除容器失败，容器不存在: container={container_name}, project={project.pname}"
        )
        return jsonify({"success": False, "message": "容器不存在"}), 404

    removed = _docker_remove_container(container_name)
    if not removed:
        logger.error(
            f"删除容器失败: container={container_name}, project={project.pname}"
        )
        return jsonify({"success": False, "message": "删除容器失败"}), 500

    # 清除内存状态
    DOCKER_STATUS.pop(pid, None)
    logger.info(
        f"容器已删除: project={project.pname}, pid={pid}, container={container_name}"
    )
    return jsonify({"success": True, "message": "容器已删除", "status": "stopped"}), 200


@project_bp.route("/<uuid:pid>/docker/status", methods=["GET"])
def project_docker_status(pid):
    """返回项目 docker 状态：stopped | starting | running"""
    pid = str(pid)
    project = get_project_by_pid(pid)
    if not project:
        return jsonify({"success": False, "message": "项目不存在"}), 404

    # 首先检查内存状态
    status = DOCKER_STATUS.get(pid)
    if status:
        return jsonify({"success": True, "status": status}), 200

    # 如果没有内存标记，检测容器实际状态
    container_name = project.docker_name
    if _docker_container_exists(container_name):
        st = _docker_container_status(container_name)
        mapped = "running" if st == "running" else "stopped"
        return jsonify({"success": True, "status": mapped}), 200

    # 默认视为已停止
    return jsonify({"success": True, "status": "stopped"}), 200
