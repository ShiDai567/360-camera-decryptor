# 使用 Python 3.11-slim 作为基础镜像
FROM python:3.11-slim

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CAMERA_CONFIG_PATH=/app/backend/data/config.yaml

# 安装系统依赖 (FFmpeg 和 Node.js)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ffmpeg \
    ca-certificates \
    nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制 Python 依赖文件并安装
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
# 注意：我们将上下文设置为项目根目录，所以这里复制整个目录的基础结构
COPY . .

# 暴露 Flask 运行端口
EXPOSE 5000

# 启动命令
CMD ["python", "backend/server.py"]
