#!/usr/bin/env python3
"""
Health check script for Docker HEALTHCHECK.
"""

import sys
import httpx

try:
    response = httpx.get("http://localhost:8080/health", timeout=3.0)
    if response.status_code == 200:
        sys.exit(0)
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
