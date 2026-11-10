# Floating upstream image by house standard; compatibility target is Mosquitto binary 2.1.2.
# Disposable integration tested binary 2.1.2; reverify tools on upstream image changes.
FROM eclipse-mosquitto:latest

USER root
RUN apk add --no-cache python3 py3-pip tzdata \
    && python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/mqtt-user-manager
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY wsgi.py ./
USER 1883:1883
EXPOSE 8080
# Override the Mosquitto upstream entry point; our app must never masquerade as broker PID1.
ENTRYPOINT ["python", "wsgi.py"]
