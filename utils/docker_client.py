"""Docker 客户端封装和工具函数"""

import os
import docker
import logging
import tarfile
import io


logger = logging.getLogger(__name__)

# Docker client (会自动连接到本地 Docker daemon)
try:
    docker_client = docker.from_env()
except Exception as e:
    logger.error(f"无法连接到 Docker daemon: {e}", exc_info=True)
    docker_client = None


def _docker_image_exists(image_name: str) -> bool:
    """检查 Docker 镜像是否存在"""
    if not docker_client:
        logger.warning("Docker client 未初始化，无法检查镜像")
        return False
    try:
        docker_client.images.get(image_name)
        logger.debug(f"镜像 {image_name} 已存在")
        return True
    except docker.errors.ImageNotFound:
        logger.debug(f"镜像 {image_name} 不存在")
        return False
    except Exception as e:
        logger.error(f"检查镜像 {image_name} 时发生异常: {e}", exc_info=True)
        return False


def _docker_container_exists(container_name: str) -> bool:
    """检查 Docker 容器是否存在"""
    if not docker_client:
        logger.warning("Docker client 未初始化，无法检查容器")
        return False
    try:
        docker_client.containers.get(container_name)
        logger.debug(f"容器 {container_name} 已存在")
        return True
    except docker.errors.NotFound:
        logger.debug(f"容器 {container_name} 不存在")
        return False
    except Exception as e:
        logger.error(f"检查容器 {container_name} 时发生异常: {e}", exc_info=True)
        return False


def _docker_container_status(container_name: str) -> str:
    """获取容器状态: running, stopped"""
    if not docker_client:
        logger.debug("Docker client 未初始化")
        return "stopped"
    try:
        container = docker_client.containers.get(container_name)
        status = container.status  # running, exited, paused, restarting, etc.
        logger.debug(f"容器 {container_name} 状态: {status}")
        if status == "running":
            return "running"
        else:
            return "stopped"
    except docker.errors.NotFound:
        logger.debug(f"容器 {container_name} 不存在")
        return "stopped"
    except Exception as e:
        logger.error(f"获取容器 {container_name} 状态失败: {e}", exc_info=True)
        return "stopped"


def _docker_list_images() -> list:
    """获取本地所有 Docker 镜像列表
    
    返回:
        list: 镜像信息列表，每个元素为 dict，包含:
            - id: 镜像ID(短)
            - name: 镜像名称(第一个tag或<none>)
            - tags: 所有标签列表
            - size: 镜像大小(MB)
            - created: 创建时间
    """
    if not docker_client:
        logger.warning("Docker client 未初始化，无法获取镜像列表")
        return []
    try:
        images = docker_client.images.list()
        result = []
        for img in images:
            # 获取镜像标签
            tags = img.tags if img.tags else []
            # 镜像名称取第一个tag，没有tag则显示ID
            name = tags[0] if tags else f"<none>:{img.short_id}"
            # 计算镜像大小(MB)
            size_mb = round(img.attrs.get('Size', 0) / (1024 * 1024), 2)
            result.append({
                'id': img.short_id,
                'name': name,
                'tags': tags,
                'size': size_mb,
                'created': img.attrs.get('Created', '')
            })
        logger.debug(f"获取到 {len(result)} 个镜像")
        return result
    except Exception as e:
        logger.error(f"获取镜像列表失败: {e}", exc_info=True)
        return []


def _docker_build_image(image_name: str, path: str = None) -> bool:
    """构建 Docker 镜像（阻塞）。成功返回 True"""
    if not docker_client:
        logger.warning("Docker client 未初始化，无法构建镜像")
        return False
    # 目前决定手动加入镜像，此处直接失败
    try:
        build_path = path or os.getcwd()
        logger.info(f"开始构建镜像: {image_name} (路径: {build_path})")
        image, build_logs = docker_client.images.build(
            path=build_path,
            tag=image_name,
            rm=True,  # 删除中间容器
        )
        # 构建日志仅在 DEBUG 级别输出
        for log in build_logs:
            if "stream" in log:
                logger.debug(log["stream"].strip())
        logger.info(f"镜像构建成功: {image_name}")
        return True
    except docker.errors.BuildError as e:
        logger.error(f"镜像构建失败: {image_name}, 错误: {e}")
        return False
    except Exception as e:
        logger.error(f"镜像构建异常: {image_name}", exc_info=True)
        return False


def _docker_run_container(
    image_name: str,
    container_name: str,
    host_port: int,
    container_port: int,
    cpu_count: int = 1,
    mem_limit: str = "1g",
    memswap_limit: str = "1.5g",
    pids_limit: int = 8,
) -> str:
    """运行容器（detached）并返回容器 ID，失败返回空字符串"""
    if not docker_client:
        logger.warning("Docker client 未初始化，无法运行容器")
        return ""
    try:
        container = docker_client.containers.run(
            image_name,
            name=container_name,
            ports={f"{container_port}/tcp": host_port},
            detach=True,
            stdin_open=True,  # 等价于 docker run -i
            tty=True,  # 等价于 docker run -t
            remove=False,  # 不自动删除
            cpu_count=cpu_count,
            mem_limit=mem_limit,
            memswap_limit=memswap_limit,
            pids_limit=pids_limit,
        )
        logger.info(
            f"容器创建并启动成功: {container_name} (ID: {container.short_id}, 端口: {host_port}:{container_port})"
        )
        return container.id
    except docker.errors.APIError as e:
        logger.error(f"容器运行失败: {container_name}, 错误: {e}")
        return ""
    except Exception as e:
        logger.error(f"容器运行异常: {container_name}", exc_info=True)
        return ""


def _docker_start_container(container_name: str) -> bool:
    """启动已存在的容器"""
    if not docker_client:
        logger.warning("Docker client 未初始化，无法启动容器")
        return False
    try:
        container = docker_client.containers.get(container_name)
        container.start()
        logger.info(f"容器启动成功: {container_name}")
        return True
    except docker.errors.NotFound:
        logger.warning(f"容器不存在，无法启动: {container_name}")
        return False
    except docker.errors.APIError as e:
        logger.error(f"容器启动失败: {container_name}, 错误: {e}")
        return False
    except Exception as e:
        logger.error(f"容器启动异常: {container_name}", exc_info=True)
        return False


def _docker_stop_container(container_name: str) -> bool:
    """停止容器"""
    if not docker_client:
        logger.warning("Docker client 未初始化，无法停止容器")
        return False
    try:
        container = docker_client.containers.get(container_name)
        container.stop()
        logger.info(f"容器停止成功: {container_name}")
        return True
    except docker.errors.NotFound:
        logger.warning(f"容器不存在，无法停止: {container_name}")
        return False
    except docker.errors.APIError as e:
        logger.error(f"容器停止失败: {container_name}, 错误: {e}")
        return False
    except Exception as e:
        logger.error(f"容器停止异常: {container_name}", exc_info=True)
        return False


def _docker_remove_container(container_name: str) -> bool:
    """删除容器"""
    if not docker_client:
        logger.warning("Docker client 未初始化，无法删除容器")
        return False
    try:
        container = docker_client.containers.get(container_name)
        container.remove(force=True)
        logger.info(f"容器删除成功: {container_name}")
        return True
    except docker.errors.NotFound:
        logger.warning(f"容器不存在，无法删除: {container_name}")
        return False
    except docker.errors.APIError as e:
        logger.error(f"容器删除失败: {container_name}, 错误: {e}")
        return False
    except Exception as e:
        logger.error(f"容器删除异常: {container_name}", exc_info=True)
        return False


def _upload_to_container(
    container, file_data: bytes, target_path: str, filename: str
) -> tuple[bool, str]:
    """
    将文件直接上传到容器中

    Args:
        container: Docker容器对象
        file_data: 文件二进制数据
        target_path: 容器内目标目录
        filename: 文件名

    Returns:
        (success: bool, message: str)
    """
    try:
        # 创建一个内存中的tar归档
        tar_stream = io.BytesIO()
        tar = tarfile.open(fileobj=tar_stream, mode="w")

        # 将文件添加到tar归档
        tarinfo = tarfile.TarInfo(name=filename)
        tarinfo.size = len(file_data)
        tarinfo.mode = 0o644  # 设置文件权限

        tar.addfile(tarinfo, io.BytesIO(file_data))
        tar.close()

        # 重置流位置到开始
        tar_stream.seek(0)

        # 确保目标目录存在
        try:
            exec_result = container.exec_run(f"mkdir -p {target_path}", user="root")
            if exec_result.exit_code != 0:
                logger.warning(
                    f"创建目录失败: {exec_result.output.decode('utf-8', errors='ignore')}"
                )
        except Exception as e:
            logger.warning(f"创建目录时出错: {e}")

        # 使用Docker API的put_archive方法上传文件
        success = container.put_archive(path=target_path, data=tar_stream.read())

        if success:
            full_path = f"{target_path.rstrip('/')}/{filename}"
            logger.info(f"文件上传成功: {filename} -> {full_path}")
            return True, f"文件已成功上传到 {full_path}"
        else:
            logger.error(f"文件上传失败: {filename}")
            return False, "文件上传失败"

    except Exception as e:
        error_msg = f"上传文件到容器时发生错误: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg
