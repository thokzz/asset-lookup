#!/bin/bash
set -e

echo "Starting Asset Lookup application..."

# CRITICAL: Ensure instance directory exists and is writable
echo "Creating required directories..."
mkdir -p /app/instance
mkdir -p /app/logs
mkdir -p /app/app/static/uploads

# Set permissions to ensure write access
chmod 755 /app/instance
chmod 755 /app/logs
chmod 755 /app/app/static/uploads

# Test that we can write to the instance directory
echo "Testing database directory access..."
if touch /app/instance/test_write.tmp 2>/dev/null; then
    rm -f /app/instance/test_write.tmp
    echo "✅ Database directory is writable"
else
    echo "❌ Cannot write to /app/instance directory"
    ls -la /app/
    ls -la /app/instance/
    exit 1
fi

# Create symbolic link for email templates
echo "Setting up email templates..."
mkdir -p /app/app/templates/emails
if [ -d "/app/app/templates/email" ]; then
    ln -sf /app/app/templates/email/* /app/app/templates/emails/ 2>/dev/null || true
fi

echo "Starting application with gunicorn..."
exec gunicorn --bind 0.0.0.0:5000 run:app