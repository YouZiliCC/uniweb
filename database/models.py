from .base import db, login_manager
from datetime import datetime, timedelta, timezone
from sqlalchemy import Column, DateTime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import uuid

# Asia/Shanghai timezone (UTC+8)
_local_tz = timezone(timedelta(hours=8))


def generate_uuid():
    return str(uuid.uuid4())


class TimestampMixin:
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(_local_tz), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(_local_tz),
        onupdate=lambda: datetime.now(_local_tz),
        nullable=False,
    )


class User(db.Model, TimestampMixin, UserMixin):
    # 用户表
    __tablename__ = "users"
    # 字段
    uid = db.Column(db.String(512), primary_key=True, default=generate_uuid)
    uname = db.Column(db.String(512), unique=True, nullable=False)
    uinfo = db.Column(db.Text, nullable=True)
    sid = db.Column(db.String(512), unique=True, nullable=False)
    email = db.Column(db.String(512), unique=True, nullable=False)
    passwd_hash = db.Column(db.String(512), nullable=False)
    gid = db.Column(
        db.String(512), db.ForeignKey("groups.gid", ondelete="SET NULL"), nullable=True
    )
    role = db.Column(db.Integer, default=0)  # 0: 普通用户, 1: 管理员, 2: Teacher

    @property
    def is_admin(self):
        return self.role == 1

    @property
    def is_teacher(self):
        return self.role == 2

    @property
    def is_leader(self):
        return self.group.leader_id == self.uid if self.group else False

    def set_password(self, password):
        self.passwd_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.passwd_hash, password)

    def __repr__(self):
        return f"<User {self.uname} ({self.email})>"

    def get_id(self):
        return self.uid


class Group(db.Model, TimestampMixin):
    # 工作组表
    __tablename__ = "groups"
    # 字段
    gid = db.Column(db.String(512), primary_key=True, default=generate_uuid)
    gname = db.Column(db.String(512), nullable=False)
    ginfo = db.Column(db.Text, nullable=True)
    leader_id = db.Column(db.String(512), db.ForeignKey("users.uid"), nullable=False)
    users = db.relationship("User", backref="group", foreign_keys=[User.gid], lazy=True)
    projects = db.relationship(
        "Project",
        backref="group",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy=True,
    )

    def __repr__(self):
        users_list = ";".join(user.uname for user in self.users)
        return f"<Group {self.gname} ({users_list})>"


class Project(db.Model, TimestampMixin):
    # 项目表
    __tablename__ = "projects"
    # 字段
    pid = db.Column(db.String(512), primary_key=True, default=generate_uuid)
    pname = db.Column(db.String(512), nullable=False)
    pinfo = db.Column(db.Text, nullable=True)
    gid = db.Column(
        db.String(512), db.ForeignKey("groups.gid", ondelete="CASCADE"), nullable=False
    )
    docker_name = db.Column(db.String(512), unique=True, default=generate_uuid)
    docker_image = db.Column(db.String(512), nullable=True)  # Docker镜像名称
    port = db.Column(db.Integer, unique=True, nullable=True)
    docker_port = db.Column(db.Integer, unique=False, nullable=True)

    def __repr__(self):
        return f"<Project {self.pname} ({self.port}:{self.docker_port})>"


class GroupApplication(db.Model, TimestampMixin):
    # 工作组申请表
    __tablename__ = "group_applications"
    # 字段
    gaid = db.Column(db.String(512), primary_key=True, default=generate_uuid)
    uid = db.Column(
        db.String(512), db.ForeignKey("users.uid", ondelete="CASCADE"), nullable=False
    )
    gid = db.Column(
        db.String(512), db.ForeignKey("groups.gid", ondelete="CASCADE"), nullable=False
    )
    status = db.Column(
        db.Integer, default=0, nullable=False
    )  # 0: 待审核, 1: 已接受, 2: 已拒绝
    message = db.Column(db.Text, nullable=True)  # 申请留言

    # 建立关系 - 使用 passive_deletes 让数据库处理级联删除
    user = db.relationship(
        "User",
        backref=db.backref("applications", passive_deletes=True),
        foreign_keys=[uid],
    )
    group = db.relationship(
        "Group",
        backref=db.backref("applications", passive_deletes=True),
        foreign_keys=[gid],
    )

    def __repr__(self):
        return f"<GroupApplication {self.user.uname} -> {self.group.gname} (status={self.status})>"


class ProjectStar(db.Model, TimestampMixin):
    # 项目点赞表
    __tablename__ = "project_stars"
    # 字段
    psid = db.Column(db.String(512), primary_key=True, default=generate_uuid)
    uid = db.Column(
        db.String(512), db.ForeignKey("users.uid", ondelete="CASCADE"), nullable=False
    )
    pid = db.Column(
        db.String(512),
        db.ForeignKey("projects.pid", ondelete="CASCADE"),
        nullable=False,
    )

    user = db.relationship(
        "User",
        backref=db.backref("stars", passive_deletes=True),
        foreign_keys=[uid],
    )
    project = db.relationship(
        "Project",
        backref=db.backref("stars", passive_deletes=True),
        foreign_keys=[pid],
    )

    def __repr__(self):
        return f"<ProjectStar {self.user.uname} -> {self.project.pname}>"


class ProjectComment(db.Model, TimestampMixin):
    # 项目评论表
    __tablename__ = "project_comments"
    # 字段
    pcid = db.Column(db.String(512), primary_key=True, default=generate_uuid)
    uid = db.Column(
        db.String(512), db.ForeignKey("users.uid", ondelete="CASCADE"), nullable=False
    )
    pid = db.Column(
        db.String(512),
        db.ForeignKey("projects.pid", ondelete="CASCADE"),
        nullable=False,
    )
    content = db.Column(db.Text, nullable=False)

    user = db.relationship(
        "User",
        backref=db.backref("comments", passive_deletes=True),
        foreign_keys=[uid],
    )
    project = db.relationship(
        "Project",
        backref=db.backref("comments", passive_deletes=True),
        foreign_keys=[pid],
    )

    @property
    def is_teacher_comment(self):
        return self.user.is_teacher

    def __repr__(self):
        return f"<ProjectComment {self.user.uname} on {self.project.pname}>"


class SystemSetting(db.Model):
    # 系统设置表
    __tablename__ = "system_settings"
    # 字段
    key = db.Column(db.String(256), primary_key=True)
    value = db.Column(db.String(512), nullable=False, default="")
    description = db.Column(db.String(512), nullable=True)

    def __repr__(self):
        return f"<SystemSetting {self.key}={self.value}>"


# 用户加载回调函数(flask_login)
@login_manager.user_loader
def load_user(user_id: str):
    return db.session.get(User, user_id)
