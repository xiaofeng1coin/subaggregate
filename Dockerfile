# 文件名: Dockerfile (已修正)

# ---- STAGE 1: Builder (安装依赖) ----
FROM python:3.11-slim-bookworm as builder
WORKDIR /app
RUN pip install --upgrade pip
# 复制你的 requirements.txt 文件
COPY requirements.txt .
# 将依赖安装到一个特定目录，方便下一阶段复制
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- STAGE 2: Final Image (最终运行环境) ----
FROM python:3.11-slim-bookworm

# ----------------- 时区设置 (修正版) -----------------
# 设置时区环境变量
ENV TZ=Asia/Shanghai
# 更新apt-get源，安装时区数据包，并配置系统时区
# 注意：我们保留 tzdata 包，不再将其卸载，以确保时区数据可用
RUN set -x \
    && apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*
# --------------------------------------------------------

WORKDIR /app

# 从 builder 阶段复制已经安装好的依赖
COPY --from=builder /install /usr/local
# 复制你项目中的所有代码 (包括 app.py, static/, templates/)
COPY . .

# 暴露 Flask 应用运行的端口
EXPOSE 5000

# 设置环境变量，确保 Python 日志直接输出
ENV PYTHONUNBUFFERED=1

# 使用 'python' 命令来直接启动 'app.py'。
# Flask内建的服务器将处理请求，日志会直接输出到容器标准输出。
CMD ["python", "app.py"]
