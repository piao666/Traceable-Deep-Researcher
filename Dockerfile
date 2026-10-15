# syntax=docker/dockerfile:1
# Stage 1: Browser and build tools installation
# Python 3.12+ required for LangChain v1
FROM python:3.14-slim-bookworm AS install-browser

# Use Debian's browser packages without the optional desktop services.
# Cache downloads so interrupted builds can resume without fetching them again.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && printf 'Acquire::https::Timeout "180";\nAcquire::Retries "3";\n' > /etc/apt/apt.conf.d/80-download-retries \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       wget ca-certificates chromium chromium-driver firefox-esr build-essential \
    && chromium --version && chromedriver --version \
    && rm -rf /var/lib/apt/lists/*

RUN ARCH=$(dpkg --print-architecture) \
    && GECKO_ARCH=$(case ${ARCH} in amd64) echo "linux64" ;; arm64) echo "linux-aarch64" ;; *) echo "Unsupported architecture: ${ARCH}" >&2; exit 1 ;; esac) \
    && wget https://github.com/mozilla/geckodriver/releases/download/v0.36.0/geckodriver-v0.36.0-${GECKO_ARCH}.tar.gz \
    && tar -xvzf geckodriver-v0.36.0-${GECKO_ARCH}.tar.gz \
    && chmod +x geckodriver \
    && mv geckodriver /usr/local/bin/ \
    && rm geckodriver-v0.36.0-${GECKO_ARCH}.tar.gz

# Stage 2: Python dependencies installation
FROM install-browser AS traceable-deep-researcher-install

ENV PIP_ROOT_USER_ACTION=ignore
WORKDIR /usr/src/app

# Copy and install Python dependencies in a single layer to optimize cache usage
COPY ./requirements.txt ./requirements.txt
COPY ./multi_agents/requirements.txt ./multi_agents/requirements.txt

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt -r multi_agents/requirements.txt --upgrade --prefer-binary

# Stage 3: Final stage with non-root user and app
FROM traceable-deep-researcher-install AS traceable-deep-researcher

# Basic server configuration
ARG HOST=0.0.0.0
ENV HOST=${HOST}
ARG PORT=8000
ENV PORT=${PORT}
EXPOSE ${PORT}

# Uvicorn parameters used in CMD
ARG WORKERS=1
ENV WORKERS=${WORKERS}

# Create a non-root user for security
# NOTE: Don't use this if you are relying on `_check_pkg` to pip install packages dynamically.
RUN useradd -ms /bin/bash traceable-deep-researcher && \
    chown -R traceable-deep-researcher:traceable-deep-researcher /usr/src/app && \
    # Add these lines to create and set permissions for outputs directory
    mkdir -p /usr/src/app/outputs /usr/src/app/data /usr/src/app/logs /usr/src/app/my-docs && \
    chown -R traceable-deep-researcher:traceable-deep-researcher /usr/src/app/outputs /usr/src/app/data /usr/src/app/logs /usr/src/app/my-docs && \
    chmod 777 /usr/src/app/outputs
USER traceable-deep-researcher
WORKDIR /usr/src/app

# Copy the rest of the application files with proper ownership
COPY --chown=traceable-deep-researcher:traceable-deep-researcher ./ ./
CMD uvicorn main:app --host ${HOST} --port ${PORT} --workers ${WORKERS}
