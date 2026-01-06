from .base import db
from .models import User, Project, Group, GroupApplication, ProjectStar, ProjectComment, SystemSetting
from sqlalchemy import select
import logging


# 配置 Logger
logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------------------------
# 基础数据库工具函数
# -------------------------------------------------------------------------------------------
def safe_commit():
    """
    安全地提交数据库事务，出错时回滚并记录错误。

    返回:
        bool: 提交是否成功。
    """
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"数据库提交失败: {e}", exc_info=True)
        return False


def safe_add(instance):
    """
    安全地添加数据库记录并提交。

    参数:
        instance: SQLAlchemy 模型实例。

    返回:
        bool: 添加并提交是否成功。
    """
    try:
        db.session.add(instance)
        return safe_commit()
    except Exception as e:
        logger.error(
            f"数据库添加记录失败 [{type(instance).__name__}]: {e}", exc_info=True
        )
        db.session.rollback()
        return False


def safe_delete(instance):
    """
    安全地删除数据库记录并提交。

    参数:
        instance: SQLAlchemy 模型实例。

    返回:
        bool: 删除并提交是否成功。
    """
    try:
        db.session.delete(instance)
        return safe_commit()
    except Exception as e:
        logger.error(
            f"数据库删除记录失败 [{type(instance).__name__}]: {e}", exc_info=True
        )
        db.session.rollback()
        return False


# -------------------------------------------------------------------------------------------
# User CRUD 操作
# -------------------------------------------------------------------------------------------
def create_user(uname, email, sid, password, uinfo=None, role=0):
    """
    创建新用户。

    参数:
        uname (str): 用户名。
        email (str): 邮箱。
        sid (str): 学号。
        password (str): 原始密码。
        uinfo (str): 用户信息。

    返回:
        User: 创建成功的用户对象，失败则返回None。
    """
    try:
        # 检查用户名和邮箱是否已存在
        if any(
            [
                get_user_by_uname(uname),
                get_user_by_email(email),
                get_user_by_sid(sid),
            ]
        ):
            logger.debug(
                f"创建用户失败: 用户名/邮箱/学号已存在 (uname={uname}, email={email}, sid={sid})"
            )
            return None

        user = User(uname=uname, email=email, uinfo=uinfo, sid=sid, role=role)
        user.set_password(password)  # 使用模型方法设置密码哈希

        if safe_add(user):
            logger.info(f"用户创建成功: uname={uname}, uid={user.uid}")
            return user
        return None
    except Exception as e:
        logger.error(f"创建用户异常: uname={uname}", exc_info=True)
        db.session.rollback()
        return None


def update_user(user, **kwargs):
    """
    更新用户记录。

    参数:
        user (User): 要更新的用户对象。
        **kwargs: 要更新的字段及其值。

    返回:
        bool: 更新是否成功。
    """
    if not user:
        logger.warning("update_user Failed: 用户对象为 None")
        return False
    try:
        for key, value in kwargs.items():
            if hasattr(user, key):
                if key == "password":  # 特殊处理密码更新
                    user.set_password(value)
                elif key != "uid":  # 不允许修改ID
                    setattr(user, key, value)
        return safe_commit()
    except Exception as e:
        logger.error(
            f"更新用户失败: uid={user.uid}, uname={getattr(user, 'uname', 'unknown')}",
            exc_info=True,
        )
        db.session.rollback()
        return False


def delete_user(user):
    """
    删除用户记录。

    参数:
        user (User): 要删除的用户对象。

    返回:
        bool: 删除是否成功。
    """
    if not user:
        logger.warning("delete_user Failed: 用户对象为 None")
        return False
    try:
        return safe_delete(user)
    except Exception as e:
        logger.error(
            f"删除用户失败: uid={user.uid}, uname={getattr(user, 'uname', 'unknown')}",
            exc_info=True,
        )
        db.session.rollback()
        return False


def list_all_users():
    """
    列出所有用户。

    返回:
        list: 所有用户对象列表。
    """
    try:
        return db.session.execute(select(User)).scalars().all()
    except Exception as e:
        logger.error(f"list_all_users Failed: {e}", exc_info=True)
        return []


def get_user_by_uname(uname):
    """
    根据用户名获取用户。

    参数:
        uname (str): 用户名。

    返回:
        User: 匹配的用户对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(User).where(User.uname == uname)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_user_by_uname Failed: {e}", exc_info=True)
        return None


def get_user_by_email(email):
    """
    根据邮箱获取用户。

    参数:
        email (str): 邮箱。

    返回:
        User: 匹配的用户对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_user_by_email Failed: {e}", exc_info=True)
        return None


def get_user_by_uid(uid):
    """
    根据用户ID获取用户。

    参数:
        uid (str): 用户ID。

    返回:
        User: 匹配的用户对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(User).where(User.uid == uid)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_user_by_uid Failed: {e}", exc_info=True)
        return None


def get_user_by_sid(sid):
    """
    根据学号获取用户。

    参数:
        sid (str): 学号。

    返回:
        User: 匹配的用户对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(User).where(User.sid == sid)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_user_by_sid Failed: {e}", exc_info=True)
        return None


# -------------------------------------------------------------------------------------------
# Group CRUD 操作
# -------------------------------------------------------------------------------------------
def create_group(gname, leader_id, ginfo=None):
    """
    创建新工作组。

    参数:
        gname (str): 工作组名称。
        ginfo (str): 工作组信息。

    返回:
        Group: 创建成功的工作组对象，失败则返回None。
    """
    try:
        group = Group(gname=gname, leader_id=leader_id, ginfo=ginfo)
        if safe_add(group):
            logger.info(f"工作组 {gname} 创建成功, ID: {group.gid}")
            return group
        return None
    except Exception as e:
        logger.error(f"创建工作组失败: {e}", exc_info=True)
        db.session.rollback()
        return None


def update_group(group, **kwargs):
    """
    更新工作组记录。

    参数:
        group (Group): 要更新的工作组对象。
        **kwargs: 要更新的字段及其值。

    返回:
        bool: 更新是否成功。
    """
    if not group:
        logger.warning("update_group Failed: 工作组对象为 None")
        return False
    try:
        for key, value in kwargs.items():
            if hasattr(group, key):
                if key != "gid":  # 不允许修改ID
                    setattr(group, key, value)
        return safe_commit()
    except Exception as e:
        logger.error(
            f"更新工作组失败: gid={group.gid}, gname={getattr(group, 'gname', 'unknown')}",
            exc_info=True,
        )
        db.session.rollback()
        return False


def delete_group(group):
    """
    删除工作组记录。

    参数:
        group (Group): 要删除的工作组对象。

    返回:
        bool: 删除是否成功。
    """
    if not group:
        logger.warning("delete_group Failed: 工作组对象为 None")
        return False
    try:
        return safe_delete(group)
    except Exception as e:
        logger.error(
            f"删除工作组失败: gid={group.gid}, gname={getattr(group, 'gname', 'unknown')}",
            exc_info=True,
        )
        db.session.rollback()
        return False


def list_all_groups():
    """
    列出所有工作组。

    返回:
        list: 所有工作组对象列表。
    """
    try:
        return db.session.execute(select(Group)).scalars().all()
    except Exception as e:
        logger.error(f"list_all_groups Failed: {e}", exc_info=True)
        return []


def get_group_by_gid(gid):
    """
    根据工作组ID获取工作组。

    参数:
        gid (str): 工作组ID。

    返回:
        Group: 匹配的工作组对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(Group).where(Group.gid == gid)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_group_by_gid Failed: {e}", exc_info=True)
        return None


# -------------------------------------------------------------------------------------------
# Project CRUD 操作
# -------------------------------------------------------------------------------------------
def create_project(pname, gid, pinfo=None, port=None, docker_port=None, docker_image=None):
    """
    创建新项目。

    参数:
        pname (str): 项目名称。
        pinfo (str): 项目描述。
        gid (str): 工作组ID。
        port (int): 项目端口。
        docker_port (int): Docker映射端口。
        docker_image (str): Docker镜像名称。

    返回:
        Project: 创建成功的项目对象，失败则返回None。
    """
    try:
        project = Project(
            pname=pname, pinfo=pinfo, gid=gid, port=port, docker_port=docker_port,
            docker_image=docker_image
        )
        if safe_add(project):
            logger.info(f"项目 {pname} 创建成功, ID: {project.pid}")
            return project
        return None
    except Exception as e:
        logger.error(f"创建项目失败: {e}", exc_info=True)
        db.session.rollback()
        return None


def update_project(project, **kwargs):
    """
    更新项目记录。

    参数:
        project (Project): 要更新的项目对象。
        **kwargs: 要更新的字段及其值。

    返回:
        bool: 更新是否成功。
    """
    if not project:
        return False
    try:
        for key, value in kwargs.items():
            if hasattr(project, key):
                if key != "pid":  # 不允许修改ID
                    setattr(project, key, value)
        return safe_commit()
    except Exception as e:
        logger.error(f"更新项目 {project.pid} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def delete_project(project):
    """
    删除项目记录。

    参数:
        project (Project): 要删除的项目对象。

    返回:
        bool: 删除是否成功。
    """
    if not project:
        return False
    try:
        return safe_delete(project)
    except Exception as e:
        logger.error(f"删除项目 {project.pid} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def list_all_projects():
    """
    列出所有项目。

    返回:
        list: 所有项目对象列表。
    """
    try:
        return db.session.execute(select(Project)).scalars().all()
    except Exception as e:
        logger.error(f"list_all_projects Failed: {e}", exc_info=True)
        return []


def get_project_by_pid(pid):
    """
    根据项目ID获取项目。

    参数:
        pid (str): 项目ID。

    返回:
        Project: 匹配的项目对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(Project).where(Project.pid == pid)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_group_by_pid Failed: {e}", exc_info=True)
        return None


def get_projects_by_port(port):
    """
    根据端口获取项目列表。

    参数:
        port (int): 端口号。

    返回:
        list: 匹配的项目对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(Project).where(Project.port == port)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_projects_by_port Failed: {e}", exc_info=True)
        return None


def get_projects_by_docker_port(docker_port):
    """
    根据Docker映射端口获取项目列表。

    参数:
        docker_port (int): Docker映射端口号。

    返回:
        list: 匹配的项目对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(Project).where(Project.docker_port == docker_port)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_projects_by_docker_port Failed: {e}", exc_info=True)
        return None


def get_projects_by_user(user):
    """
    根据用户获取项目列表。

    参数:
        user (User): 用户对象。

    返回:
        list: 匹配的项目对象列表。
    """
    try:
        return (
            db.session.execute(select(Project).where(Project.gid == user.gid))
            .scalars()
            .all()
        )
    except Exception as e:
        logger.error(f"get_projects_by_user Failed: {e}", exc_info=True)
        return []


# -------------------------------------------------------------------------------------------
# GroupApplication CRUD 操作
# -------------------------------------------------------------------------------------------
def create_group_application(uid, gid, message=None):
    """
    创建工作组申请。

    参数:
        uid (str): 用户ID。
        gid (str): 工作组ID。
        message (str): 申请留言。

    返回:
        GroupApplication: 创建成功的申请对象，失败则返回None。
    """
    try:
        # 检查是否已存在待审核的申请
        existing = get_pending_application(uid, gid)
        if existing:
            logger.warning(f"用户 {uid} 已有待审核的申请到工作组 {gid}")
            return None

        application = GroupApplication(uid=uid, gid=gid, message=message, status=0)
        if safe_add(application):
            logger.info(f"工作组申请创建成功, ID: {application.gaid}")
            return application
        return None
    except Exception as e:
        logger.error(f"创建工作组申请失败: {e}", exc_info=True)
        db.session.rollback()
        return None


def update_group_application(application, **kwargs):
    """
    更新工作组申请记录。

    参数:
        application (GroupApplication): 要更新的申请对象。
        **kwargs: 要更新的字段及其值。

    返回:
        bool: 更新是否成功。
    """
    if not application:
        logger.warning("update_group_application Failed: 申请对象为 None")
        return False
    try:
        for key, value in kwargs.items():
            if hasattr(application, key):
                if key != "gaid":  # 不允许修改ID
                    setattr(application, key, value)
        return safe_commit()
    except Exception as e:
        logger.error(f"更新申请 {application.gaid} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def delete_group_application(application):
    """
    删除工作组申请记录。

    参数:
        application (GroupApplication): 要删除的申请对象。

    返回:
        bool: 删除是否成功。
    """
    if not application:
        logger.warning("delete_group_application Failed: 申请对象为 None")
        return False
    try:
        return safe_delete(application)
    except Exception as e:
        logger.error(f"删除申请 {application.gaid} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def get_application_by_gaid(gaid):
    """
    根据申请ID获取申请。

    参数:
        gaid (str): 申请ID。

    返回:
        GroupApplication: 匹配的申请对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(GroupApplication).where(GroupApplication.gaid == gaid)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_application_by_gaid Failed: {e}", exc_info=True)
        return None


def get_pending_application(uid, gid):
    """
    获取用户对某工作组的待审核申请。

    参数:
        uid (str): 用户ID。
        gid (str): 工作组ID。

    返回:
        GroupApplication: 待审核的申请对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(GroupApplication).where(
                GroupApplication.uid == uid,
                GroupApplication.gid == gid,
                GroupApplication.status == 0,
            )
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_pending_application Failed: {e}", exc_info=True)
        return None


def get_group_pending_applications(gid):
    """
    获取某工作组的所有待审核申请。

    参数:
        gid (str): 工作组ID。

    返回:
        list: 待审核的申请对象列表。
    """
    try:
        return (
            db.session.execute(
                select(GroupApplication).where(
                    GroupApplication.gid == gid, GroupApplication.status == 0
                )
            )
            .scalars()
            .all()
        )
    except Exception as e:
        logger.error(f"get_group_pending_applications Failed: {e}", exc_info=True)
        return []


def get_user_applications(uid):
    """
    获取用户的所有申请。

    参数:
        uid (str): 用户ID。

    返回:
        list: 申请对象列表。
    """
    try:
        return (
            db.session.execute(
                select(GroupApplication).where(GroupApplication.uid == uid)
            )
            .scalars()
            .all()
        )
    except Exception as e:
        logger.error(f"get_user_applications Failed: {e}", exc_info=True)
        return []


# -------------------------------------------------------------------------------------------
# ProjectStar CRUD 操作
# -------------------------------------------------------------------------------------------
def create_project_star(uid, pid):
    """
    创建项目点赞记录。

    参数:
        uid (str): 用户ID。
        pid (str): 项目ID。
    返回:
        ProjectStar: 创建成功的点赞对象，失败则返回None。
    """
    try:
        project_star = ProjectStar(uid=uid, pid=pid)
        if safe_add(project_star):
            logger.info(f"项目点赞记录创建成功, 用户ID: {uid}, 项目ID: {pid}")
            return project_star
        return None
    except Exception as e:
        logger.error(f"创建项目点赞记录失败: {e}", exc_info=True)
        db.session.rollback()
        return None


def delete_project_star(project_star):
    """
    删除项目点赞记录。

    参数:
        project_star (ProjectStar): 要删除的点赞对象。

    返回:
        bool: 删除是否成功。
    """
    if not project_star:
        logger.warning("delete_project_star Failed: 点赞对象为 None")
        return False
    try:
        db.session.delete(project_star)
        db.session.commit()
        return True
    except Exception as e:
        logger.error(f"删除项目点赞记录失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def get_project_star_count_by_pid(pid):
    """
    获取项目的点赞数。

    参数:
        pid (str): 项目ID。

    返回:
        int: 点赞数量。
    """
    try:
        from .models import ProjectStar
        from sqlalchemy import func

        count = db.session.execute(
            select(func.count(ProjectStar.psid)).where(ProjectStar.pid == pid)
        ).scalar()
        return count or 0
    except Exception as e:
        logger.error(f"get_project_star_count_by_pid Failed: {e}", exc_info=True)
        return 0


def check_user_starred(uid, pid):
    """
    检查用户是否已对项目点赞。

    参数:
        uid (str): 用户ID。
        pid (str): 项目ID。

    返回:
        bool: 是否已点赞。
    """
    try:
        from .models import ProjectStar

        star = db.session.execute(
            select(ProjectStar).where(ProjectStar.uid == uid, ProjectStar.pid == pid)
        ).scalar_one_or_none()
        return star is not None
    except Exception as e:
        logger.error(f"check_user_starred Failed: {e}", exc_info=True)
        return False


# -------------------------------------------------------------------------------------------
# ProjectComment CRUD 操作
# -------------------------------------------------------------------------------------------
def create_project_comment(uid, pid, content):
    """
    创建项目评论。

    参数:
        uid (str): 用户ID。
        pid (str): 项目ID。
        content (str): 评论内容。

    返回:
        ProjectComment: 创建成功的评论对象，失败则返回None。
    """
    try:
        project_comment = ProjectComment(uid=uid, pid=pid, content=content)
        if safe_add(project_comment):
            logger.info(f"项目评论创建成功, 用户ID: {uid}, 项目ID: {pid}")
            return project_comment
        return None
    except Exception as e:
        logger.error(f"创建项目评论失败: {e}", exc_info=True)
        db.session.rollback()
        return None


def update_comment(comment, **kwargs):
    """
    更新评论内容。

    参数:
        comment (ProjectComment): 要更新的评论对象。
        **kwargs: 要更新的字段及其值。

    返回:
        bool: 更新是否成功。
    """
    if not comment:
        logger.warning("update_comment Failed: 评论对象为 None")
        return False
    try:
        for key, value in kwargs.items():
            if hasattr(comment, key):
                if key != "pcid":  # 不允许修改ID
                    setattr(comment, key, value)
        return safe_commit()
    except Exception as e:
        logger.error(f"更新评论 {comment.pcid} 失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def delete_project_comment(project_comment):
    """
    删除项目评论。

    参数:
        project_comment (ProjectComment): 要删除的评论对象。

    返回:
        bool: 删除是否成功。
    """
    if not project_comment:
        logger.warning("delete_project_comment Failed: 评论对象为 None")
        return False
    try:
        return safe_delete(project_comment)
    except Exception as e:
        logger.error(f"删除项目评论失败: {e}", exc_info=True)
        db.session.rollback()
        return False


def get_comment_by_pcid(pcid):
    """
    根据评论ID获取评论。

    参数:
        pcid (str): 评论ID。

    返回:
        ProjectComment: 匹配的评论对象，未找到则返回None。
    """
    try:
        return db.session.execute(
            select(ProjectComment).where(ProjectComment.pcid == pcid)
        ).scalar_one_or_none()
    except Exception as e:
        logger.error(f"get_comment_by_pcid Failed: {e}", exc_info=True)
        return None


def get_ordered_project_comments_by_pid(pid):
    """
    获取项目的所有评论，教师评论排在最前面。

    参数:
        pid (str): 项目ID。

    返回:
        list: 评论对象列表，教师评论在前，然后按创建时间倒序排列。
    """
    try:
        # 先获取所有评论并 join user 表来判断是否是教师
        from .models import User

        comments = (
            db.session.execute(
                select(ProjectComment)
                .join(User, ProjectComment.uid == User.uid)
                .where(ProjectComment.pid == pid)
                .order_by(
                    User.role.desc(),  # role=1 (教师) 排在前面
                    ProjectComment.created_at.desc(),  # 然后按时间倒序
                )
            )
            .scalars()
            .all()
        )
        return comments
    except Exception as e:
        logger.error(f"get_ordered_project_comments_by_pid Failed: {e}", exc_info=True)
        return []


# -------------------------------------------------------------------------------------------
# SystemSetting CRUD 操作
# -------------------------------------------------------------------------------------------
def get_system_setting(key, default=None):
    """
    获取系统设置值。

    参数:
        key (str): 设置键名。
        default: 默认值，如果设置不存在则返回此值。

    返回:
        str: 设置值，未找到则返回默认值。
    """
    try:
        setting = db.session.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        ).scalar_one_or_none()
        return setting.value if setting else default
    except Exception as e:
        logger.error(f"get_system_setting Failed: {e}", exc_info=True)
        return default


def set_system_setting(key, value, description=None):
    """
    设置系统设置值（存在则更新，不存在则创建）。

    参数:
        key (str): 设置键名。
        value (str): 设置值。
        description (str): 设置描述（可选）。

    返回:
        bool: 操作是否成功。
    """
    try:
        setting = db.session.execute(
            select(SystemSetting).where(SystemSetting.key == key)
        ).scalar_one_or_none()
        if setting:
            setting.value = value
            if description is not None:
                setting.description = description
        else:
            setting = SystemSetting(key=key, value=value, description=description)
            db.session.add(setting)
        return safe_commit()
    except Exception as e:
        logger.error(f"set_system_setting Failed: {e}", exc_info=True)
        db.session.rollback()
        return False


def get_all_system_settings():
    """
    获取所有系统设置。

    返回:
        dict: 键值对形式的所有设置。
    """
    try:
        settings = db.session.execute(select(SystemSetting)).scalars().all()
        return {s.key: {"value": s.value, "description": s.description} for s in settings}
    except Exception as e:
        logger.error(f"get_all_system_settings Failed: {e}", exc_info=True)
        return {}

