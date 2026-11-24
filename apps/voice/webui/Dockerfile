FROM ghcr.io/open-webui/open-webui@sha256:a26effeb220e132482bf7e0560b3404843e7bc40d23051144e062960df8df6b0

COPY patch_compiled.py /tmp/patch_station_call.py
RUN python /tmp/patch_station_call.py \
      --input /app/build/_app/immutable/chunks/D4rfk4Lu.js \
      --output /tmp/station_call.js \
    && mv /tmp/station_call.js /app/build/_app/immutable/chunks/D4rfk4Lu.js \
    && rm /tmp/patch_station_call.py

COPY patch_research_backend.py /tmp/patch_research_backend.py
RUN python /tmp/patch_research_backend.py /app/backend/open_webui \
    && rm /tmp/patch_research_backend.py

COPY patch_sso_backend.py /tmp/patch_sso_backend.py
COPY station_sso_audit.py /app/backend/open_webui/utils/station_sso_audit.py
RUN python /tmp/patch_sso_backend.py /app/backend/open_webui \
    && rm /tmp/patch_sso_backend.py
