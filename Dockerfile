# 文件名: Dockerfile

# ---- STAGE 1: Builder (安装依赖) ----
# 使用一个带有构建工具的 Python slim 镜像
FROM python:3.11-slim-bookworm as builder

# 设置工作目录
WORKDIR /app

# 提前复制依赖文件以利用缓存
COPY requirements.txt .

# 使用 --prefix 在一个可控的位置安装依赖，而不是全局安装
# 这使得依赖像一个独立的软件包，易于复制
RUN pip install --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- STAGE 2: Final Image (最终运行环境) ----
# 使用一个干净的 slim 镜像
FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app

# 从 builder 阶段复制已经安装好的依赖项
# 这会将 gunicorn 等可执行文件安装到 /usr/local/bin
COPY --from=builder /install /usr/local

# ----------------- 关键步骤 -----------------
# 复制所有应用代码到镜像的 /app 目录。
# 这样你的 `docker cp` 才能从镜像的 /app 中提取出这些文件。
COPY . .
# -----------------------------------------------

# 暴露应用程序运行的端口
EXPOSE 5000

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 容器启动时运行的命令
# 使用 Gunicorn 的绝对路径启动，这是最稳妥的方式，可以绕过任何 $PATH 问题
# 当容器启动时，它会执行 /usr/local/bin/gunicorn
# gunicorn 会在工作目录 /app 下寻找 app:app
CMD ["/usr/local/bin/gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "app:app"]
