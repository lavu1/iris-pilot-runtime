FROM python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e AS dependencies

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --require-hashes -r requirements.lock
ENV PYTHONPATH=/app/src
RUN groupadd --gid 10001 iris && useradd --uid 10001 --gid iris --no-create-home iris \
    && mkdir /output && chown iris:iris /output

FROM dependencies AS test
COPY requirements-dev.lock ./
RUN pip install --require-hashes -r requirements-dev.lock
COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
COPY fixtures ./fixtures
USER 10001:10001
ENTRYPOINT ["python", "-m", "pytest"]
CMD ["-q", "-p", "no:cacheprovider"]

FROM dependencies AS runtime
COPY pyproject.toml README.md ./
COPY src ./src
USER 10001:10001
ENTRYPOINT ["python", "-m", "iris_runtime"]
CMD ["run"]
