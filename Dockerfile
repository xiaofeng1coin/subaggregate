# 文件名: Dockerfile

# ---- STAGE 1: Builder ----
# 使用一个带有构建工具的 Python slim 镜像作为基础
# "as builder" 为这个阶段命名
FROM python:3.11-slim-bookworm as builder

# 设置工作目录
WORKDIR /app

# 更新 pip
RUN pip install --upgrade pip

# 复制依赖文件
# 这一步单独复制是为了利用Docker的层缓存。只要requirements.txt不变，这一层就不会重新构建。
COPY requirements.txt .

# 安装依赖项到一个指定的目录，方便后面复制到最终镜像
# --no-cache-dir 减少镜像大小
# --target 指定安装位置，而不是全局安装
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt


# ---- STAGE 2: Final Image ----
# 使用一个非常干净、最小化的 slim 镜像作为最终镜像
FROM python:3.11-slim-bookworm

# 设置工作目录
WORKDIR /app

# 从 builder 阶段复制已经安装好的依赖项
COPY --from=builder /app/deps /usr/local/lib/python3.11/site-packages

# 暴露应用程序运行的端口
EXPOSE 5000

# 设置环境变量，确保Python输出是无缓冲的
ENV PYTHONUNBUFFERED=1

# 容器启动时运行的命令
# 使用 Gunicorn 启动应用
# "app:app" 表示运行 app.py 文件中的 app 实例
# --bind 0.0.0.0:5000 使容器内的服务可以在外部访问
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:5000", "app:app"]
