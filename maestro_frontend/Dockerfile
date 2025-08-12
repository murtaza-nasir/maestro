# Multi-stage build for React frontend
FROM node:20-alpine as build

# Set working directory
WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (including dev dependencies for build)
RUN npm install

# Copy source code
COPY . .

# Build the application
# No need for build-time API URLs anymore - using relative URLs
RUN npm run build

# Production stage with simple static server
FROM node:20-alpine

# Install serve globally for serving static files
RUN npm install -g serve

# Copy built assets from build stage
COPY --from=build /app/dist /app

# Set working directory
WORKDIR /app

# Expose port 3000 (serve default port)
EXPOSE 3000

# Start serve with CORS enabled for cross-origin requests
CMD ["serve", "-s", ".", "-l", "3000", "--cors"]
