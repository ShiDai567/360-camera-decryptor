#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility entrypoint for the camera API CLI."""

from app.api_client import CameraAPIRequest
from app.cli import main

__all__ = ["CameraAPIRequest", "main"]


if __name__ == "__main__":
    main()
