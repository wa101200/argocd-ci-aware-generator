FROM debian:bookworm-slim


COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/

WORKDIR /app


RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  uv sync --locked

COPY ./ /app/

RUN rm -rf /inference


ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080

CMD [ "python", "app/main.py"]
