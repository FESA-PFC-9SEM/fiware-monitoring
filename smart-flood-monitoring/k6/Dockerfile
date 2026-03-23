# Use the xk6 builder image as the build stage
FROM grafana/xk6:latest as builder

# Add your desired extensions here
# Example: with xk6-exec and xk6-output-influxdb
RUN xk6 build --with github.com/grafana/xk6-mqtt --output /tmp/k6

# Use the official k6 image as the runtime stage
FROM grafana/k6:latest

# Copy the custom-built k6 binary from the builder stage
COPY --from=builder /tmp/k6 /usr/bin/k6

# Set the entrypoint to the custom k6 binary
ENTRYPOINT ["k6"]
