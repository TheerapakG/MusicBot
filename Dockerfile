FROM alpine:edge

# Add project source
WORKDIR /usr/src/musicbot
COPY . ./

# Install dependencies
RUN apk update
RUN apk add --no-cache \
  ca-certificates \
  ffmpeg \
  opus \
  python3 \
  libsodium-dev

# Install build dependencies
RUN apk add --no-cache --virtual .build-deps \
  gcc \
  git \
  libffi-dev \
  make \
  musl-dev \
  python3-dev

# Install pip dependencies
RUN false
RUN pip3 install --no-cache-dir -r requirements.txt
RUN pip3 install --upgrade --force-reinstall --version websockets==4.0.1

# Clean up build dependencies
RUN apk del .build-deps

# Create volume for mapping the config
VOLUME /usr/src/musicbot/config

ENV APP_ENV=docker

ENTRYPOINT ["python3", "run.py"]
