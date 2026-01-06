from functools import wraps
from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    jsonify,
    abort,
    request,
)
from flask_login import login_required, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, TextAreaField
from wtforms.validators import DataRequired, Length
from database.actions import *
from blueprints.project import ProjectForm
from utils.image_upload import save_uploaded_image
from utils.docker_client import _docker_list_images
import logging

group_bp = Blueprint("group", __name__)
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------------------------
# Group Forms
# -------------------------------------------------------------------------------------------
class GroupForm(FlaskForm):
    gname = StringField(
        "工作组名称", validators=[DataRequired(), Length(min=3, max=50)]
    )
    ginfo = TextAreaField("工作组描述", validators=[Length(max=2000)])
    submit = SubmitField("保存")


class ChangeLeaderForm(FlaskForm):
    new_leader_name = SelectField("更换组长为", validators=[DataRequired()])
    submit = SubmitField("确认更换")


# -------------------------------------------------------------------------------------------
# Group Decorators
# -------------------------------------------------------------------------------------------
def group_required(func):
    """工作组成员权限装饰器"""

    @wraps(func)
    def decorated(*args, **kwargs):
        gid = str(kwargs.get("gid"))
        if any(
            [
                not current_user.is_authenticated,
                not current_user.gid,
                str(current_user.gid) != str(gid),
            ]
        ):
            flash("需要工作组成员权限才能访问此页面", "warning")
            return redirect(url_for("group.group_detail", gid=gid))
        return func(*args, **kwargs)

    return decorated


def leader_required(func):
    """工作组组长权限装饰器"""

    @wraps(func)
    def decorated(*args, **kwargs):
        gid = str(kwargs.get("gid"))
        group = get_group_by_gid(gid)
        if any(
            [
                not current_user.is_authenticated,
                not current_user.gid,
                str(current_user.gid) != str(gid),
                str(group.leader_id) != str(current_user.uid),
            ]
        ):
            flash("需要工作组组长权限才能执行此操作", "warning")
            return redirect(url_for("group.group_detail", gid=gid))
        return func(*args, **kwargs)

    return decorated


# -------------------------------------------------------------------------------------------
# Group Views
# -------------------------------------------------------------------------------------------
@group_bp.route("/", methods=["GET"])
def group_list():
    """工作组列表页面"""
    groups = list_all_groups()

    # 获取当前用户的所有待审核申请
    user_applications = {}
    if current_user.is_authenticated and not current_user.gid:
        applications = get_user_applications(current_user.uid)
        # 创建 gid -> application 的映射，只保留待审核的
        user_applications = {
            str(appli.gid): appli for appli in applications if appli.status == 0
        }

    return render_template(
        "group/list.html", groups=groups, user_applications=user_applications
    )


@group_bp.route("/<uuid:gid>", methods=["GET"])
def group_detail(gid):
    """工作组详情页面"""
    gid = str(gid)
    group = get_group_by_gid(gid)
    if not group:
        abort(404, description="工作组不存在")

    # 获取待审核的申请（仅组长可见）
    pending_applications = []
    if current_user.is_authenticated and str(group.leader_id) == str(current_user.uid):
        pending_applications = get_group_pending_applications(gid)

    # 检查当前用户是否已申请
    user_application = None
    if current_user.is_authenticated and not current_user.gid:
        user_application = get_pending_application(current_user.uid, gid)

    return render_template(
        "group/detail.html",
        group=group,
        pending_applications=pending_applications,
        user_application=user_application,
    )


@group_bp.route("/my_group", methods=["GET"])
@login_required
def my_group():
    """当前用户所属工作组页面"""
    group = get_group_by_gid(current_user.gid)
    if not group:
        flash("您当前未加入任何工作组", "warning")
        return redirect(url_for("group.group_list"))
    return redirect(url_for("group.group_detail", gid=group.gid))


# -------------------------------------------------------------------------------------------
# Group Member Actions
# -------------------------------------------------------------------------------------------
@group_bp.route("/<uuid:gid>/apply", methods=["POST"])
@login_required
def apply_to_group(gid):
    """申请加入工作组"""
    gid = str(gid)

    # 检查用户是否已加入其他工作组
    if current_user.gid:
        return jsonify({"error": "您已经加入了一个工作组"}), 400

    # 检查工作组是否存在
    group = get_group_by_gid(gid)
    if not group:
        return jsonify({"error": "工作组不存在"}), 404

    # 检查是否已有待审核的申请
    existing_application = get_pending_application(current_user.uid, gid)
    if existing_application:
        return jsonify({"error": "您已经提交过申请，请等待审核"}), 400

    # 创建申请
    application = create_group_application(current_user.uid, gid)
    if not application:
        logger.error(
            f"创建申请失败: user={current_user.uname}, group={group.gname}, gid={gid}"
        )
        return jsonify({"error": "提交申请失败，请重试"}), 500

    logger.info(
        f"申请提交成功: user={current_user.uname}, group={group.gname}, gid={gid}"
    )
    return jsonify({"message": "申请已提交，请等待组长审核"}), 200


@group_bp.route("/<uuid:gid>/applications/<uuid:gaid>/accept", methods=["POST"])
@login_required
@leader_required
def accept_application(gid, gaid):
    """接受工作组申请"""
    gid = str(gid)
    gaid = str(gaid)

    # 获取申请
    application = get_application_by_gaid(gaid)
    if not application or str(application.gid) != gid:
        return jsonify({"error": "申请不存在"}), 404

    # 检查申请状态
    if application.status != 0:
        return jsonify({"error": "该申请已被处理"}), 400

    # 获取用户
    user = get_user_by_uid(application.uid)
    if not user:
        return jsonify({"error": "用户不存在"}), 404

    # 检查用户是否已加入其他工作组
    if user.gid:
        return jsonify({"error": "该用户已加入其他工作组"}), 400

    # 将用户加入工作组
    if not update_user(user, gid=gid):
        logger.error(
            f"接受申请失败: user={user.uname}, group={application.group.gname}, gid={gid}"
        )
        return jsonify({"error": "接受申请失败"}), 500

    # 更新申请状态
    if not update_group_application(application, status=1):
        logger.warning(f"更新申请状态失败: gaid={gaid}, user={user.uname}")

    logger.info(
        f"申请已接受: user={user.uname}, group={application.group.gname}, gid={gid}"
    )
    return jsonify({"message": "已接受申请，用户已加入工作组"}), 200


@group_bp.route("/<uuid:gid>/applications/<uuid:gaid>/reject", methods=["POST"])
@login_required
@leader_required
def reject_application(gid, gaid):
    """拒绝工作组申请"""
    gid = str(gid)
    gaid = str(gaid)

    # 获取申请
    application = get_application_by_gaid(gaid)
    if not application or str(application.gid) != gid:
        return jsonify({"error": "申请不存在"}), 404

    # 检查申请状态
    if application.status != 0:
        return jsonify({"error": "该申请已被处理"}), 400

    # 更新申请状态
    if not update_group_application(application, status=2):
        logger.error(f"拒绝申请失败: gaid={gaid}, user={application.user.uname}")
        return jsonify({"error": "拒绝申请失败"}), 500

    logger.info(
        f"申请已拒绝: user={application.user.uname}, group={application.group.gname}, gid={gid}"
    )
    return jsonify({"message": "已拒绝申请"}), 200


@group_bp.route("/<uuid:gid>/members/<uuid:uid>/remove", methods=["POST"])
@login_required
@leader_required
def remove_member(gid, uid):
    """移除工作组成员"""
    gid = str(gid)
    uid = str(uid)
    group = get_group_by_gid(gid)
    if not group:
        return jsonify({"error": "工作组不存在"}), 404
    user = get_user_by_uid(uid)
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    if not update_user(user, gid=None):
        logger.error(
            f"移除用户失败: user={user.uname}, group={group.gname}, operator={current_user.uname}"
        )
        return jsonify({"error": "移除用户失败"}), 500
    logger.info(
        f"用户已成功移除工作组: user={user.uname}, group={group.gname}, operator={current_user.uname}"
    )
    return jsonify({"message": "用户已成功移除工作组"}), 200


@group_bp.route("/<uuid:gid>/leader_change", methods=["GET", "POST"])
@login_required
@leader_required
def leader_change(gid):
    """工作组组长更换"""
    gid = str(gid)
    group = get_group_by_gid(gid)
    users = group.users if group else []
    if not group:
        return jsonify({"error": "工作组不存在"}), 404
    form = ChangeLeaderForm()
    form.new_leader_name.choices = [(user.uname, user.uname) for user in users]
    if form.validate_on_submit():
        new_leader = get_user_by_uname(form.new_leader_name.data)
        if not new_leader:
            flash("新组长不存在", "error")
            return render_template("group/leader_change.html", form=form, group=group)
        if not update_group(group, leader_id=new_leader.uid):
            logger.error(
                f"更换组长失败: group={group.gname}, new_leader={new_leader.uname}, operator={current_user.uname}"
            )
            flash("更换组长失败", "error")
            return render_template("group/leader_change.html", form=form, group=group)
        logger.info(
            f"组长更换成功: group={group.gname}, new_leader={new_leader.uname}, operator={current_user.uname}"
        )
        flash("组长更换成功", "success")
        return redirect(url_for("group.group_detail", gid=gid))
    return render_template("group/leader_change.html", form=form, group=group)


# -------------------------------------------------------------------------------------------
# Group Project Actions
# -------------------------------------------------------------------------------------------
@group_bp.route("/<uuid:gid>/projects", methods=["GET", "POST"])
@login_required
@leader_required
def group_projects(gid):
    """工作组项目管理"""
    gid = str(gid)
    group = get_group_by_gid(gid)
    if not group:
        return jsonify({"error": "工作组不存在"}), 404
    pass


@group_bp.route("/<uuid:gid>/projects/create", methods=["GET", "POST"])
@login_required
@leader_required
def project_create(gid):
    """创建工作组项目"""
    gid = str(gid)
    group = get_group_by_gid(gid)
    if not group:
        flash("工作组不存在", "warning")
        return redirect(url_for("group.group_list"))
    
    # 获取Docker镜像列表
    images = _docker_list_images()
    image_choices = [('', '请选择Docker镜像')]
    for img in images:
        # 使用镜像名称作为值和显示文本
        image_choices.append((img['name'], f"{img['name']} ({img['size']} MB)"))
    
    form = ProjectForm(image_choices=image_choices)
    if form.validate_on_submit():
        project = create_project(
            pname=form.pname.data,
            pinfo=form.pinfo.data,
            gid=group.gid,
            port=form.port.data,
            docker_port=form.docker_port.data,
            docker_image=form.docker_image.data,
        )
        if not project:
            flash("创建项目失败，请重试", "danger")
            logger.error(
                f"创建项目失败: project={form.pname.data}, group={group.gname}, operator={current_user.uname}"
            )
            return render_template("project/create.html", form=form, group=group)
        flash("项目创建成功！", "success")
        logger.info(
            f"创建项目成功: project={form.pname.data}, pid={project.pid}, image={form.docker_image.data}, group={group.gname}, operator={current_user.uname}"
        )
        return redirect(url_for("group.group_detail", gid=group.gid))
    return render_template("project/create.html", form=form, group=group)


@group_bp.route("/<uuid:gid>/projects/<uuid:pid>/delete", methods=["POST"])
@login_required
@leader_required
def project_delete(gid, pid):
    """删除工作组项目"""
    gid = str(gid)
    group = get_group_by_gid(gid)
    if not group:
        return jsonify({"error": "工作组不存在"}), 404
    project = get_project_by_pid(pid)
    if not project or str(project.gid) != str(gid):
        return jsonify({"error": "项目不存在"}), 404

    pname = project.pname  # 保存项目名，删除后无法访问
    if not delete_project(project):
        logger.error(
            f"删除项目失败: project={pname}, pid={pid}, operator={current_user.uname}"
        )
        return jsonify({"error": "删除项目失败"}), 500
    logger.info(
        f"删除项目成功: project={pname}, pid={pid}, operator={current_user.uname}"
    )
    return jsonify({"message": "项目已成功删除"}), 200


# -------------------------------------------------------------------------------------------
# Group Actions
# -------------------------------------------------------------------------------------------
@group_bp.route("/create", methods=["GET", "POST"])
@login_required
def group_create():
    """创建工作组页面"""
    if current_user.gid:
        abort(403, description="您已属于某个工作组，无法创建新工作组")
    form = GroupForm()
    if form.validate_on_submit():
        group = create_group(
            gname=form.gname.data,
            ginfo=form.ginfo.data,
            leader_id=current_user.uid,
        )
        if not group:
            flash("创建工作组失败，请重试", "danger")
            logger.warning(f"创建工作组失败: {form.gname.data}")
            return render_template("group/create.html", form=form)
        # 将当前用户加入新创建的工作组
        if not update_user(current_user, gid=group.gid):
            flash("将用户加入工作组失败，请联系管理员", "danger")
            logger.error(f"将用户 {current_user.uname} 加入工作组 {group.gname} 失败")
            return render_template("group/create.html", form=form)
        flash("工作组创建成功！您已成为该组成员", "success")
        logger.info(f"创建工作组成功: {form.gname.data} by user {current_user.uname}")
        return redirect(url_for("group.group_detail", gid=group.gid))
    return render_template("group/create.html", form=form)


@group_bp.route("/<uuid:gid>/edit", methods=["GET", "POST"])
@login_required
@group_required
def group_edit(gid):
    """工作组编辑页面"""
    gid = str(gid)
    group = get_group_by_gid(gid)
    if not group:
        flash("工作组不存在", "warning")
        return redirect(url_for("group.group_list"))
    form = GroupForm(obj=group)
    if form.validate_on_submit():
        # 处理图片上传
        if "gimg" in request.files:
            file = request.files["gimg"]
            if file and file.filename:
                success, message = save_uploaded_image(
                    file,
                    save_folder="static/img/groups",
                    filename=gid,
                    convert_to_format="PNG",
                )
                if success:
                    flash(message, "success")
                else:
                    flash(message, "warning")

        updated_group = update_group(
            group,
            gname=form.gname.data,
            ginfo=form.ginfo.data,
        )
        if not updated_group:
            flash("更新工作组信息失败，请重试", "danger")
            logger.warning(f"更新工作组信息失败: {form.gname.data}")
            return render_template("group/edit.html", form=form, group=group)
        if updated_group and not success:
            flash(f"工作组信息更新成功，但图片上传失败", "warning")
            logger.debug(
                f"更新工作组信息成功，但图片上传失败: {form.gname.data} by user {current_user.uname}"
            )
        else:
            flash("工作组信息更新成功", "success")
            logger.info(
                f"更新工作组信息成功: {form.gname.data} by user {current_user.uname}"
            )
        return redirect(url_for("group.group_detail", gid=gid))
    return render_template("group/edit.html", form=form, group=group)


@group_bp.route("/<uuid:gid>/delete", methods=["POST"])
@login_required
@leader_required
def group_delete(gid):
    """删除工作组"""
    gid = str(gid)
    group = get_group_by_gid(gid)
    if not group:
        return jsonify({"error": "工作组不存在"}), 404
    if not delete_group(group):
        logger.warning(f"删除工作组失败: {group.gname} by user {current_user.uname}")
        return jsonify({"error": "删除工作组失败"}), 500
    logger.info(f"删除工作组成功: {group.gname} by user {current_user.uname}")
    return jsonify({"message": "工作组已成功删除"}), 200  # 自动清空用户的gid字段
