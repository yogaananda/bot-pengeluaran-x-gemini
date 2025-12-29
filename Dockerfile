FROM python:3.10

WORKDIR /code

# Install pondasi sistem
RUN apt-get update && apt-get install -y \
    netbase \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt /code/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /code/requirements.txt

COPY . .

# Render tidak seketat HF soal user, tapi ini tetap praktik yang baik
RUN useradd -m -u 1000 user
RUN chown -R user:user /code
USER user

CMD ["python", "main.py"]
