ARG BUILD_FROM

# Build the React SPA and the Lovelace card; only static files reach the runtime image.
FROM node:22-alpine AS web
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json* frontend/
RUN cd frontend && npm ci
COPY card/package.json card/package-lock.json* card/
RUN cd card && npm ci
COPY frontend frontend
COPY card card
RUN cd frontend && npm run build && cd ../card && npm run build

FROM ${BUILD_FROM}
WORKDIR /opt/subtracker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY catalogs catalogs
COPY alembic.ini .
COPY --from=web /src/app/static app/static
COPY --from=web /src/card/dist/subtracker-card.js card/subtracker-card.js
COPY run.sh /run.sh
RUN chmod a+x /run.sh
CMD ["/run.sh"]
