#!/usr/bin/env python3
"""
Test script to replicate and understand issue #243:
GPU memory consumption with gunicorn workers and torch models.

This script creates a minimal CLAMS app that simulates the problem
and provides tools to monitor VRAM usage across multiple workers.

Usage:
    # Development mode (single process, 1 model copy in VRAM)
    python test_issue_243.py --mode dev

    # Production mode (multiple workers, N model copies in VRAM)
    python test_issue_243.py --mode prod

    # Monitor VRAM while sending concurrent requests
    python test_issue_243.py --mode prod --monitor
"""

import argparse
import os
import sys
import time
import logging
from typing import Union

from clams import ClamsApp, Restifier
from mmif import Mmif, View, AnnotationTypes
from clams.appmetadata import AppMetadata

# Suppress warnings for cleaner output
import warnings
warnings.filterwarnings('ignore')


class DummyTorchModel:
    """
    Simulates a torch model with controllable VRAM footprint.
    Replace this with real torch model loading to see actual issue.
    """
    def __init__(self, size_mb=100):
        self.size_mb = size_mb
        self.worker_id = os.getpid()
        print(f"[Worker {self.worker_id}] Loading dummy model ({size_mb}MB)...", file=sys.stderr)

        # If torch is available, allocate actual VRAM
        try:
            import torch
            if torch.cuda.is_available():
                # Allocate a tensor to consume VRAM
                num_elements = (size_mb * 1024 * 1024) // 4  # 4 bytes per float32
                self.tensor = torch.randn(num_elements, device='cuda:0')
                print(f"[Worker {self.worker_id}] Model loaded in VRAM: {size_mb}MB", file=sys.stderr)
            else:
                print(f"[Worker {self.worker_id}] CUDA not available, using CPU", file=sys.stderr)
                self.tensor = None
        except ImportError:
            print(f"[Worker {self.worker_id}] PyTorch not available, simulating model", file=sys.stderr)
            self.tensor = None

    def predict(self, data):
        """Simulate inference"""
        return f"Prediction from worker {self.worker_id}"


class TestApp(ClamsApp):
    """
    Minimal CLAMS app that demonstrates the VRAM issue.

    The model is loaded in __init__, which happens BEFORE gunicorn forks workers.
    This means each worker gets its own copy of the model in VRAM.
    """

    def __init__(self, model_size_mb=100):
        super().__init__()
        self.model_size_mb = model_size_mb

        # THIS IS THE KEY ISSUE: Model loaded before worker fork
        self.model = DummyTorchModel(size_mb=model_size_mb)

        print(f"[Main Process {os.getpid()}] TestApp initialized", file=sys.stderr)

    def _appmetadata(self) -> AppMetadata:
        metadata = AppMetadata(
            identifier='test-issue-243',
            name='Issue 243 Test App',
            description='Test app to demonstrate GPU memory issue with gunicorn workers',
            app_version='1.0.0',
            mmif_version='1.0.0'
        )
        metadata.add_parameter(
            name='dummy_param',
            type='string',
            description='A dummy parameter',
            default='test'
        )
        return metadata

    def _annotate(self, mmif: Union[str, Mmif], **parameters) -> Mmif:
        if isinstance(mmif, str):
            mmif = Mmif(mmif)

        worker_id = os.getpid()

        # Simulate inference
        prediction = self.model.predict("dummy data")

        # Create a new view with worker info
        view = mmif.new_view()
        self.sign_view(view, parameters)

        # Add annotation showing which worker processed this
        view.metadata['worker_pid'] = worker_id
        view.metadata['model_worker_pid'] = self.model.worker_id
        view.metadata['prediction'] = prediction

        print(f"[Worker {worker_id}] Processed request with model from worker {self.model.worker_id}",
              file=sys.stderr)

        return mmif


def print_gpu_memory():
    """Print current GPU memory usage"""
    try:
        import torch
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                allocated = torch.cuda.memory_allocated(i) / 1024**2
                reserved = torch.cuda.memory_reserved(i) / 1024**2
                print(f"  GPU {i}: Allocated={allocated:.1f}MB, Reserved={reserved:.1f}MB")
        else:
            print("  CUDA not available")
    except ImportError:
        print("  PyTorch not installed")


def monitor_mode():
    """
    Monitor mode: Send concurrent requests and monitor VRAM usage.
    Run this AFTER starting the server in production mode.
    """
    import requests
    import subprocess
    import json
    from concurrent.futures import ThreadPoolExecutor, as_completed

    base_url = "http://localhost:5000"

    print("\n" + "="*70)
    print("MONITORING MODE: Sending concurrent requests")
    print("="*70)

    # Create a minimal MMIF input
    mmif_input = Mmif(validate=False)
    mmif_str = mmif_input.serialize()

    # Get initial GPU state
    print("\nInitial GPU Memory State:")
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.used,memory.total',
                                '--format=csv,noheader,nounits'],
                               capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            print(f"  {line}")
    except FileNotFoundError:
        print("  nvidia-smi not available")

    print_gpu_memory()

    # Send concurrent requests
    num_requests = 10
    print(f"\nSending {num_requests} concurrent requests...")

    def send_request(request_id):
        try:
            response = requests.post(base_url, data=mmif_str,
                                    headers={'Content-Type': 'application/json'})
            result = response.json()

            # Extract worker info
            worker_info = "N/A"
            if 'views' in result and len(result['views']) > 0:
                view = result['views'][0]
                if 'metadata' in view:
                    worker_pid = view['metadata'].get('worker_pid', 'N/A')
                    model_pid = view['metadata'].get('model_worker_pid', 'N/A')
                    worker_info = f"Worker={worker_pid}, Model={model_pid}"

            return request_id, response.status_code, worker_info
        except Exception as e:
            return request_id, f"Error: {e}", "N/A"

    with ThreadPoolExecutor(max_workers=num_requests) as executor:
        futures = [executor.submit(send_request, i) for i in range(num_requests)]

        results = []
        for future in as_completed(futures):
            results.append(future.result())

    # Display results
    print("\nRequest Results:")
    results.sort(key=lambda x: x[0])
    for req_id, status, worker_info in results:
        print(f"  Request {req_id}: Status={status}, {worker_info}")

    # Show unique workers that processed requests
    workers_seen = set()
    for _, _, worker_info in results:
        if "Worker=" in worker_info:
            workers_seen.add(worker_info.split(',')[0])

    print(f"\nUnique workers that processed requests: {len(workers_seen)}")
    for worker in sorted(workers_seen):
        print(f"  {worker}")

    # Get final GPU state
    print("\nFinal GPU Memory State:")
    try:
        result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.used,memory.total',
                                '--format=csv,noheader,nounits'],
                               capture_output=True, text=True)
        for line in result.stdout.strip().split('\n'):
            print(f"  {line}")
    except FileNotFoundError:
        print("  nvidia-smi not available")

    print_gpu_memory()

    print("\n" + "="*70)
    print("KEY OBSERVATION:")
    print(f"If you see {len(workers_seen)} unique workers, each has its own model copy in VRAM")
    print("This demonstrates the issue: N workers = N × model size in VRAM")
    print("="*70 + "\n")


def main():
    parser = argparse.ArgumentParser(description='Test Issue #243: Gunicorn, Torch, and CUDA')
    parser.add_argument('--mode', choices=['dev', 'prod', 'monitor'], default='dev',
                       help='Run mode: dev (single process), prod (gunicorn), monitor (send test requests)')
    parser.add_argument('--port', type=int, default=5000,
                       help='Port to run on (default: 5000)')
    parser.add_argument('--model-size', type=int, default=100,
                       help='Size of dummy model in MB (default: 100)')
    parser.add_argument('--workers', type=int, default=None,
                       help='Number of gunicorn workers (default: auto-calculated)')

    args = parser.parse_args()

    if args.mode == 'monitor':
        monitor_mode()
        return

    print("\n" + "="*70)
    print(f"ISSUE #243 TEST - Mode: {args.mode.upper()}")
    print("="*70)

    if args.mode == 'dev':
        print("\nDEVELOPMENT MODE:")
        print("  - Single process (Flask development server)")
        print("  - One model copy in VRAM")
        print("  - Good for testing, not production")
    else:
        import multiprocessing
        num_workers = args.workers if args.workers else (multiprocessing.cpu_count() * 2) + 1
        print("\nPRODUCTION MODE (Gunicorn):")
        print(f"  - Multiple workers: {num_workers}")
        print(f"  - Each worker loads model independently")
        print(f"  - Expected VRAM usage: ~{num_workers * args.model_size}MB")
        print(f"  - This demonstrates the issue!")

    print(f"\nModel size: {args.model_size}MB")
    print(f"Port: {args.port}")

    print("\nInitial GPU state:")
    print_gpu_memory()

    print("\nCreating app instance...")
    app = TestApp(model_size_mb=args.model_size)

    print("\nStarting HTTP server...")
    print(f"Server will be available at: http://localhost:{args.port}")

    if args.mode == 'prod':
        print("\nTo test concurrent requests, run in another terminal:")
        print(f"  python {sys.argv[0]} --mode monitor --port {args.port}")

    print("\n" + "="*70 + "\n")

    # Start the server
    http_app = Restifier(app, port=args.port)

    if args.mode == 'prod':
        options = {}
        if args.workers:
            options['workers'] = args.workers
        http_app.serve_production(**options)
    else:
        app.logger.setLevel(logging.DEBUG)
        http_app.run()


if __name__ == '__main__':
    main()
