# 文件名: Dockerfile

# ---- STAGE 1: Builder (安装依赖) ----
FROM python:3.11-slim-bookworm as builder
WORKDIR /app
RUN pip install --upgrade pip
# 复制你的 requirements.txt 文件 (请确保里面没有 gunicorn)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- STAGE 2: Final Image (最终运行环境) ----
FROM python:3.11-slim-bookworm

# ----------------- 时区设置 (保持不变) -----------------
# 设置时区环境变量
ENV TZ=Asia/Shanghai
# 更新apt-get源，安装时区数据包，并配置系统时区
RUN set -x \
    && apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && apt-get purge -y --auto-remove tzdata \
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

# ======================= 【【【 核心修改点 】】】 =======================
#
# CMD ["/usr/local/bin/gunicorn", \   <-- 删除这部分
#      "--workers", "2", \
#      "--bind", "0.0.0.0:5000", \
#      "--log-level", "info", \
#      "--log-file", "-", \
#      "--access-logfile", "-", \
#      "--error-logfile", "-", \
#      "app:app"]
#
# 替换为下面的命令：
# 直接使用'python'命令来启动'app.py'。
# Flask的app.run(host='0.0.0.0', port=5000)会处理监听地址和端口。
# 日志会因为 PYTHONUNBUFFERED=1 而直接输出到 stdout/stderr，被Docker捕获。
#
CMD ["python", "app.py"]
# ====================================================================
