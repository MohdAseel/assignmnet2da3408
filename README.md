# DA3408 Assignment 2

Docker and Kubernetes implementation for a spam-detection API and an indexed CSV-validation workload.

## Overview

This repository covers four deployment tasks:

1. Compare a naive Docker image with a multi-stage image for a FastAPI spam classifier.
2. Run the API with Redis using Docker Compose and cache repeated predictions.
3. Run eight shard validators as a Kubernetes Indexed Job.
| `GET` | `/healthz` | Returns HTTP 200 when the model is loaded. |
| `POST` | `/predict` | Accepts `{"text": "..."}` and returns a spam/ham label. |

## Repository layout

```text
.
├── app/                    # API source, model training, requirements, and Dockerfiles
├── shards/                 # Eight generated CSV input shards
├── generate_shards.py      # Deterministic shard generator and ground-truth checker
├── docker-compose.yml      # API and Redis services
├── q3_job.yaml             # Kubernetes Indexed Job manifest
├── q4_deployment.yaml      # Redis and spam API Deployment/Service manifests
├── assignment2.md          # Assignment specification and marking rubric
└── implementation_steps.md # Detailed setup and evidence workflow
```

## Prerequisites

- Python 3.10 or newer
- Docker Engine and Docker Compose v2
- `kubectl`
- A Kubernetes cluster such as Minikube

The detailed Ubuntu and Minikube setup is in [implementation_steps.md](implementation_steps.md).

## Build the model

The expected application files are `app/train.py`, `app/main.py`, `app/requirements.txt`, and the trained `app/model.joblib`. The training script reads `app/spam_dataset.csv` and saves the joblib pipeline beside it.

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r app/requirements.txt
python3 app/train.py
```

The generated dataset should contain 1,000 rows with `text` and `label` columns. Keep the generated model and dataset available before building the API image.

## Question 1: Docker images

The naive image uses a full Python base image and installs the runtime directly into it. The multi-stage image creates a virtual environment in a builder stage based on `python:3.11-slim`, then copies only that environment and the application into a fresh slim runtime stage.

Build and compare the images:

```bash
docker build -f app/Dockerfile.naive -t spam-api:naive app
docker build -f app/Dockerfile.multistage -t spam-api:multi app
docker images spam-api:naive spam-api:multi
```

Calculate the reduction from the two reported sizes:

```text
reduction (%) = ((naive size - multi-stage size) / naive size) * 100
```

The multi-stage image excludes the builder's temporary installation context, build-only files, and installer/cache artifacts. It also uses the slim runtime base instead of the full Python base. The final image should contain only the virtual environment, runtime libraries, application source, dataset, and trained model.

## Question 2: Docker Compose and Redis

The Compose file defines:

- `api`: builds the multi-stage API image and publishes port `8000`.
- `cache`: runs the official `redis:7-alpine` image.

The API must use the Compose service name `cache` as its Redis hostname, not `localhost`:

```bash
docker compose up --build -d
docker compose ps
curl http://localhost:8000/healthz
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{"text":"WIN a FREE laptop now! Click here: tinyurl.com/abc"}'
```

The first identical prediction should return `"cache": "miss"`; the repeated request should return `"cache": "hit"`. Capture timings with a small client or the benchmark described in [implementation_steps.md](implementation_steps.md), then shut down the stack with:

```bash
docker compose down
```

Compose coordinates multiple containers on one host, including networking, environment variables, and startup order. Kubernetes provides cluster-level scheduling, service discovery, replica management, self-healing, and rolling updates across nodes.

## Question 3: Indexed Job

Generate or refresh the eight deterministic validation shards:

```bash
python3 generate_shards.py
```

Each file in `shards/` contains 100 signup rows. The generator deliberately creates malformed email addresses or missing names and prints the ground-truth invalid-row count for each shard.

The Job is designed for a cluster with four allocatable CPUs:

- `completions: 8` processes every shard exactly once.
- `parallelism: 4` allows four one-CPU validator pods to run concurrently.
- CPU requests and limits are both `1`, so the Job does not oversubscribe the stated capacity.
- With three two-CPU nodes, `parallelism: 6` would be reasonable and would reduce the number of waves.

Apply and inspect the Job:

```bash
kubectl apply -f q3_job.yaml
kubectl get jobs
kubectl get pods -o wide -w
```

The required evidence is a `kubectl get pods -o wide` capture showing four active pods at once, followed by logs for all eight completions:

```bash
kubectl get pods -o wide
kubectl get pods -o name | ForEach-Object { kubectl logs $_ }
```

Results are collected through the Kubernetes API with pod logs rather than a shared volume. This is sufficient for short-lived counts and avoids extra storage/provisioner setup on Minikube.

## Question 4: Deployment, Service, and updates

The deployment manifest defines:

- Two `spam-api` replicas.
- CPU requests of `250m` and limits of `500m`.
- A readiness probe against `/healthz`.
- A NodePort Service on port `30080`.
- A Redis Deployment and ClusterIP Service for the API cache.

Apply the manifest and check readiness:

```bash
kubectl apply -f q4_deployment.yaml
kubectl rollout status deployment/spam-api-deployment
kubectl get pods -l app=spam-api -o wide
kubectl get service spam-api-service
```

### Self-healing

Delete one running API pod and observe the replacement:

```bash
kubectl delete pod <pod-name>
kubectl get pods -l app=spam-api -w
```

The Deployment manages a ReplicaSet. The ReplicaSet compares the desired replica count with the current pod count and creates a replacement when a pod is deleted.

### Rolling update

Build and load a new image tag after making a visible version change to `/healthz`:

```bash
docker build -t spam-api:k8s-v2 app
minikube image load spam-api:k8s-v2
kubectl set image deployment/spam-api-deployment api=spam-api:k8s-v2
kubectl set env deployment/spam-api-deployment APP_VERSION=k8s-v2
kubectl rollout status deployment/spam-api-deployment
kubectl rollout history deployment/spam-api-deployment
```

A Deployment replaces pods gradually while maintaining ready replicas. A Job is different: it runs finite completions and stops, so it does not provide continuous serving, replacement replicas, or rolling updates.
