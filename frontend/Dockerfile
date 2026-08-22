# The frontend build emits architecture-independent static assets.  Keep the
# Node build stage on the builder's native architecture so an x86 CI runner
# does not execute Node under QEMU while producing the ARM64 runtime image.
FROM --platform=$BUILDPLATFORM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Only the runtime image needs to match the requested deployment platform.
FROM --platform=$TARGETPLATFORM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
