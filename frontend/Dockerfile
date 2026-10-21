FROM node:22-slim

WORKDIR /app

COPY package.json package-lock.json .npmrc ./
RUN --mount=type=secret,id=ods_npm_token,required=true \
    ODS_NPM_TOKEN="$(cat /run/secrets/ods_npm_token)" npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]