FROM node:22-slim

WORKDIR /app

# ODS packages need the Artifactory credential: docker-compose.yml hands in
# the developer's ~/.npmrc as the build secret `ods_npmrc` (issue #135).
COPY package.json package-lock.json .npmrc ./
RUN --mount=type=secret,id=ods_npmrc,required=true \
    NPM_CONFIG_USERCONFIG=/run/secrets/ods_npmrc npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]