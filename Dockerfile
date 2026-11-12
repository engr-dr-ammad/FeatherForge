FROM docker:27-cli AS dockercli
FROM python:3.12-slim
WORKDIR /app
COPY . .
COPY --from=dockercli /usr/local/bin/docker /usr/local/bin/docker
RUN --mount=type=secret,id=proxy_ca,target=/run/proxy-ca,required=false \
    if [ -f /run/proxy-ca ]; then export PIP_CERT=/run/proxy-ca; fi; \
    pip install --no-cache-dir -r requirements.txt && \
    chmod -R a+rX /app && mkdir -p /data && chown 1000:1000 /data
ENV PYTHONDONTWRITEBYTECODE=1 FORGE_DATA=/data
USER 1000:1000
EXPOSE 8000
CMD ["uvicorn","forge.app:app","--host","0.0.0.0","--port","8000"]
