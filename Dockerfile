FROM python:3.11-slim

# GUI表示(Tkinter)や画像処理、日本語フォントのインストール
RUN apt-get update && apt-get install -y \
    python3-tk \
    tk-dev \
    libgl1 \
    libglib2.0-0 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ライブラリのインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# コードのコピー
COPY . .

# 基地局の通信ポートを明示（ドキュメント用）
EXPOSE 50007