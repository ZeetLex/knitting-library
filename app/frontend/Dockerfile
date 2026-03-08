# This file builds the React frontend.
# It creates a production build and serves it with nginx.

# Step 1: Build the React app
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (this layer is cached by Docker)
COPY package.json ./
RUN npm install --legacy-peer-deps

# Copy the rest of the frontend code and build it
COPY . .
RUN npm run build

# Step 2: Serve the built app with nginx
FROM nginx:alpine

# Copy the built React app files to nginx's web root
COPY --from=builder /app/build /usr/share/nginx/html

# Copy our custom nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
