# 文件名: Dockerfile

# ---- STAGE 1: Builder (安装依赖) ----
FROM python:3.11-slim-bookworm as builder
WORKDIR /app
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- STAGE 2: Final Image (最终运行环境) ----
FROM python:3.11-slim-bookworm

# ----------------- 关键修改点：设置时区 -----------------
# 设置时区环境变量，很多程序会直接使用这个变量
ENV TZ=Asia/Shanghai

# 更新apt-get源，安装时区数据包，并配置系统时区
# 这样做能确保容器内的所有进程（包括系统命令如`date`）都使用北京时间
RUN set -x \
    && apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && apt-get purge -y --auto-remove tzdata \
    && rm -rf /var/lib/apt/lists/*
# --------------------------------------------------------

WORKDIR /app

# 从 builder 阶段复制依赖和代码
COPY --from=builder /install /usr/local
COPY . .

# 暴露端口
EXPOSE 5000

# 设置环境变量
ENV PYTHONUNBUFFERED=1

# 容器启动时运行的命令 (包含日志配置)
CMD ["/usr/local/bin/gunicorn", \
     "--workers", "2", \
     "--bind", "0.0.0.0:5000", \
     "--log-level", "info", \
     "--log-file", "-", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
