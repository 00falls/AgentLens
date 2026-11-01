FROM python:3.12.14-slim-bookworm
COPY configs/sandbox/worker.py /app/worker.py
RUN mkdir -p /opt/agentlens /sandbox \
    && printf 'synthetic forbidden fixture\n' > /opt/agentlens/denied.txt \
    && chmod 644 /opt/agentlens/denied.txt \
    && groupadd --gid 10001 analyst \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /bin/sh analyst \
    && chown analyst:analyst /sandbox
WORKDIR /sandbox
USER analyst
CMD ["/bin/sleep", "180"]
